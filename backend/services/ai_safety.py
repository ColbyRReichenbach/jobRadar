"""App-specific AI safety gateway.

The gateway centralizes controls that must apply across OpenAI-backed surfaces:
secret/PII redaction, prompt-injection screening for untrusted email/web content,
token estimation for budget decisions, and durable safety-decision logging.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, replace
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiSafetyDecision
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


class AiSafetyBlockedError(RuntimeError):
    """Raised when a request should not be sent to the model."""


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
    score = 0.0
    reasons: list[str] = []
    for reason, weight, pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            score += weight
            reasons.append(reason)
    return PromptRisk(score=round(min(score, 1.0), 3), reasons=reasons)


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
    await record_safety_decision(
        db_session,
        preflight,
        surface=surface,
        task_name=task_config.name,
        stage="preflight",
        user_id=user_id or (metadata or {}).get("user_id"),
        metadata=metadata,
    )
    if preflight.policy_decision == POLICY_BLOCK:
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
    preflight = evaluate_payload(
        user_message,
        data_classes=kwargs.get("data_classes") or (),
        consent_snapshot=kwargs.get("consent_snapshot"),
        allow_identity=bool(kwargs.get("allow_identity", False)),
        untrusted_input=bool(kwargs.get("untrusted_input", False)),
        block_on_high_risk=bool(kwargs.get("block_on_high_risk", False)),
    )
    if preflight.policy_decision == POLICY_BLOCK:
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
