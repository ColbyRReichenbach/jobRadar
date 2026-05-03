"""Lineage and quality reporting for Radar outputs."""

from __future__ import annotations

import uuid
import json
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    AiArtifact,
    AiModelCall,
    ResearchEvidenceItem,
    ResearchProfile,
    ResearchReport,
    ResearchRun,
    ResearchRunStep,
    ResearchSourceItem,
)
from backend.services.ai_artifacts import record_ai_artifact
from backend.services.ai_usage import sanitize_metadata
from backend.services.reports.report_templates import report_input_from_dict
from backend.services.reports.report_writer import write_report_bundle

FRESH_SOURCE_WINDOW_DAYS = 30
RADAR_REPORT_ARTIFACT_TYPES = ("research_report", "radar_report")
RADAR_LINEAGE_REPORT_TYPE = "radar_lineage"
RADAR_LINEAGE_DATASET_VERSION = "radar-lineage-v1"
RADAR_LINEAGE_PROMPT_VERSION = "deterministic-lineage-v1"


class RadarLineageNotFoundError(ValueError):
    """Raised when a user-scoped Radar run/report cannot be found."""


def _coerce_uuid(value: uuid.UUID | str | None, field_name: str) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    if normalized is None:
        return None
    return normalized.isoformat().replace("+00:00", "Z")


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _truncate(value: str | None, limit: int = 240) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _normalized_url(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).strip().lower().rstrip("/") or None


def _domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.lower() or parsed.path.lower() or None


def _unique_text(values: Iterable[str | None], *, limit: int = 20) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        cleaned = " ".join(str(value).split())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _duration_seconds(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    start = _utc(started_at)
    end = _utc(completed_at)
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds(), 3)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def _verification_counts(report: ResearchReport, evidence_items: list[ResearchEvidenceItem]) -> tuple[int, int]:
    structured = report.structured_json if isinstance(report.structured_json, dict) else {}
    verification = structured.get("verification") if isinstance(structured.get("verification"), dict) else {}
    unsupported_count = verification.get("unsupported_claim_count")
    claim_count = verification.get("claim_count")
    if isinstance(unsupported_count, int) and isinstance(claim_count, int) and claim_count >= 0:
        return unsupported_count, claim_count

    unsupported_statuses = {"unsupported", "unverified", "false", "hallucinated", "contradicted"}
    unsupported = 0
    for item in evidence_items:
        metadata = item.structured_json if isinstance(item.structured_json, dict) else {}
        status = str(
            metadata.get("support_status")
            or metadata.get("verification_status")
            or metadata.get("claim_support")
            or ""
        ).lower()
        if status in unsupported_statuses:
            unsupported += 1
    return unsupported, len(evidence_items)


def compute_radar_quality_metrics(
    *,
    report: ResearchReport,
    run: ResearchRun | None,
    evidence_items: list[ResearchEvidenceItem],
    source_items: list[ResearchSourceItem],
    steps: list[ResearchRunStep],
    model_calls: list[AiModelCall],
    as_of: datetime | None = None,
    fresh_source_window_days: int = FRESH_SOURCE_WINDOW_DAYS,
) -> dict[str, Any]:
    """Compute deterministic Radar quality, lineage, and cost metrics."""

    generated_at = _utc(as_of) or _utc(report.report_date) or datetime.now(timezone.utc)
    freshness_cutoff = generated_at - timedelta(days=fresh_source_window_days)

    source_urls = [_normalized_url(item.source_url) for item in source_items]
    source_urls = [item for item in source_urls if item]
    unique_source_urls = set(source_urls)
    duplicate_source_url_count = max(len(source_urls) - len(unique_source_urls), 0)

    source_dates = [_utc(item.published_at) or _utc(item.fetched_at) for item in source_items]
    fresh_source_count = sum(1 for item in source_dates if item is not None and item >= freshness_cutoff)
    stale_source_count = max(len(source_items) - fresh_source_count, 0)

    source_item_ids = {item.id for item in source_items}
    covered_evidence_count = sum(
        1
        for item in evidence_items
        if item.source_item_id in source_item_ids or bool(_normalized_url(item.url))
    )

    unsupported_claim_count, claim_count = _verification_counts(report, evidence_items)
    step_durations = [
        duration
        for duration in (_duration_seconds(step.started_at, step.completed_at) for step in steps)
        if duration is not None
    ]
    linked_model_cost_cents = sum(call.cost_estimate_cents or 0 for call in model_calls)
    run_cost_cents = run.cost_estimate_cents or 0 if run else 0
    effective_cost_cents = linked_model_cost_cents or run_cost_cents

    return {
        "report_id": str(report.id),
        "run_id": str(run.id) if run else None,
        "source_count": len(source_items),
        "evidence_count": len(evidence_items),
        "unique_source_url_count": len(unique_source_urls),
        "duplicate_source_url_count": duplicate_source_url_count,
        "duplicate_source_url_rate": _rate(duplicate_source_url_count, len(source_urls)),
        "fresh_source_count": fresh_source_count,
        "stale_source_count": stale_source_count,
        "source_freshness_window_days": fresh_source_window_days,
        "source_freshness_rate": _rate(fresh_source_count, len(source_items)),
        "covered_evidence_count": covered_evidence_count,
        "source_coverage_rate": _rate(covered_evidence_count, len(evidence_items)),
        "unsupported_claim_count": unsupported_claim_count,
        "claim_count": claim_count,
        "unsupported_claim_rate": _rate(unsupported_claim_count, claim_count),
        "run_llm_call_count": run.llm_call_count or 0 if run else 0,
        "linked_model_call_count": len(model_calls),
        "successful_run_step_count": sum(1 for step in steps if step.status == "succeeded"),
        "failed_run_step_count": sum(1 for step in steps if step.status == "failed"),
        "run_token_input_count": run.tokens_in or 0 if run else 0,
        "run_token_output_count": run.tokens_out or 0 if run else 0,
        "linked_prompt_token_count": sum(call.prompt_tokens or 0 for call in model_calls),
        "linked_output_token_count": sum(call.output_tokens or 0 for call in model_calls),
        "run_cost_estimate_cents": run_cost_cents,
        "linked_model_call_cost_cents": linked_model_cost_cents,
        "effective_cost_per_report_cents": effective_cost_cents,
        "projected_cost_per_1000_reports_cents": effective_cost_cents * 1_000,
        "total_run_duration_seconds": _duration_seconds(run.started_at, run.completed_at) if run else None,
        "mean_step_duration_seconds": round(mean(step_durations), 3) if step_durations else None,
        "p95_step_duration_seconds": _percentile(step_durations, 0.95),
    }


def _serialize_report(report: ResearchReport) -> dict[str, Any]:
    return {
        "id": str(report.id),
        "profile_id": str(report.profile_id) if report.profile_id else None,
        "run_id": str(report.run_id) if report.run_id else None,
        "title": report.title,
        "status": report.status,
        "report_date": _iso(report.report_date),
        "finding_count": report.finding_count,
        "source_count": report.source_count,
        "overall_confidence": report.overall_confidence,
    }


def _serialize_run(run: ResearchRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "id": str(run.id),
        "profile_id": str(run.profile_id),
        "run_type": run.run_type,
        "mode": run.mode,
        "status": run.status,
        "orchestrator_version": run.orchestrator_version,
        "started_at": _iso(run.started_at),
        "completed_at": _iso(run.completed_at),
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "llm_call_count": run.llm_call_count,
        "cost_estimate_cents": run.cost_estimate_cents,
    }


def _serialize_profile(profile: ResearchProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "id": str(profile.id),
        "name": profile.name,
        "mode": profile.mode,
        "frequency": profile.frequency,
        "selected_domains": profile.selected_domains or [],
        "selected_roles": profile.selected_roles or [],
        "selected_companies": profile.selected_companies or [],
        "keywords": profile.keywords or [],
    }


def _serialize_source(item: ResearchSourceItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "run_id": str(item.run_id) if item.run_id else None,
        "profile_id": str(item.profile_id) if item.profile_id else None,
        "source_type": item.source_type,
        "source_name": item.source_name,
        "source_url": item.source_url,
        "domain": _domain(item.source_url),
        "title": _truncate(item.title),
        "published_at": _iso(item.published_at),
        "fetched_at": _iso(item.fetched_at),
        "content_hash_prefix": item.content_hash[:12] if item.content_hash else None,
    }


def _serialize_evidence(item: ResearchEvidenceItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "run_id": str(item.run_id) if item.run_id else None,
        "report_id": str(item.report_id) if item.report_id else None,
        "source_item_id": str(item.source_item_id) if item.source_item_id else None,
        "evidence_type": item.evidence_type,
        "title": _truncate(item.title),
        "claim": _truncate(item.claim),
        "url": item.url,
        "domain": item.domain or _domain(item.url),
        "company_name": item.company_name,
        "role_title": item.role_title,
        "published_at": _iso(item.published_at),
        "confidence": item.confidence,
        "relevance_score": item.relevance_score,
    }


def _serialize_step(step: ResearchRunStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "run_id": str(step.run_id),
        "step_name": step.step_name,
        "step_order": step.step_order,
        "status": step.status,
        "model_name": step.model_name,
        "prompt_version": step.prompt_version,
        "tool_name": step.tool_name,
        "tokens_in": step.tokens_in,
        "tokens_out": step.tokens_out,
        "cost_estimate_cents": step.cost_estimate_cents,
        "duration_seconds": _duration_seconds(step.started_at, step.completed_at),
    }


def _serialize_model_call(call: AiModelCall) -> dict[str, Any]:
    return {
        "id": str(call.id),
        "surface": call.surface,
        "task_name": call.task_name,
        "provider": call.provider,
        "model": call.model,
        "prompt_version": call.prompt_version,
        "variant": call.variant,
        "status": call.status,
        "prompt_tokens": call.prompt_tokens,
        "output_tokens": call.output_tokens,
        "total_tokens": call.total_tokens,
        "cost_estimate_cents": call.cost_estimate_cents,
        "latency_ms": call.latency_ms,
        "created_at": _iso(call.created_at),
    }


def _serialize_artifact(artifact: AiArtifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "model_call_id": str(artifact.model_call_id) if artifact.model_call_id else None,
        "artifact_type": artifact.artifact_type,
        "artifact_ref_id": str(artifact.artifact_ref_id) if artifact.artifact_ref_id else None,
        "title": artifact.title,
        "path": artifact.path,
        "metadata": sanitize_metadata(artifact.metadata_json),
        "created_at": _iso(artifact.created_at),
    }


async def collect_radar_lineage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | str,
    report_id: uuid.UUID | str | None = None,
    run_id: uuid.UUID | str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Return a sanitized, user-scoped Radar lineage payload."""

    uid = _coerce_uuid(user_id, "user_id")
    rid = _coerce_uuid(report_id, "report_id")
    run_uuid = _coerce_uuid(run_id, "run_id")
    if uid is None:
        raise ValueError("user_id is required")
    if rid is None and run_uuid is None:
        raise ValueError("report_id or run_id is required")

    report_stmt = select(ResearchReport).where(ResearchReport.user_id == uid)
    if rid is not None:
        report_stmt = report_stmt.where(ResearchReport.id == rid)
    if run_uuid is not None:
        report_stmt = report_stmt.where(ResearchReport.run_id == run_uuid)
    report = (await db.execute(report_stmt.order_by(ResearchReport.report_date.desc()))).scalars().first()
    if report is None:
        raise RadarLineageNotFoundError("Radar report not found for user")

    run: ResearchRun | None = None
    if report.run_id:
        run = (
            await db.execute(
                select(ResearchRun).where(ResearchRun.id == report.run_id, ResearchRun.user_id == uid)
            )
        ).scalars().first()
    if run is None and run_uuid is not None:
        run = (
            await db.execute(select(ResearchRun).where(ResearchRun.id == run_uuid, ResearchRun.user_id == uid))
        ).scalars().first()

    profile = None
    if report.profile_id:
        profile = (
            await db.execute(
                select(ResearchProfile).where(ResearchProfile.id == report.profile_id, ResearchProfile.user_id == uid)
            )
        ).scalars().first()

    evidence_items = list(
        (
            await db.execute(
                select(ResearchEvidenceItem)
                .where(ResearchEvidenceItem.user_id == uid, ResearchEvidenceItem.report_id == report.id)
                .order_by(ResearchEvidenceItem.created_at.asc())
            )
        ).scalars()
    )

    source_ids = {item.source_item_id for item in evidence_items if item.source_item_id is not None}
    source_filters = []
    if run is not None:
        source_filters.append(ResearchSourceItem.run_id == run.id)
    if source_ids:
        source_filters.append(ResearchSourceItem.id.in_(source_ids))
    source_items: list[ResearchSourceItem] = []
    if source_filters:
        source_items = list(
            (
                await db.execute(
                    select(ResearchSourceItem)
                    .where(ResearchSourceItem.user_id == uid, or_(*source_filters))
                    .order_by(ResearchSourceItem.fetched_at.asc())
                )
            ).scalars()
        )

    steps: list[ResearchRunStep] = []
    if run is not None:
        steps = list(
            (
                await db.execute(
                    select(ResearchRunStep)
                    .where(ResearchRunStep.user_id == uid, ResearchRunStep.run_id == run.id)
                    .order_by(ResearchRunStep.step_order.asc())
                )
            ).scalars()
        )

    artifacts = list(
        (
            await db.execute(
                select(AiArtifact)
                .where(
                    AiArtifact.user_id == uid,
                    AiArtifact.artifact_ref_id == report.id,
                    AiArtifact.artifact_type.in_(RADAR_REPORT_ARTIFACT_TYPES),
                )
                .order_by(AiArtifact.created_at.asc())
            )
        ).scalars()
    )
    model_call_ids = [artifact.model_call_id for artifact in artifacts if artifact.model_call_id is not None]
    model_calls: list[AiModelCall] = []
    if model_call_ids:
        model_calls = list(
            (
                await db.execute(
                    select(AiModelCall)
                    .where(AiModelCall.user_id == uid, AiModelCall.id.in_(model_call_ids))
                    .order_by(AiModelCall.created_at.asc())
                )
            ).scalars()
        )

    metrics = compute_radar_quality_metrics(
        report=report,
        run=run,
        evidence_items=evidence_items,
        source_items=source_items,
        steps=steps,
        model_calls=model_calls,
        as_of=as_of,
    )

    return {
        "generated_at": _iso(_utc(as_of) or datetime.now(timezone.utc)),
        "user_id": str(uid),
        "report": _serialize_report(report),
        "run": _serialize_run(run),
        "profile": _serialize_profile(profile),
        "quality_metrics": metrics,
        "sources": [_serialize_source(item) for item in source_items],
        "evidence": [_serialize_evidence(item) for item in evidence_items],
        "steps": [_serialize_step(step) for step in steps],
        "artifacts": [_serialize_artifact(artifact) for artifact in artifacts],
        "model_calls": [_serialize_model_call(call) for call in model_calls],
    }


async def record_radar_report_artifact(
    db: AsyncSession,
    *,
    report: ResearchReport,
    run: ResearchRun | None = None,
    model_call_id: uuid.UUID | str | None = None,
    path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AiArtifact:
    """Record an idempotent artifact row for a generated Radar report."""

    call_uuid = _coerce_uuid(model_call_id, "model_call_id")
    model_call = None
    if call_uuid is not None:
        model_call = (
            await db.execute(
                select(AiModelCall).where(AiModelCall.id == call_uuid, AiModelCall.user_id == report.user_id)
            )
        ).scalars().first()
        if model_call is None:
            raise RadarLineageNotFoundError("Model call not found for Radar report user")

    if run is None and report.run_id:
        run = (
            await db.execute(
                select(ResearchRun).where(ResearchRun.id == report.run_id, ResearchRun.user_id == report.user_id)
            )
        ).scalars().first()

    profile = None
    if report.profile_id:
        profile = (
            await db.execute(
                select(ResearchProfile).where(
                    ResearchProfile.id == report.profile_id,
                    ResearchProfile.user_id == report.user_id,
                )
            )
        ).scalars().first()

    evidence_items = list(
        (
            await db.execute(
                select(ResearchEvidenceItem).where(
                    ResearchEvidenceItem.user_id == report.user_id,
                    ResearchEvidenceItem.report_id == report.id,
                )
            )
        ).scalars()
    )

    existing_stmt = select(AiArtifact).where(
        AiArtifact.user_id == report.user_id,
        AiArtifact.artifact_type == "research_report",
        AiArtifact.artifact_ref_id == report.id,
    )
    if call_uuid is None:
        existing_stmt = existing_stmt.where(AiArtifact.model_call_id.is_(None))
    else:
        existing_stmt = existing_stmt.where(AiArtifact.model_call_id == call_uuid)
    existing = (await db.execute(existing_stmt)).scalars().first()
    if existing:
        return existing

    role_area = _unique_text(
        [
            *(profile.selected_roles if profile and profile.selected_roles else []),
            *(item.role_title for item in evidence_items),
        ],
        limit=10,
    )
    companies = _unique_text(
        [
            *(profile.selected_companies if profile and profile.selected_companies else []),
            *(item.company_name for item in evidence_items),
        ],
        limit=10,
    )
    topics = _unique_text(
        [
            *(profile.selected_domains if profile and profile.selected_domains else []),
            *(profile.keywords if profile and profile.keywords else []),
            *(item.domain for item in evidence_items),
        ],
        limit=20,
    )

    artifact_metadata = {
        "research_run_id": str(run.id) if run else None,
        "research_profile_id": str(report.profile_id) if report.profile_id else None,
        "generated_at": _iso(report.report_date),
        "company_names": companies,
        "role_area": role_area,
        "topics": topics,
        "model": model_call.model if model_call else None,
        "prompt_version": model_call.prompt_version if model_call else None,
        "cost_estimate_cents": (
            model_call.cost_estimate_cents if model_call and model_call.cost_estimate_cents is not None else run.cost_estimate_cents if run else None
        ),
        "source_count": report.source_count,
        "finding_count": report.finding_count,
        "report_status": report.status,
        **(metadata or {}),
    }

    return await record_ai_artifact(
        db,
        artifact_type="research_report",
        user_id=report.user_id,
        model_call_id=call_uuid,
        artifact_ref_id=report.id,
        title=report.title,
        path=path,
        metadata=artifact_metadata,
    )


def build_radar_lineage_report_input(
    lineage: dict[str, Any],
    *,
    generated_at: datetime,
    git_sha: str,
    release_version: str = "local",
    recommendation: str = "review",
    decision: str = "pending_admin_review",
    ai_summary: str | None = None,
) -> dict[str, Any]:
    """Build structured input for the immutable report writer."""

    metrics = dict(lineage["quality_metrics"])
    run = lineage.get("run") or {}
    model_calls = lineage.get("model_calls") or []
    step_models = [step.get("model_name") for step in lineage.get("steps") or [] if step.get("model_name")]
    models = _unique_text([*(call.get("model") for call in model_calls), *step_models], limit=5)
    prompts = _unique_text(
        [
            *(call.get("prompt_version") for call in model_calls),
            *(step.get("prompt_version") for step in lineage.get("steps") or [] if step.get("prompt_version")),
        ],
        limit=5,
    )
    metrics["contributing_model_names"] = models
    metrics["contributing_prompt_versions"] = prompts
    dataset_version = f"{RADAR_LINEAGE_DATASET_VERSION}-{str(metrics.get('run_id') or metrics.get('report_id'))[:8]}"

    return {
        "metadata": {
            "report_type": RADAR_LINEAGE_REPORT_TYPE,
            "title": f"Radar Lineage Report - {lineage['report']['title']}",
            "generated_at": _iso(generated_at),
            "git_sha": git_sha,
            "release_version": release_version,
            "dataset_version": dataset_version,
            "model": ", ".join(models) if models else "deterministic",
            "prompt_version": RADAR_LINEAGE_PROMPT_VERSION,
            "recommendation": recommendation,
            "decision": decision,
        },
        "metrics": metrics,
        "token_breakdown": {
            "run_tokens_in": run.get("tokens_in") or 0,
            "run_tokens_out": run.get("tokens_out") or 0,
            "linked_prompt_tokens": metrics["linked_prompt_token_count"],
            "linked_output_tokens": metrics["linked_output_token_count"],
            "linked_total_tokens": sum(call.get("total_tokens") or 0 for call in model_calls),
        },
        "cost_breakdown": {
            "run_cost_estimate_cents": metrics["run_cost_estimate_cents"],
            "linked_model_call_cost_cents": metrics["linked_model_call_cost_cents"],
            "effective_cost_per_report_cents": metrics["effective_cost_per_report_cents"],
            "projected_cost_per_1000_reports_cents": metrics["projected_cost_per_1000_reports_cents"],
        },
        "latency_metrics": {
            "total_run_duration_seconds": metrics["total_run_duration_seconds"],
            "mean_step_duration_seconds": metrics["mean_step_duration_seconds"],
            "p95_step_duration_seconds": metrics["p95_step_duration_seconds"],
        },
        "supporting_artifacts": [
            {"label": "Radar lineage source payload", "path": "lineage_payload.json"},
        ],
        "notes": [
            "Lineage payload omits raw source text and raw model prompts/responses.",
            "Cost uses linked ledger calls when available, otherwise the Radar run aggregate estimate.",
            "Unsupported-claim rate uses explicit verification counts when present.",
        ],
        "ai_summary": ai_summary,
    }


def write_radar_lineage_report_bundle(
    lineage: dict[str, Any],
    output_dir: str,
    *,
    generated_at: datetime,
    git_sha: str,
    release_version: str = "local",
    overwrite: bool = False,
    ai_summary: str | None = None,
) -> str:
    report_payload = build_radar_lineage_report_input(
        lineage,
        generated_at=generated_at,
        git_sha=git_sha,
        release_version=release_version,
        ai_summary=ai_summary,
    )
    report = report_input_from_dict(report_payload)
    target_dir = write_report_bundle(report, output_dir, overwrite=overwrite)
    (target_dir / "lineage_payload.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(target_dir)
