"""Admin AI Ops telemetry and lineage services."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    AiAdminAccessLog,
    AiArtifact,
    AiExperiment,
    AiModelCall,
    AiModelCard,
    AiPromotionReport,
    AiSafetyDecision,
    AiShadowRun,
    SearchDocument,
)

REDACTED_KEYS = {"raw_prompt", "system_prompt", "email_body", "body", "access_token", "refresh_token", "api_key"}
_TRUTHY_VALUES = {"1", "true", "yes", "on"}


class FullTraceAccessDisabledError(RuntimeError):
    """Raised when raw AI trace payload access is disabled by deployment policy."""


def full_trace_payload_access_enabled() -> bool:
    return os.getenv("AI_TRACE_FULL_PAYLOADS_ENABLED", "false").strip().lower() in _TRUTHY_VALUES


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, inner in value.items():
            if str(key).lower() in REDACTED_KEYS:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_mapping(inner)
        return redacted
    if isinstance(value, list):
        return [_redact_mapping(item) for item in value]
    return value


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(len(ordered) * 0.95)) - 1))
    return ordered[index]


def serialize_model_call(call: AiModelCall) -> dict[str, Any]:
    return {
        "id": str(call.id),
        "user_id": str(call.user_id) if call.user_id else None,
        "surface": call.surface,
        "task_name": call.task_name,
        "provider": call.provider,
        "model": call.model,
        "prompt_version": call.prompt_version,
        "variant": call.variant,
        "status": call.status,
        "validation_result": call.validation_result,
        "fallback_used": call.fallback_used,
        "fallback_reason": call.fallback_reason,
        "latency_ms": call.latency_ms,
        "total_tokens": call.total_tokens,
        "prompt_tokens": call.prompt_tokens,
        "output_tokens": call.output_tokens,
        "cost_estimate_cents": call.cost_estimate_cents,
        "created_at": _iso(call.created_at),
    }


async def telemetry_overview(db: AsyncSession) -> dict[str, Any]:
    calls = list((await db.execute(select(AiModelCall))).scalars())
    total_calls = len(calls)
    failures = [call for call in calls if call.status != "success"]
    fallbacks = [call for call in calls if call.fallback_used]
    latencies = [call.latency_ms or 0 for call in calls if call.latency_ms is not None]
    total_cost = sum(call.cost_estimate_cents or 0 for call in calls)
    total_tokens = sum(call.total_tokens or 0 for call in calls)

    by_task: dict[str, dict[str, Any]] = {}
    for call in calls:
        key = f"{call.surface}:{call.task_name}"
        row = by_task.setdefault(key, {"surface": call.surface, "task_name": call.task_name, "calls": 0, "cost_cents": 0, "failures": 0})
        row["calls"] += 1
        row["cost_cents"] += call.cost_estimate_cents or 0
        row["failures"] += 1 if call.status != "success" else 0

    doc_count = int((await db.execute(select(func.count(SearchDocument.id)))).scalar_one() or 0)
    stale_count = int(
        (
            await db.execute(
                select(func.count(SearchDocument.id)).where(
                    SearchDocument.source_updated_at.isnot(None),
                    SearchDocument.indexed_at < SearchDocument.source_updated_at,
                )
            )
        ).scalar_one()
        or 0
    )
    queued_shadow = int(
        (await db.execute(select(func.count(AiShadowRun.id)).where(AiShadowRun.status == "queued"))).scalar_one() or 0
    )
    running_experiments = int(
        (await db.execute(select(func.count(AiExperiment.id)).where(AiExperiment.status == "running"))).scalar_one() or 0
    )
    paused_experiments = int(
        (await db.execute(select(func.count(AiExperiment.id)).where(AiExperiment.status == "paused"))).scalar_one() or 0
    )
    pending_promotions = int(
        (await db.execute(select(func.count(AiPromotionReport.id)).where(AiPromotionReport.status == "pending_review"))).scalar_one() or 0
    )
    blocked_safety_decisions = int(
        (
            await db.execute(
                select(func.count(AiSafetyDecision.id)).where(AiSafetyDecision.policy_decision == "block")
            )
        ).scalar_one()
        or 0
    )
    redacted_safety_decisions = int(
        (
            await db.execute(
                select(func.count(AiSafetyDecision.id)).where(AiSafetyDecision.policy_decision == "allow_redacted")
            )
        ).scalar_one()
        or 0
    )
    quarantined_safety_decisions = int(
        (
            await db.execute(
                select(func.count(AiSafetyDecision.id)).where(AiSafetyDecision.policy_decision == "quarantine")
            )
        ).scalar_one()
        or 0
    )
    unreviewed_safety_decisions = int(
        (
            await db.execute(
                select(func.count(AiSafetyDecision.id)).where(
                    AiSafetyDecision.policy_decision.in_(("block", "quarantine")),
                    AiSafetyDecision.review_status == "unreviewed",
                )
            )
        ).scalar_one()
        or 0
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overview": {
            "total_calls": total_calls,
            "failure_count": len(failures),
            "failure_rate": round(len(failures) / total_calls, 4) if total_calls else 0.0,
            "fallback_rate": round(len(fallbacks) / total_calls, 4) if total_calls else 0.0,
            "total_cost_cents": total_cost,
            "total_tokens": total_tokens,
            "p95_latency_ms": _p95(latencies),
        },
        "by_task": sorted(by_task.values(), key=lambda item: item["calls"], reverse=True),
        "search_freshness": {
            "document_count": doc_count,
            "stale_document_count": stale_count,
        },
        "queue_health": {
            "queued_shadow_runs": queued_shadow,
        },
        "experiment_guardrails": {
            "running_experiments": running_experiments,
            "paused_experiments": paused_experiments,
            "pending_promotion_reports": pending_promotions,
        },
        "safety_guardrails": {
            "blocked_decisions": blocked_safety_decisions,
            "redacted_decisions": redacted_safety_decisions,
            "quarantined_decisions": quarantined_safety_decisions,
            "unreviewed_decisions": unreviewed_safety_decisions,
        },
    }


async def list_runs(db: AsyncSession, *, limit: int = 50, surface: str | None = None, task_name: str | None = None) -> list[dict[str, Any]]:
    filters = []
    if surface:
        filters.append(AiModelCall.surface == surface)
    if task_name:
        filters.append(AiModelCall.task_name == task_name)
    rows = list(
        (
            await db.execute(
                select(AiModelCall)
                .where(*filters)
                .order_by(AiModelCall.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    return [serialize_model_call(row) for row in rows]


async def run_detail(db: AsyncSession, *, call_id: uuid.UUID) -> dict[str, Any] | None:
    call = await db.get(AiModelCall, call_id)
    if call is None:
        return None
    artifacts = list(
        (
            await db.execute(
                select(AiArtifact).where(AiArtifact.model_call_id == call.id).order_by(AiArtifact.created_at.desc())
            )
        ).scalars()
    )
    return {
        "run": serialize_model_call(call),
        "request_metadata": _redact_mapping(call.request_metadata or {}),
        "response_metadata": _redact_mapping(call.response_metadata or {}),
        "artifacts": [serialize_artifact(item) for item in artifacts],
        "full_trace_available": full_trace_payload_access_enabled(),
        "full_trace_requires_reason": True,
    }


async def full_trace_with_access_log(
    db: AsyncSession,
    *,
    call_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    reason: str,
) -> dict[str, Any] | None:
    if len(reason.strip()) < 8:
        raise ValueError("A specific access reason is required")
    if not full_trace_payload_access_enabled():
        raise FullTraceAccessDisabledError("Full trace payload access is disabled for this environment")
    call = await db.get(AiModelCall, call_id)
    if call is None:
        return None
    log = AiAdminAccessLog(
        admin_user_id=admin_user_id,
        action="view_full_ai_trace",
        target_type="ai_model_call",
        target_id=call.id,
        reason=reason.strip(),
        metadata_json={"surface": call.surface, "task_name": call.task_name},
    )
    db.add(log)
    await db.flush()
    return {
        "run": serialize_model_call(call),
        "request_metadata": call.request_metadata or {},
        "response_metadata": call.response_metadata or {},
        "access_log_id": str(log.id),
    }


def serialize_artifact(artifact: AiArtifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "user_id": str(artifact.user_id) if artifact.user_id else None,
        "model_call_id": str(artifact.model_call_id) if artifact.model_call_id else None,
        "artifact_type": artifact.artifact_type,
        "artifact_ref_id": str(artifact.artifact_ref_id) if artifact.artifact_ref_id else None,
        "title": artifact.title,
        "path": artifact.path,
        "metadata": _redact_mapping(artifact.metadata_json or {}),
        "created_at": _iso(artifact.created_at),
    }


async def list_artifacts(db: AsyncSession, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(AiArtifact).order_by(AiArtifact.created_at.desc()).limit(limit))).scalars())
    return [serialize_artifact(row) for row in rows]


async def list_experiments(db: AsyncSession) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(AiExperiment).order_by(AiExperiment.created_at.desc()))).scalars())
    return [
        {
            "id": str(row.id),
            "experiment_key": row.experiment_key,
            "surface": row.surface,
            "task_name": row.task_name,
            "status": row.status,
            "control_variant": row.control_variant,
            "candidate_variants": row.candidate_variants or [],
            "traffic_allocation": row.traffic_allocation or {},
            "guardrail_thresholds": row.guardrail_thresholds or {},
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in rows
    ]


async def list_model_cards(db: AsyncSession) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(AiModelCard).order_by(AiModelCard.created_at.desc()))).scalars())
    return [
        {
            "id": str(row.id),
            "task_name": row.task_name,
            "model": row.model,
            "prompt_version": row.prompt_version,
            "approval_status": row.approval_status,
            "primary_metrics": row.primary_metrics or {},
            "guardrail_metrics": row.guardrail_metrics or {},
            "updated_at": _iso(row.updated_at),
        }
        for row in rows
    ]


async def list_promotion_reports(db: AsyncSession) -> list[dict[str, Any]]:
    rows = list((await db.execute(select(AiPromotionReport).order_by(AiPromotionReport.created_at.desc()))).scalars())
    return [
        {
            "id": str(row.id),
            "experiment_id": str(row.experiment_id),
            "status": row.status,
            "recommendation": row.recommendation,
            "generated_after_calls": row.generated_after_calls,
            "generated_after_feedback": row.generated_after_feedback,
            "report": _redact_mapping(row.report_json or {}),
            "created_at": _iso(row.created_at),
            "reviewed_at": _iso(row.reviewed_at),
        }
        for row in rows
    ]


async def list_trace_access_logs(db: AsyncSession, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(AiAdminAccessLog)
                .order_by(AiAdminAccessLog.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    return [
        {
            "id": str(row.id),
            "admin_user_id": str(row.admin_user_id) if row.admin_user_id else None,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": str(row.target_id) if row.target_id else None,
            "reason": row.reason,
            "metadata": _redact_mapping(row.metadata_json or {}),
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]


def serialize_safety_decision(row: AiSafetyDecision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id) if row.user_id else None,
        "model_call_id": str(row.model_call_id) if row.model_call_id else None,
        "surface": row.surface,
        "task_name": row.task_name,
        "stage": row.stage,
        "policy_decision": row.policy_decision,
        "risk_score": row.risk_score,
        "prompt_injection_score": row.prompt_injection_score,
        "input_data_classes": row.input_data_classes or [],
        "consent_snapshot": _redact_mapping(row.consent_snapshot or {}),
        "redaction_counts": row.redaction_counts or {},
        "reasons": row.reasons or [],
        "token_estimate": row.token_estimate,
        "metadata": _redact_mapping(row.metadata_json or {}),
        "review_status": row.review_status or "unreviewed",
        "reviewed_by_user_id": str(row.reviewed_by_user_id) if row.reviewed_by_user_id else None,
        "reviewed_at": _iso(row.reviewed_at),
        "review_notes": row.review_notes,
        "created_at": _iso(row.created_at),
    }


async def list_safety_decisions(
    db: AsyncSession,
    *,
    limit: int = 50,
    surface: str | None = None,
    task_name: str | None = None,
    policy_decision: str | None = None,
    stage: str | None = None,
    min_risk: float | None = None,
) -> list[dict[str, Any]]:
    filters = []
    if surface:
        filters.append(AiSafetyDecision.surface == surface)
    if task_name:
        filters.append(AiSafetyDecision.task_name == task_name)
    if policy_decision:
        filters.append(AiSafetyDecision.policy_decision == policy_decision)
    if stage:
        filters.append(AiSafetyDecision.stage == stage)
    if min_risk is not None:
        filters.append(AiSafetyDecision.risk_score >= min_risk)
    rows = list(
        (
            await db.execute(
                select(AiSafetyDecision)
                .where(*filters)
                .order_by(AiSafetyDecision.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    return [serialize_safety_decision(row) for row in rows]


async def review_safety_decision(
    db: AsyncSession,
    *,
    decision_id: uuid.UUID,
    admin_user_id: uuid.UUID,
    review_status: str,
    review_notes: str | None = None,
) -> dict[str, Any] | None:
    row = await db.get(AiSafetyDecision, decision_id)
    if row is None:
        return None
    row.review_status = review_status
    row.reviewed_by_user_id = admin_user_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.review_notes = review_notes.strip() if review_notes else None
    await db.flush()
    return serialize_safety_decision(row)
