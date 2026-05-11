"""Persistence helpers for Gmail classifier trace metadata."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import EmailClassificationTrace, EmailEvent


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _preflight_status(classification: dict[str, Any]) -> str:
    if classification.get("safety_status") == "quarantined":
        return "quarantined"
    fallback_reason = classification.get("fallback_reason")
    if fallback_reason in {"prompt_injection_risk", "redaction_leak", "prompt_too_large"}:
        return f"blocked:{fallback_reason}"
    if classification.get("model_used"):
        return "llm_called"
    if classification.get("classifier_mode") == "hybrid_dry_run":
        return "dry_run_no_model"
    if classification.get("classifier_mode") == "hybrid_no_model":
        return "model_disabled"
    return "not_required"


def build_trace_feature_summary(classification: dict[str, Any]) -> dict[str, Any]:
    matched_features = classification.get("matched_features") or []
    summary: dict[str, Any] = {
        "matched_feature_count": len(matched_features) if isinstance(matched_features, list) else 0,
        "ambiguity_reasons": classification.get("ambiguity_reasons") or [],
        "fallback_reason": classification.get("fallback_reason"),
        "confidence_band": classification.get("confidence_band"),
        "status_update_allowed": bool(classification.get("status_update_allowed", False)),
        "redaction_counts": classification.get("redaction_counts") or {},
    }
    for key in ["score_summary", "route_scores", "subtype_scores"]:
        if classification.get(key) is not None:
            summary[key] = classification[key]
    return summary


async def create_email_classification_trace(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    classification: dict[str, Any],
    email_event: EmailEvent | None = None,
    gmail_message_id: str | None = None,
    candidate_source_url_count: int | None = None,
) -> EmailClassificationTrace:
    resolved_user_id = user_id or (email_event.user_id if email_event else None)
    if resolved_user_id is None:
        raise ValueError("Email classification traces require a user_id.")

    resolved_message_id = gmail_message_id or (email_event.gmail_message_id if email_event else None)
    classifier_mode = classification.get("classifier_mode") or "legacy"
    values = {
        "user_id": resolved_user_id,
        "email_event_id": email_event.id if email_event else None,
        "gmail_message_id": resolved_message_id,
        "classifier_mode": classifier_mode,
        "classification": classification.get("classification"),
        "classification_confidence": _safe_float(classification.get("confidence")),
        "route": classification.get("route"),
        "subtype": classification.get("subtype"),
        "route_confidence": _safe_float(classification.get("route_confidence")),
        "subtype_confidence": _safe_float(classification.get("subtype_confidence")),
        "decision_path": classification.get("decision_path"),
        "threshold_version": classification.get("threshold_version"),
        "policy_version": classification.get("policy_version") or classification.get("threshold_version"),
        "matched_signals_json": classification.get("matched_features") or [],
        "feature_summary_json": build_trace_feature_summary(classification),
        "preflight_status": _preflight_status(classification),
        "candidate_source_url_count": candidate_source_url_count,
        "model_used": bool(classification.get("model_used", False)),
        "status_update_allowed": bool(classification.get("status_update_allowed", False)),
    }

    if resolved_message_id:
        existing = await _find_existing_trace(
            db,
            user_id=resolved_user_id,
            gmail_message_id=resolved_message_id,
            classifier_mode=classifier_mode,
        )
        if existing:
            return await _update_existing_trace(db, existing, values)

    trace = EmailClassificationTrace(
        **values,
    )
    if not resolved_message_id:
        db.add(trace)
        await db.flush()
        return trace

    try:
        async with db.begin_nested():
            db.add(trace)
            await db.flush()
        return trace
    except IntegrityError:
        existing = await _find_existing_trace(
            db,
            user_id=resolved_user_id,
            gmail_message_id=resolved_message_id,
            classifier_mode=classifier_mode,
        )
        if not existing:
            raise
        return await _update_existing_trace(db, existing, values)


async def _find_existing_trace(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    gmail_message_id: str,
    classifier_mode: str,
) -> EmailClassificationTrace | None:
    return (
        await db.execute(
            select(EmailClassificationTrace).where(
                EmailClassificationTrace.user_id == user_id,
                EmailClassificationTrace.gmail_message_id == gmail_message_id,
                EmailClassificationTrace.classifier_mode == classifier_mode,
            )
        )
    ).scalar_one_or_none()


async def _update_existing_trace(
    db: AsyncSession,
    trace: EmailClassificationTrace,
    values: dict[str, Any],
) -> EmailClassificationTrace:
    trace.email_event_id = values["email_event_id"] or trace.email_event_id
    trace.classification = values["classification"]
    trace.classification_confidence = values["classification_confidence"]
    trace.route = values["route"]
    trace.subtype = values["subtype"]
    trace.route_confidence = values["route_confidence"]
    trace.subtype_confidence = values["subtype_confidence"]
    trace.decision_path = values["decision_path"]
    trace.threshold_version = values["threshold_version"]
    trace.policy_version = values["policy_version"]
    trace.matched_signals_json = values["matched_signals_json"]
    trace.feature_summary_json = values["feature_summary_json"]
    trace.preflight_status = values["preflight_status"]
    trace.candidate_source_url_count = values["candidate_source_url_count"]
    trace.model_used = values["model_used"]
    trace.status_update_allowed = values["status_update_allowed"]
    await db.flush()
    return trace
