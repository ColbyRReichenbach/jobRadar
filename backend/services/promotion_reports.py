"""Promotion report generation for governed AI experiments."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiExperiment, AiFeedbackRewardEvent, AiModelCall, AiPromotionReport
from backend.services.statistics import mean_delta, minimum_detectable_effect_warning, wilson_interval


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _variant_list(experiment: AiExperiment) -> list[str]:
    return [experiment.control_variant, *(experiment.candidate_variants or [])]


def _call_in_experiment(call: AiModelCall, experiment: AiExperiment) -> bool:
    metadata = call.request_metadata if isinstance(call.request_metadata, dict) else {}
    return (
        call.surface == experiment.surface
        and call.task_name == experiment.task_name
        and call.variant in set(_variant_list(experiment))
        and metadata.get("experiment_key") == experiment.experiment_key
    )


async def _calls_for_experiment(db: AsyncSession, experiment: AiExperiment) -> list[AiModelCall]:
    rows = list(
        (
            await db.execute(
                select(AiModelCall).where(
                    AiModelCall.surface == experiment.surface,
                    AiModelCall.task_name == experiment.task_name,
                )
            )
        ).scalars()
    )
    return [row for row in rows if _call_in_experiment(row, experiment)]


async def _rewards_for_experiment(db: AsyncSession, experiment: AiExperiment) -> list[AiFeedbackRewardEvent]:
    return list(
        (
            await db.execute(
                select(AiFeedbackRewardEvent).where(
                    AiFeedbackRewardEvent.experiment_key == experiment.experiment_key,
                )
            )
        ).scalars()
    )


def _summarize_variant(variant: str, calls: list[AiModelCall], rewards: list[AiFeedbackRewardEvent]) -> dict[str, Any]:
    variant_calls = [call for call in calls if call.variant == variant]
    variant_rewards = [reward for reward in rewards if reward.variant == variant]
    thumbs_up = sum(1 for reward in variant_rewards if reward.reward_score > 0)
    cost = sum(call.cost_estimate_cents or 0 for call in variant_calls)
    latencies = [call.latency_ms or 0 for call in variant_calls if call.latency_ms is not None]
    feedback_count = len(variant_rewards)
    positive_rate = thumbs_up / feedback_count if feedback_count else 0.0
    avg_reward = sum(reward.reward_score for reward in variant_rewards) / feedback_count if feedback_count else 0.0
    return {
        "variant": variant,
        "call_count": len(variant_calls),
        "feedback_count": feedback_count,
        "thumbs_up": thumbs_up,
        "thumbs_down": sum(1 for reward in variant_rewards if reward.reward_score < 0),
        "positive_rate": round(positive_rate, 4),
        "positive_rate_ci": wilson_interval(thumbs_up, feedback_count),
        "avg_reward": round(avg_reward, 4),
        "total_cost_cents": cost,
        "avg_cost_cents": round(cost / len(variant_calls), 4) if variant_calls else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
        "fallback_rate": round(sum(1 for call in variant_calls if call.fallback_used) / len(variant_calls), 4) if variant_calls else 0.0,
        "guardrail_failure_rate": round(
            sum(1 for call in variant_calls if call.validation_result not in {None, "valid", "passed"}) / len(variant_calls),
            4,
        ) if variant_calls else 0.0,
    }


def _scale_projection(summary: dict[str, Any], users: int) -> dict[str, Any]:
    return {
        "users": users,
        "projected_requests": users,
        "projected_cost_cents": round(float(summary["avg_cost_cents"]) * users, 2),
    }


def _task_mix(calls: list[AiModelCall]) -> dict[str, dict[str, int]]:
    mix: dict[str, dict[str, int]] = {}
    for call in calls:
        variant = call.variant or "unknown"
        metadata = call.request_metadata if isinstance(call.request_metadata, dict) else {}
        query_type = str(metadata.get("query_type") or "unknown")
        mix.setdefault(variant, {})
        mix[variant][query_type] = mix[variant].get(query_type, 0) + 1
    return mix


def _recommendation(
    experiment: AiExperiment,
    summaries: list[dict[str, Any]],
    *,
    min_calls: int,
    min_feedback: int,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    control = next((item for item in summaries if item["variant"] == experiment.control_variant), None)
    if not control:
        return "keep_control_collect_more_data", ["Missing control summary."]
    for summary in summaries:
        warning = minimum_detectable_effect_warning(summary["call_count"], min_calls)
        if warning:
            warnings.append(f"{summary['variant']}: {warning}")
        feedback_warning = minimum_detectable_effect_warning(summary["feedback_count"], min_feedback)
        if feedback_warning:
            warnings.append(f"{summary['variant']}: {feedback_warning}")
    if warnings:
        return "keep_control_collect_more_data", warnings

    candidates = [item for item in summaries if item["variant"] != experiment.control_variant]
    if not candidates:
        return "keep_control", warnings
    best = max(candidates, key=lambda item: (item["avg_reward"], -item["avg_cost_cents"], -item["avg_latency_ms"]))
    reward_delta = mean_delta(float(best["avg_reward"]), float(control["avg_reward"]))
    cost_delta = mean_delta(float(best["avg_cost_cents"]), float(control["avg_cost_cents"]))
    if reward_delta > 0 and cost_delta <= max(1.0, float(control["avg_cost_cents"]) * 0.1):
        return f"promote:{best['variant']}", warnings
    return "keep_control", warnings


async def generate_promotion_report(
    db: AsyncSession,
    *,
    experiment: AiExperiment,
    min_calls: int = 1000,
    min_feedback: int = 50,
) -> AiPromotionReport:
    calls = await _calls_for_experiment(db, experiment)
    rewards = await _rewards_for_experiment(db, experiment)
    summaries = [_summarize_variant(variant, calls, rewards) for variant in _variant_list(experiment)]
    recommendation, warnings = _recommendation(experiment, summaries, min_calls=min_calls, min_feedback=min_feedback)
    projections = {
        summary["variant"]: [_scale_projection(summary, users) for users in (1_000, 10_000, 1_000_000)]
        for summary in summaries
    }
    report = AiPromotionReport(
        experiment_id=experiment.id,
        status="pending_review",
        recommendation=recommendation,
        generated_after_calls=len(calls),
        generated_after_feedback=len(rewards),
        report_json={
            "experiment_key": experiment.experiment_key,
            "variant_summaries": summaries,
            "task_query_mix": _task_mix(calls),
            "warnings": warnings,
            "scale_projections": projections,
            "admin_decision_required": True,
        },
    )
    db.add(report)
    await db.flush()
    return report


async def approve_promotion_report(
    db: AsyncSession,
    *,
    report: AiPromotionReport,
    admin_user_id: uuid.UUID,
) -> AiPromotionReport:
    experiment = await db.get(AiExperiment, report.experiment_id)
    report.status = "approved"
    report.reviewed_by_user_id = admin_user_id
    report.reviewed_at = _utcnow()
    if experiment and report.recommendation.startswith("promote:"):
        experiment.control_variant = report.recommendation.split(":", 1)[1]
        experiment.status = "completed"
        experiment.updated_at = _utcnow()
    await db.flush()
    return report


async def reject_promotion_report(
    db: AsyncSession,
    *,
    report: AiPromotionReport,
    admin_user_id: uuid.UUID,
) -> AiPromotionReport:
    report.status = "rejected"
    report.reviewed_by_user_id = admin_user_id
    report.reviewed_at = _utcnow()
    await db.flush()
    return report
