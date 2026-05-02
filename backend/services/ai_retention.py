"""Retention, anonymization, and reprocessing policy helpers for AI governance."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    AiAdminAccessLog,
    AiArtifact,
    AiExperimentAssignment,
    AiFeedbackRewardEvent,
    AiModelCall,
    AiModelCard,
    AiPromotionReport,
    AiShadowRun,
)
from backend.services.ai_usage import trace_retention_days

REDACTED_TRACE_PAYLOAD: dict[str, Any] = {
    "retention_redacted": True,
    "reason": "AI_TRACE_RETENTION_DAYS elapsed",
}

REPROCESSING_POLICY: dict[str, Any] = {
    "requires_new_model_call": True,
    "preserve_original_artifacts": True,
    "allowed_source_statuses": ["success", "failure", "validation_failed"],
    "allowed_reprocess_statuses": ["queued", "running", "success", "failure", "cancelled"],
    "promotion_requires_admin_review": True,
    "rollback_requires_previous_model_card": True,
    "shadow_outputs_visible_to_user": False,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def ai_trace_retention_cutoff(*, now: datetime | None = None, retention_days: int | None = None) -> datetime:
    days = retention_days if retention_days is not None else trace_retention_days()
    return (now or _utcnow()) - timedelta(days=max(days, 1))


async def redact_expired_ai_trace_payloads(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    retention_days: int | None = None,
) -> int:
    """Redact raw metadata on old model calls while retaining aggregate ledger rows."""
    cutoff = ai_trace_retention_cutoff(now=now, retention_days=retention_days)
    result = await db.execute(
        update(AiModelCall)
        .where(AiModelCall.created_at < cutoff)
        .values(
            request_metadata=REDACTED_TRACE_PAYLOAD,
            response_metadata=REDACTED_TRACE_PAYLOAD,
            error_message=None,
        )
    )
    return int(result.rowcount or 0)


async def anonymize_user_ai_records(db: AsyncSession, *, user_id: uuid.UUID | str) -> dict[str, int]:
    """Detach AI governance rows from a deleted user without erasing aggregate evidence."""
    uid = _coerce_uuid(user_id)
    counts: dict[str, int] = {}

    updates = [
        ("ai_model_calls", update(AiModelCall).where(AiModelCall.user_id == uid).values(user_id=None)),
        ("ai_artifacts", update(AiArtifact).where(AiArtifact.user_id == uid).values(user_id=None)),
        ("ai_shadow_runs", update(AiShadowRun).where(AiShadowRun.user_id == uid).values(user_id=None)),
        ("ai_admin_access_logs", update(AiAdminAccessLog).where(AiAdminAccessLog.admin_user_id == uid).values(admin_user_id=None)),
        ("ai_promotion_reports", update(AiPromotionReport).where(AiPromotionReport.reviewed_by_user_id == uid).values(reviewed_by_user_id=None)),
        ("ai_model_cards", update(AiModelCard).where(AiModelCard.approved_by_user_id == uid).values(approved_by_user_id=None)),
    ]
    for name, stmt in updates:
        result = await db.execute(stmt)
        counts[name] = int(result.rowcount or 0)

    deletes = [
        ("ai_experiment_assignments", delete(AiExperimentAssignment).where(AiExperimentAssignment.user_id == uid)),
        ("ai_feedback_reward_events", delete(AiFeedbackRewardEvent).where(AiFeedbackRewardEvent.user_id == uid)),
    ]
    for name, stmt in deletes:
        result = await db.execute(stmt)
        counts[name] = int(result.rowcount or 0)

    return counts


def reprocessing_policy_snapshot() -> dict[str, Any]:
    return dict(REPROCESSING_POLICY)
