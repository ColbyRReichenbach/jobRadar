"""Governed AI experiment assignment, feedback rewards, and shadow runs."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    AiExperiment,
    AiExperimentAssignment,
    AiFeedbackRewardEvent,
    AiModelCall,
    AiShadowRun,
    CopilotFeedback,
    CopilotMessage,
)


def experiments_enabled() -> bool:
    return os.getenv("COPILOT_EXPERIMENTS_ENABLED", "false").lower() == "true"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stable_unit_interval(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def _input_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def create_or_update_experiment(
    db: AsyncSession,
    *,
    experiment_key: str,
    surface: str,
    task_name: str,
    status: str = "draft",
    control_variant: str = "control",
    candidate_variants: list[str] | None = None,
    traffic_allocation: dict[str, float] | None = None,
    guardrail_thresholds: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AiExperiment:
    experiment = (
        await db.execute(select(AiExperiment).where(AiExperiment.experiment_key == experiment_key))
    ).scalars().first()
    if experiment is None:
        experiment = AiExperiment(experiment_key=experiment_key, surface=surface, task_name=task_name)
        db.add(experiment)
    experiment.surface = surface
    experiment.task_name = task_name
    experiment.status = status
    experiment.control_variant = control_variant
    experiment.candidate_variants = candidate_variants or []
    experiment.traffic_allocation = traffic_allocation or {}
    experiment.guardrail_thresholds = guardrail_thresholds or {}
    experiment.metadata_json = metadata or {}
    experiment.updated_at = _utcnow()
    await db.flush()
    return experiment


async def assign_variant(db: AsyncSession, *, experiment: AiExperiment, user_id: uuid.UUID) -> AiExperimentAssignment:
    existing = (
        await db.execute(
            select(AiExperimentAssignment).where(
                AiExperimentAssignment.experiment_id == experiment.id,
                AiExperimentAssignment.user_id == user_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing

    variant = experiment.control_variant
    if experiments_enabled() and experiment.status == "running":
        score = _stable_unit_interval(str(experiment.id), str(user_id))
        cumulative = 0.0
        for candidate in experiment.candidate_variants or []:
            cumulative += float((experiment.traffic_allocation or {}).get(candidate, 0.0))
            if score < cumulative:
                variant = candidate
                break

    assignment = AiExperimentAssignment(
        experiment_id=experiment.id,
        user_id=user_id,
        variant=variant,
        assigned_by="deterministic_hash" if variant != experiment.control_variant else "control_or_disabled",
    )
    db.add(assignment)
    await db.flush()
    return assignment


async def queue_shadow_run(
    db: AsyncSession,
    *,
    experiment: AiExperiment,
    user_id: uuid.UUID | None,
    production_model_call_id: uuid.UUID | None,
    candidate_variant: str,
    input_payload: str,
    output_metadata: dict[str, Any] | None = None,
) -> AiShadowRun:
    row = AiShadowRun(
        experiment_id=experiment.id,
        user_id=user_id,
        production_model_call_id=production_model_call_id,
        candidate_variant=candidate_variant,
        input_hash=_input_hash(input_payload),
        status="queued",
        visible_to_user=False,
        output_metadata=output_metadata or {},
    )
    db.add(row)
    await db.flush()
    return row


def reward_score_for_rating(rating: str) -> float:
    if rating == "thumbs_up":
        return 1.0
    if rating == "thumbs_down":
        return -1.0
    return 0.0


async def record_feedback_reward_event(db: AsyncSession, *, feedback: CopilotFeedback) -> AiFeedbackRewardEvent:
    existing = (
        await db.execute(select(AiFeedbackRewardEvent).where(AiFeedbackRewardEvent.feedback_id == feedback.id))
    ).scalars().first()
    message = await db.get(CopilotMessage, feedback.message_id)
    model_call = await db.get(AiModelCall, message.model_call_id) if message and message.model_call_id else None
    experiment_key = None
    if model_call and isinstance(model_call.request_metadata, dict):
        experiment_key = model_call.request_metadata.get("experiment_key")

    row = existing or AiFeedbackRewardEvent(
        feedback_id=feedback.id,
        message_id=feedback.message_id,
        user_id=feedback.user_id,
        rating=feedback.rating,
        reward_score=reward_score_for_rating(feedback.rating),
    )
    row.model_call_id = model_call.id if model_call else None
    row.experiment_key = experiment_key
    row.variant = model_call.variant if model_call else None
    row.rating = feedback.rating
    row.reward_score = reward_score_for_rating(feedback.rating)
    row.metadata_json = {"source": "copilot_feedback"}
    if existing is None:
        db.add(row)
    await db.flush()
    return row


async def auto_pause_if_guardrail_breached(
    db: AsyncSession,
    *,
    experiment: AiExperiment,
    guardrail_metrics: dict[str, float],
) -> bool:
    thresholds = experiment.guardrail_thresholds or {}
    max_critical = thresholds.get("max_critical_failure_rate")
    if max_critical is None:
        return False
    if float(guardrail_metrics.get("critical_failure_rate", 0.0)) <= float(max_critical):
        return False
    experiment.status = "paused"
    experiment.metadata_json = {
        **(experiment.metadata_json or {}),
        "auto_pause_reason": "critical_guardrail_breach",
        "last_guardrail_metrics": guardrail_metrics,
    }
    experiment.updated_at = _utcnow()
    await db.flush()
    return True
