"""Persistence helpers for AI model-call audit rows."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiModelCall
from backend.services.ai_pricing import estimate_cost_cents, get_effective_model_pricing

_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "oauth",
    "authorization",
    "cookie",
    "secret",
    "password",
    "gmail_token",
    "encrypted",
)


def trace_retention_days() -> int:
    raw_value = os.getenv("AI_TRACE_RETENTION_DAYS", "30")
    try:
        value = int(raw_value)
    except ValueError:
        return 30
    return max(value, 1)


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int | None = None
    context_tokens: int | None = None
    tool_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    output_tokens: int | None = None
    billable_input_tokens: int | None = None
    billable_output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        values = [
            self.prompt_tokens,
            self.context_tokens,
            self.tool_tokens,
            self.reasoning_tokens,
            self.output_tokens,
        ]
        present = [value for value in values if value is not None]
        if not present:
            return None
        return sum(max(value or 0, 0) for value in present)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            sanitized[key_text] = "[redacted]" if _is_sensitive_key(key_text) else sanitize_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_metadata(item) for item in value]
    return value


def _coerce_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def record_model_call(
    db: AsyncSession,
    *,
    surface: str,
    task_name: str,
    model: str,
    prompt_version: str,
    status: str,
    user_id: uuid.UUID | str | None = None,
    provider: str = "openai",
    variant: str | None = None,
    release_version: str | None = None,
    validation_result: str | None = None,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    latency_ms: int | float | None = None,
    retry_count: int = 0,
    token_usage: TokenUsage | None = None,
    cost_estimate_cents: int | None = None,
    cost_breakdown: dict[str, Any] | None = None,
    request_metadata: dict[str, Any] | None = None,
    response_metadata: dict[str, Any] | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    model_card_id: uuid.UUID | str | None = None,
) -> AiModelCall:
    usage = token_usage or TokenUsage()
    prompt_tokens = usage.prompt_tokens
    output_tokens = usage.output_tokens
    if cost_estimate_cents is None:
        pricing = await get_effective_model_pricing(db, provider=provider, model=model)
        cost_estimate_cents, generated_breakdown = estimate_cost_cents(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            pricing_config={(pricing.provider, pricing.model): pricing},
        )
        cost_breakdown = cost_breakdown or generated_breakdown

    release = release_version or os.getenv("APP_VERSION") or os.getenv("RAILWAY_GIT_COMMIT_SHA")
    row = AiModelCall(
        user_id=_coerce_uuid(user_id),
        surface=surface,
        task_name=task_name,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        variant=variant,
        release_version=release,
        status=status,
        validation_result=validation_result,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        latency_ms=int(latency_ms) if latency_ms is not None else None,
        retry_count=max(retry_count, 0),
        prompt_tokens=usage.prompt_tokens,
        context_tokens=usage.context_tokens,
        tool_tokens=usage.tool_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        output_tokens=usage.output_tokens,
        billable_input_tokens=usage.billable_input_tokens if usage.billable_input_tokens is not None else usage.prompt_tokens,
        billable_output_tokens=usage.billable_output_tokens if usage.billable_output_tokens is not None else usage.output_tokens,
        total_tokens=usage.total_tokens,
        cost_estimate_cents=cost_estimate_cents,
        cost_breakdown=sanitize_metadata(cost_breakdown),
        request_metadata=sanitize_metadata(request_metadata),
        response_metadata=sanitize_metadata(response_metadata),
        error_class=error_class,
        error_message=error_message[:1000] if error_message else None,
        model_card_id=_coerce_uuid(model_card_id),
    )
    db.add(row)
    await db.flush()
    return row
