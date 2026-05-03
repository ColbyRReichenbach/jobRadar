"""App-specific AI safety gateway.

The gateway centralizes controls that must apply across OpenAI-backed surfaces:
secret/PII redaction, prompt-injection screening for untrusted email/web content,
token estimation for budget decisions, and durable safety-decision logging.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiModelCall, AiSafetyDecision
from backend.services import ai_orchestrator

logger = logging.getLogger(__name__)

DATA_CLASS_SECRET = "secret"
DATA_CLASS_USER_IDENTITY = "user_identity"
DATA_CLASS_CAREER_PRIVATE = "career_private"
DATA_CLASS_UNTRUSTED_INBOUND = "untrusted_inbound"
DATA_CLASS_PUBLIC_RESEARCH = "public_research"
DATA_CLASS_GENERATED_OUTPUT = "generated_output"

POLICY_ALLOW = "allow"
POLICY_ALLOW_REDACTED = "allow_redacted"
POLICY_BLOCK = "block"
POLICY_QUARANTINE = "quarantine"

PROMPT_INJECTION_REDACTED = "[redacted prompt-injection attempt]"

SENSITIVE_KEY_FRAGMENTS = {
    "access_token",
    "api_key",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "gmail_tokens",
    "oauth",
    "password",
    "raw_prompt",
    "system_prompt",
    "developer_prompt",
    "user_prompt",
    "refresh_token",
    "secret",
    "session",
    "token",
}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("vercel_token", re.compile(r"\bvck_[A-Za-z0-9]{20,}\b")),
    ("google_oauth_secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}\b")),
    ("google_access_token", re.compile(r"\bya29\.[A-Za-z0-9._-]+\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE)),
    ("postgres_url", re.compile(r"postgres(?:ql)?://[^\s'\"<>]+", re.IGNORECASE)),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
)

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}\b")

PROMPT_INJECTION_PATTERNS: tuple[tuple[str, float, re.Pattern[str]], ...] = (
    ("ignore_prior_instructions", 0.34, re.compile(r"\b(ignore|disregard|forget)\b.{0,80}\b(previous|prior|above|system|developer)\b.{0,40}\binstructions?\b", re.IGNORECASE | re.DOTALL)),
    ("reveal_prompt", 0.36, re.compile(r"\b(reveal|print|show|dump|exfiltrate)\b.{0,80}\b(system prompt|developer message|hidden instructions|secrets?|tokens?)\b", re.IGNORECASE | re.DOTALL)),
    ("role_override", 0.24, re.compile(r"\byou are now\b.{0,80}\b(admin|developer|system|root|policy)\b", re.IGNORECASE | re.DOTALL)),
    ("tool_exfiltration", 0.31, re.compile(r"\b(call|use|invoke)\b.{0,60}\b(tool|function|api)\b.{0,80}\b(send|post|upload|exfiltrate|leak)\b", re.IGNORECASE | re.DOTALL)),
    ("instruction_boundary", 0.22, re.compile(r"\b(begin|end)\s+(system|developer|hidden)\s+(prompt|message|instructions?)\b", re.IGNORECASE)),
    ("jailbreak", 0.24, re.compile(r"\b(jailbreak|do anything now|dan mode|bypass safety|override policy)\b", re.IGNORECASE)),
    ("data_theft", 0.38, re.compile(r"\b(list|export|return|show)\b.{0,80}\b(all users|other users|database|oauth|refresh tokens?|api keys?)\b", re.IGNORECASE | re.DOTALL)),
)


def _normalize_prompt_text_for_risk(text: str) -> str:
    return (
        text.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
    )


class AiSafetyBlockedError(RuntimeError):
    """Raised when a request should not be sent to the model."""


class AiSafetyBudgetExceededError(AiSafetyBlockedError):
    """Raised when configured AI token budgets would be exceeded."""


class AiSafetyRateLimitExceededError(AiSafetyBlockedError):
    """Raised when configured AI request rate limits would be exceeded."""


class AiSafetyQuarantinedError(AiSafetyBlockedError):
    """Raised when untrusted content is quarantined before model access."""


_semantic_prompt_guard: Any | None = None
_semantic_prompt_guard_loaded = False
_redis_rate_client: Any | None = None
_rate_limit_buckets: dict[str, list[float]] = {}


@dataclass(frozen=True)
class PromptRisk:
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class RedactionResult:
    value: Any
    counts: dict[str, int]
    reasons: list[str]


@dataclass(frozen=True)
class SafetyEvaluation:
    value: Any
    policy_decision: str
    risk_score: float
    prompt_injection_score: float
    input_data_classes: list[str]
    consent_snapshot: dict[str, Any]
    redaction_counts: dict[str, int]
    reasons: list[str]
    token_estimate: int


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return max(1, int(len(text) / 4))


def _env_int(name: str, default: int = 0) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def max_input_tokens_per_request() -> int:
    return _env_int("AI_MAX_INPUT_TOKENS_PER_REQUEST", 25000)


def per_user_daily_token_cap() -> int:
    return _env_int("AI_DAILY_TOKEN_CAP_PER_USER", 0)


def global_daily_token_cap() -> int:
    return _env_int("AI_GLOBAL_DAILY_TOKEN_CAP", 0)


def per_task_daily_token_cap() -> int:
    return _env_int("AI_TASK_DAILY_TOKEN_CAP", 0)


def per_user_rate_limit_per_minute() -> int:
    return _env_int("AI_RATE_LIMIT_PER_MINUTE_PER_USER", 60)


def per_task_rate_limit_per_minute() -> int:
    return _env_int("AI_RATE_LIMIT_PER_MINUTE_PER_TASK", 120)


def global_rate_limit_per_minute() -> int:
    return _env_int("AI_RATE_LIMIT_PER_MINUTE_GLOBAL", 0)


def quarantine_prompt_risk_threshold() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv("AI_QUARANTINE_PROMPT_RISK_THRESHOLD", "0.7"))))
    except ValueError:
        return 0.7


def semantic_prompt_guard_enabled() -> bool:
    return os.getenv("AI_SEMANTIC_PROMPT_GUARD_ENABLED", "false").lower() == "true"


def semantic_prompt_guard_threshold() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv("AI_SEMANTIC_PROMPT_GUARD_THRESHOLD", "0.7"))))
    except ValueError:
        return 0.7


def _day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _get_semantic_prompt_guard() -> Any | None:
    global _semantic_prompt_guard_loaded, _semantic_prompt_guard
    if _semantic_prompt_guard is not None:
        return _semantic_prompt_guard
    if _semantic_prompt_guard_loaded or not semantic_prompt_guard_enabled():
        return None
    _semantic_prompt_guard_loaded = True
    model_name = os.getenv("AI_SEMANTIC_PROMPT_GUARD_MODEL", "ProtectAI/deberta-v3-base-prompt-injection-v2")
    try:
        from transformers import pipeline  # type: ignore

        _semantic_prompt_guard = pipeline("text-classification", model=model_name, truncation=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_prompt_guard_unavailable model=%s error=%s", model_name, exc)
        _semantic_prompt_guard = None
    return _semantic_prompt_guard


def set_semantic_prompt_guard_for_tests(guard: Any | None) -> None:
    global _semantic_prompt_guard, _semantic_prompt_guard_loaded
    _semantic_prompt_guard = guard
    _semantic_prompt_guard_loaded = guard is not None


def reset_ai_rate_limits_for_tests() -> None:
    _rate_limit_buckets.clear()


def _add_count(counts: dict[str, int], key: str, amount: int = 1) -> None:
    counts[key] = counts.get(key, 0) + amount


def _merge_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left)
    for key, value in right.items():
        _add_count(merged, key, value)
    return merged


def detect_prompt_injection_risk(text: str) -> PromptRisk:
    if not text:
        return PromptRisk(score=0.0, reasons=[])
    risk_text = _normalize_prompt_text_for_risk(text)
    score = 0.0
    reasons: list[str] = []
    for reason, weight, pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(risk_text):
            score += weight
            reasons.append(reason)
    semantic = detect_semantic_prompt_injection_risk(risk_text)
    if semantic.score > 0:
        score = max(score, semantic.score)
        reasons.extend(semantic.reasons)
    return PromptRisk(score=round(min(score, 1.0), 3), reasons=reasons)


def detect_semantic_prompt_injection_risk(text: str) -> PromptRisk:
    guard = _get_semantic_prompt_guard()
    if guard is None or not text:
        return PromptRisk(score=0.0, reasons=[])
    try:
        raw_result = guard(text[:4000])
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_prompt_guard_failed error=%s", exc)
        return PromptRisk(score=0.0, reasons=[])

    first = raw_result[0] if isinstance(raw_result, list) and raw_result else raw_result
    if isinstance(first, list) and first:
        first = max(first, key=lambda item: float(item.get("score", 0.0)) if isinstance(item, dict) else 0.0)
    if not isinstance(first, dict):
        return PromptRisk(score=0.0, reasons=[])

    label = str(first.get("label") or "").lower()
    try:
        score = float(first.get("score") or 0.0)
    except (TypeError, ValueError):
        score = 0.0
    unsafe_label = any(token in label for token in {"injection", "malicious", "jailbreak", "unsafe", "attack"})
    if unsafe_label and score >= semantic_prompt_guard_threshold():
        return PromptRisk(score=round(min(score, 1.0), 3), reasons=["semantic_prompt_guard"])
    return PromptRisk(score=0.0, reasons=[])


def sanitize_untrusted_text(text: str) -> tuple[str, PromptRisk, dict[str, int]]:
    """Line-level prompt-injection scrubbing for untrusted email/web text."""
    risk = detect_prompt_injection_risk(text)
    counts: dict[str, int] = {}
    if not risk.reasons:
        return text, risk, counts

    sanitized_lines: list[str] = []
    for line in text.splitlines():
        line_risk = detect_prompt_injection_risk(line)
        if line_risk.reasons:
            sanitized_lines.append(PROMPT_INJECTION_REDACTED)
            _add_count(counts, "prompt_injection_line")
        else:
            sanitized_lines.append(line)
    return "\n".join(sanitized_lines), risk, counts


def _redact_string(text: str, *, allow_identity: bool) -> RedactionResult:
    counts: dict[str, int] = {}
    reasons: list[str] = []
    redacted = text

    for label, pattern in SECRET_PATTERNS:
        redacted, count = pattern.subn(f"[redacted {label}]", redacted)
        if count:
            _add_count(counts, label, count)
            reasons.append(f"redacted_{label}")

    redacted, count = PHONE_PATTERN.subn("[redacted phone]", redacted)
    if count:
        _add_count(counts, "phone", count)
        reasons.append("redacted_phone")

    if not allow_identity:
        redacted, count = EMAIL_PATTERN.subn("[redacted email]", redacted)
        if count:
            _add_count(counts, "email", count)
            reasons.append("redacted_email")

    return RedactionResult(value=redacted, counts=counts, reasons=reasons)


def redact_sensitive_value(value: Any, *, allow_identity: bool = False) -> RedactionResult:
    if isinstance(value, str):
        return _redact_string(value, allow_identity=allow_identity)
    if isinstance(value, list):
        redacted_items = []
        counts: dict[str, int] = {}
        reasons: list[str] = []
        for item in value:
            redacted = redact_sensitive_value(item, allow_identity=allow_identity)
            redacted_items.append(redacted.value)
            counts = _merge_counts(counts, redacted.counts)
            reasons.extend(redacted.reasons)
        return RedactionResult(value=redacted_items, counts=counts, reasons=sorted(set(reasons)))
    if isinstance(value, dict):
        redacted_dict: dict[str, Any] = {}
        counts: dict[str, int] = {}
        reasons: list[str] = []
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in SENSITIVE_KEY_FRAGMENTS):
                redacted_dict[key] = "[redacted secret]"
                _add_count(counts, "sensitive_key")
                reasons.append("redacted_sensitive_key")
                continue
            redacted = redact_sensitive_value(item, allow_identity=allow_identity)
            redacted_dict[key] = redacted.value
            counts = _merge_counts(counts, redacted.counts)
            reasons.extend(redacted.reasons)
        return RedactionResult(value=redacted_dict, counts=counts, reasons=sorted(set(reasons)))
    return RedactionResult(value=value, counts={}, reasons=[])


def _sanitize_prompt_injection(value: Any) -> tuple[Any, PromptRisk, dict[str, int]]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                sanitized, risk, counts = _sanitize_prompt_injection(parsed)
                return json.dumps(sanitized, sort_keys=True), risk, counts
        sanitized, risk, counts = sanitize_untrusted_text(value)
        return sanitized, risk, counts
    if isinstance(value, list):
        items = []
        max_score = 0.0
        reasons: set[str] = set()
        counts: dict[str, int] = {}
        for item in value:
            sanitized, risk, item_counts = _sanitize_prompt_injection(item)
            items.append(sanitized)
            max_score = max(max_score, risk.score)
            reasons.update(risk.reasons)
            counts = _merge_counts(counts, item_counts)
        return items, PromptRisk(score=max_score, reasons=sorted(reasons)), counts
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        max_score = 0.0
        reasons: set[str] = set()
        counts: dict[str, int] = {}
        for key, item in value.items():
            sanitized, risk, item_counts = _sanitize_prompt_injection(item)
            result[key] = sanitized
            max_score = max(max_score, risk.score)
            reasons.update(risk.reasons)
            counts = _merge_counts(counts, item_counts)
        return result, PromptRisk(score=max_score, reasons=sorted(reasons)), counts
    return value, PromptRisk(score=0.0, reasons=[]), {}


def evaluate_payload(
    value: Any,
    *,
    data_classes: Iterable[str],
    consent_snapshot: dict[str, Any] | None = None,
    allow_identity: bool = False,
    untrusted_input: bool = False,
    block_on_high_risk: bool = False,
) -> SafetyEvaluation:
    classes = sorted({str(item) for item in data_classes if item})
    sanitized_value = value
    injection_risk = PromptRisk(score=0.0, reasons=[])
    injection_counts: dict[str, int] = {}

    if untrusted_input:
        sanitized_value, injection_risk, injection_counts = _sanitize_prompt_injection(sanitized_value)

    redacted = redact_sensitive_value(sanitized_value, allow_identity=allow_identity)
    sanitized_value = redacted.value
    redaction_counts = _merge_counts(injection_counts, redacted.counts)
    reasons = sorted(set([*injection_risk.reasons, *redacted.reasons]))

    risk_score = injection_risk.score
    if redaction_counts:
        risk_score = max(risk_score, 0.25)
    if redaction_counts.get("sensitive_key") or any(key in redaction_counts for key in {"openai_api_key", "google_oauth_secret", "google_access_token", "postgres_url", "bearer_token"}):
        risk_score = max(risk_score, 0.7)
    risk_score = round(min(risk_score, 1.0), 3)

    policy_decision = POLICY_ALLOW
    if redaction_counts or injection_risk.reasons:
        policy_decision = POLICY_ALLOW_REDACTED
    if untrusted_input and injection_risk.score >= quarantine_prompt_risk_threshold():
        policy_decision = POLICY_QUARANTINE
    if block_on_high_risk and injection_risk.score >= 0.7:
        policy_decision = POLICY_BLOCK
    if block_on_high_risk and redaction_counts.get("sensitive_key"):
        policy_decision = POLICY_BLOCK

    return SafetyEvaluation(
        value=sanitized_value,
        policy_decision=policy_decision,
        risk_score=risk_score,
        prompt_injection_score=injection_risk.score,
        input_data_classes=classes,
        consent_snapshot=dict(consent_snapshot or {}),
        redaction_counts=redaction_counts,
        reasons=reasons,
        token_estimate=estimate_tokens(sanitized_value),
    )


def _uuid_or_none(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


async def record_safety_decision(
    db_session: AsyncSession | None,
    evaluation: SafetyEvaluation,
    *,
    surface: str,
    task_name: str,
    stage: str,
    user_id: uuid.UUID | str | None = None,
    model_call_id: uuid.UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if db_session is None:
        return
    row = AiSafetyDecision(
        user_id=_uuid_or_none(user_id),
        model_call_id=_uuid_or_none(model_call_id),
        surface=surface,
        task_name=task_name,
        stage=stage,
        policy_decision=evaluation.policy_decision,
        risk_score=evaluation.risk_score,
        prompt_injection_score=evaluation.prompt_injection_score,
        input_data_classes=evaluation.input_data_classes,
        consent_snapshot=evaluation.consent_snapshot,
        redaction_counts=evaluation.redaction_counts,
        reasons=evaluation.reasons,
        token_estimate=evaluation.token_estimate,
        metadata_json=redact_sensitive_value(metadata or {}, allow_identity=False).value,
    )
    db_session.add(row)
    await db_session.flush()
    await _maybe_create_admin_safety_alert(
        db_session,
        decision=row,
        evaluation=evaluation,
    )


async def _maybe_create_admin_safety_alert(
    db_session: AsyncSession,
    *,
    decision: AiSafetyDecision,
    evaluation: SafetyEvaluation,
) -> None:
    if decision.stage != "preflight":
        return
    if evaluation.policy_decision not in {POLICY_BLOCK, POLICY_QUARANTINE}:
        return
    alert_type = "ai_safety_quarantine" if evaluation.policy_decision == POLICY_QUARANTINE else "ai_safety_block"
    if any(reason.endswith("_rate_limit_exceeded") for reason in evaluation.reasons):
        alert_type = "ai_rate_limit"
    elif any(reason.endswith("_token_cap_exceeded") for reason in evaluation.reasons):
        alert_type = "ai_budget_block"
    try:
        from backend.services.alerts import create_admin_operational_alert

        await create_admin_operational_alert(
            db_session,
            alert_type=alert_type,
            title=f"AI safety {evaluation.policy_decision.replace('_', ' ')} on {decision.surface}",
            body=f"{decision.task_name} was stopped before model access. Reasons: {', '.join(evaluation.reasons) or 'policy decision'}.",
            action_url="/ai-ops?safety=review",
            dedupe_key=f"/ai-ops?safety={alert_type}:{decision.surface}:{decision.task_name}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin_ai_safety_alert_failed decision_id=%s error=%s", decision.id, exc)


async def _sum_daily_tokens(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID | str | None = None,
    surface: str | None = None,
    task_name: str | None = None,
) -> int:
    filters = [AiModelCall.created_at >= _day_start()]
    uid = _uuid_or_none(user_id)
    if uid is not None:
        filters.append(AiModelCall.user_id == uid)
    if surface:
        filters.append(AiModelCall.surface == surface)
    if task_name:
        filters.append(AiModelCall.task_name == task_name)
    value = (
        await db_session.execute(
            select(func.coalesce(func.sum(AiModelCall.total_tokens), 0)).where(*filters)
        )
    ).scalar_one()
    return int(value or 0)


def _blocked_evaluation(evaluation: SafetyEvaluation, reason: str) -> SafetyEvaluation:
    return replace(
        evaluation,
        policy_decision=POLICY_BLOCK,
        risk_score=max(evaluation.risk_score, 0.8),
        reasons=sorted(set([*evaluation.reasons, reason])),
    )


async def _get_redis_rate_client() -> Any | None:
    global _redis_rate_client
    if _redis_rate_client is not None:
        return _redis_rate_client
    redis_url = os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis.asyncio as redis  # type: ignore

        _redis_rate_client = redis.from_url(redis_url, decode_responses=True)
        await _redis_rate_client.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_rate_limit_redis_unavailable error=%s", exc)
        _redis_rate_client = None
    return _redis_rate_client


def _rate_limited_memory(key: str, limit: int, *, now: float | None = None) -> bool:
    if limit <= 0:
        return False
    current = now or time.time()
    window_start = current - 60
    bucket = [timestamp for timestamp in _rate_limit_buckets.get(key, []) if timestamp >= window_start]
    if len(bucket) >= limit:
        _rate_limit_buckets[key] = bucket
        return True
    bucket.append(current)
    _rate_limit_buckets[key] = bucket
    return False


async def _rate_limited(key: str, limit: int) -> bool:
    if limit <= 0:
        return False
    client = await _get_redis_rate_client()
    if client is None:
        return _rate_limited_memory(key, limit)
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, 60)
        return int(count) > limit
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_rate_limit_redis_failed error=%s", exc)
        return _rate_limited_memory(key, limit)


async def enforce_ai_rate_limit(
    evaluation: SafetyEvaluation,
    *,
    surface: str,
    task_name: str,
    user_id: uuid.UUID | str | None = None,
) -> SafetyEvaluation:
    user_limit = per_user_rate_limit_per_minute()
    if user_limit and user_id is not None:
        if await _rate_limited(f"apptrail:ai_rate:user:{user_id}", user_limit):
            return _blocked_evaluation(evaluation, "user_rate_limit_exceeded")

    task_limit = per_task_rate_limit_per_minute()
    if task_limit:
        if await _rate_limited(f"apptrail:ai_rate:task:{surface}:{task_name}", task_limit):
            return _blocked_evaluation(evaluation, "task_rate_limit_exceeded")

    global_limit = global_rate_limit_per_minute()
    if global_limit:
        if await _rate_limited("apptrail:ai_rate:global", global_limit):
            return _blocked_evaluation(evaluation, "global_rate_limit_exceeded")

    return evaluation


async def enforce_ai_token_budget(
    db_session: AsyncSession | None,
    evaluation: SafetyEvaluation,
    *,
    surface: str,
    task_name: str,
    user_id: uuid.UUID | str | None = None,
) -> SafetyEvaluation:
    request_cap = max_input_tokens_per_request()
    if request_cap and evaluation.token_estimate > request_cap:
        return _blocked_evaluation(evaluation, "input_token_cap_exceeded")

    if db_session is None:
        return evaluation

    user_cap = per_user_daily_token_cap()
    if user_cap and user_id is not None:
        used = await _sum_daily_tokens(db_session, user_id=user_id)
        if used + evaluation.token_estimate > user_cap:
            return _blocked_evaluation(evaluation, "user_daily_token_cap_exceeded")

    global_cap = global_daily_token_cap()
    if global_cap:
        used = await _sum_daily_tokens(db_session)
        if used + evaluation.token_estimate > global_cap:
            return _blocked_evaluation(evaluation, "global_daily_token_cap_exceeded")

    task_cap = per_task_daily_token_cap()
    if task_cap:
        used = await _sum_daily_tokens(db_session, surface=surface, task_name=task_name)
        if used + evaluation.token_estimate > task_cap:
            return _blocked_evaluation(evaluation, "task_daily_token_cap_exceeded")

    return evaluation


def _safe_metadata(metadata: dict[str, Any] | None, evaluation: SafetyEvaluation) -> dict[str, Any]:
    base = redact_sensitive_value(metadata or {}, allow_identity=False).value
    if not isinstance(base, dict):
        base = {}
    base["ai_safety"] = {
        "policy_decision": evaluation.policy_decision,
        "risk_score": evaluation.risk_score,
        "prompt_injection_score": evaluation.prompt_injection_score,
        "redaction_counts": evaluation.redaction_counts,
        "data_classes": evaluation.input_data_classes,
        "token_estimate": evaluation.token_estimate,
    }
    return base


async def run_json_task_with_safety(
    task: str | ai_orchestrator.AiTaskConfig,
    user_message: str,
    *,
    metadata: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    db_session: AsyncSession | None = None,
    user_id: uuid.UUID | str | None = None,
    data_classes: Iterable[str] = (),
    consent_snapshot: dict[str, Any] | None = None,
    allow_identity: bool = False,
    untrusted_input: bool = False,
    block_on_high_risk: bool = False,
    output_data_classes: Iterable[str] = (DATA_CLASS_GENERATED_OUTPUT,),
) -> ai_orchestrator.AiTaskRunResult:
    task_config = ai_orchestrator.get_task(task) if isinstance(task, str) else task
    surface = str((metadata or {}).get("surface") or task_config.service_path)

    preflight = evaluate_payload(
        user_message,
        data_classes=data_classes,
        consent_snapshot=consent_snapshot,
        allow_identity=allow_identity,
        untrusted_input=untrusted_input,
        block_on_high_risk=block_on_high_risk,
    )
    preflight = await enforce_ai_rate_limit(
        preflight,
        surface=surface,
        task_name=task_config.name,
        user_id=user_id or (metadata or {}).get("user_id"),
    )
    preflight = await enforce_ai_token_budget(
        db_session,
        preflight,
        surface=surface,
        task_name=task_config.name,
        user_id=user_id or (metadata or {}).get("user_id"),
    )
    await record_safety_decision(
        db_session,
        preflight,
        surface=surface,
        task_name=task_config.name,
        stage="preflight",
        user_id=user_id or (metadata or {}).get("user_id"),
        metadata=metadata,
    )
    if preflight.policy_decision == POLICY_QUARANTINE:
        raise AiSafetyQuarantinedError(f"AI request quarantined for {task_config.name}: {', '.join(preflight.reasons)}")
    if preflight.policy_decision == POLICY_BLOCK:
        if any(reason.endswith("_token_cap_exceeded") for reason in preflight.reasons):
            raise AiSafetyBudgetExceededError(f"AI token budget blocked {task_config.name}: {', '.join(preflight.reasons)}")
        if any(reason.endswith("_rate_limit_exceeded") for reason in preflight.reasons):
            raise AiSafetyRateLimitExceededError(f"AI rate limit blocked {task_config.name}: {', '.join(preflight.reasons)}")
        raise AiSafetyBlockedError(f"AI request blocked by safety policy for {task_config.name}: {', '.join(preflight.reasons)}")

    result = await ai_orchestrator.run_json_task_with_metadata(
        task_config,
        str(preflight.value),
        metadata=_safe_metadata(metadata, preflight),
        max_tokens=max_tokens,
        db_session=db_session,
        user_id=str(user_id) if user_id is not None else None,
    )

    postflight = evaluate_payload(
        result.payload,
        data_classes=output_data_classes,
        consent_snapshot=consent_snapshot,
        allow_identity=allow_identity,
        untrusted_input=False,
        block_on_high_risk=False,
    )
    await record_safety_decision(
        db_session,
        postflight,
        surface=surface,
        task_name=task_config.name,
        stage="postflight",
        user_id=user_id or (metadata or {}).get("user_id"),
        model_call_id=result.model_call_id,
        metadata={"model": result.model, "prompt_version": result.prompt_version},
    )
    if postflight.value != result.payload:
        return replace(result, payload=postflight.value)
    return result


async def run_json_task(
    task: str | ai_orchestrator.AiTaskConfig,
    user_message: str,
    **kwargs: Any,
) -> dict[str, Any]:
    if kwargs.get("db_session") is not None:
        return (await run_json_task_with_safety(task, user_message, **kwargs)).payload

    task_config = ai_orchestrator.get_task(task) if isinstance(task, str) else task
    metadata = kwargs.get("metadata")
    effective_user_id = kwargs.get("user_id") or ((metadata or {}).get("user_id") if isinstance(metadata, dict) else None)
    preflight = evaluate_payload(
        user_message,
        data_classes=kwargs.get("data_classes") or (),
        consent_snapshot=kwargs.get("consent_snapshot"),
        allow_identity=bool(kwargs.get("allow_identity", False)),
        untrusted_input=bool(kwargs.get("untrusted_input", False)),
        block_on_high_risk=bool(kwargs.get("block_on_high_risk", False)),
    )
    preflight = await enforce_ai_rate_limit(
        preflight,
        surface=str((metadata or {}).get("surface") or task_config.service_path),
        task_name=task_config.name,
        user_id=effective_user_id,
    )
    preflight = await enforce_ai_token_budget(
        None,
        preflight,
        surface=str((metadata or {}).get("surface") or task_config.service_path),
        task_name=task_config.name,
        user_id=effective_user_id,
    )
    if preflight.policy_decision == POLICY_QUARANTINE:
        raise AiSafetyQuarantinedError(f"AI request quarantined for {task_config.name}: {', '.join(preflight.reasons)}")
    if preflight.policy_decision == POLICY_BLOCK:
        if any(reason.endswith("_token_cap_exceeded") for reason in preflight.reasons):
            raise AiSafetyBudgetExceededError(f"AI token budget blocked {task_config.name}: {', '.join(preflight.reasons)}")
        if any(reason.endswith("_rate_limit_exceeded") for reason in preflight.reasons):
            raise AiSafetyRateLimitExceededError(f"AI rate limit blocked {task_config.name}: {', '.join(preflight.reasons)}")
        raise AiSafetyBlockedError(f"AI request blocked by safety policy for {task_config.name}: {', '.join(preflight.reasons)}")

    payload = await ai_orchestrator.run_json_task(
        task_config,
        str(preflight.value),
        metadata=_safe_metadata(metadata, preflight),
        max_tokens=kwargs.get("max_tokens"),
        user_id=str(kwargs["user_id"]) if kwargs.get("user_id") is not None else None,
    )
    postflight = evaluate_payload(
        payload,
        data_classes=kwargs.get("output_data_classes") or (DATA_CLASS_GENERATED_OUTPUT,),
        consent_snapshot=kwargs.get("consent_snapshot"),
        allow_identity=bool(kwargs.get("allow_identity", False)),
    )
    return postflight.value
