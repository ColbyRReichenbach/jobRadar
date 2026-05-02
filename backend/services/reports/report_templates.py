"""Deterministic Markdown templates for AI governance reports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

REQUIRED_METADATA_FIELDS = (
    "report_type",
    "title",
    "generated_at",
    "git_sha",
    "release_version",
    "dataset_version",
    "model",
    "prompt_version",
    "recommendation",
    "decision",
)


@dataclass(frozen=True)
class SupportingArtifact:
    label: str
    path: str


@dataclass(frozen=True)
class ReportMetadata:
    report_type: str
    title: str
    generated_at: str
    git_sha: str
    release_version: str
    dataset_version: str
    model: str
    prompt_version: str
    recommendation: str
    decision: str


@dataclass(frozen=True)
class ReportInput:
    metadata: ReportMetadata
    metrics: dict[str, Any]
    token_breakdown: dict[str, Any]
    cost_breakdown: dict[str, Any]
    latency_metrics: dict[str, Any]
    supporting_artifacts: list[SupportingArtifact] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ai_summary: str | None = None


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_text(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"metadata.{key} is required")
    return str(value).strip()


def _validate_iso_datetime(value: str) -> str:
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("metadata.generated_at must be ISO-8601") from exc
    return value


def report_input_from_dict(payload: dict[str, Any]) -> ReportInput:
    source = _require_mapping(payload, "report")
    metadata_payload = _require_mapping(source.get("metadata"), "metadata")
    for field_name in REQUIRED_METADATA_FIELDS:
        _require_text(metadata_payload, field_name)
    metadata = ReportMetadata(
        report_type=_require_text(metadata_payload, "report_type"),
        title=_require_text(metadata_payload, "title"),
        generated_at=_validate_iso_datetime(_require_text(metadata_payload, "generated_at")),
        git_sha=_require_text(metadata_payload, "git_sha"),
        release_version=_require_text(metadata_payload, "release_version"),
        dataset_version=_require_text(metadata_payload, "dataset_version"),
        model=_require_text(metadata_payload, "model"),
        prompt_version=_require_text(metadata_payload, "prompt_version"),
        recommendation=_require_text(metadata_payload, "recommendation"),
        decision=_require_text(metadata_payload, "decision"),
    )

    artifacts = []
    for item in source.get("supporting_artifacts", []) or []:
        if not isinstance(item, dict):
            raise ValueError("supporting_artifacts entries must be objects")
        artifacts.append(
            SupportingArtifact(
                label=_require_text(item, "label"),
                path=_require_text(item, "path"),
            )
        )

    notes = [str(note).strip() for note in (source.get("notes") or []) if str(note).strip()]
    ai_summary = source.get("ai_summary")
    if ai_summary is not None:
        ai_summary = str(ai_summary).strip() or None

    return ReportInput(
        metadata=metadata,
        metrics=_require_mapping(source.get("metrics"), "metrics"),
        token_breakdown=_require_mapping(source.get("token_breakdown"), "token_breakdown"),
        cost_breakdown=_require_mapping(source.get("cost_breakdown"), "cost_breakdown"),
        latency_metrics=_require_mapping(source.get("latency_metrics"), "latency_metrics"),
        supporting_artifacts=artifacts,
        notes=notes,
        ai_summary=ai_summary,
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "report"


def render_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        return "`" + str(value).replace("|", "\\|") + "`"
    return str(value).replace("|", "\\|")


def render_key_value_table(values: dict[str, Any], *, empty_message: str = "No values provided.") -> str:
    if not values:
        return empty_message
    lines = ["| Metric | Value |", "| --- | --- |"]
    for key in sorted(values):
        lines.append(f"| {render_value(key)} | {render_value(values[key])} |")
    return "\n".join(lines)


def render_artifact_links(artifacts: list[SupportingArtifact]) -> str:
    if not artifacts:
        return "No supporting artifacts linked."
    return "\n".join(f"- [{artifact.label}]({artifact.path})" for artifact in artifacts)


def generated_date(metadata: ReportMetadata) -> str:
    parsed = datetime.fromisoformat(metadata.generated_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.date().isoformat()
