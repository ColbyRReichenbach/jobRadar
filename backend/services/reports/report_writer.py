"""Write immutable, reproducible AI report artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.services.reports.report_templates import (
    ReportInput,
    generated_date,
    render_artifact_links,
    render_key_value_table,
    report_input_from_dict,
    slugify,
)
from backend.services.reports.summary_writer import build_summary_payload, render_summary_section


def render_report_markdown(report: ReportInput) -> str:
    metadata = report.metadata
    sections = [
        f"# {metadata.title}",
        "",
        "## Metadata",
        "",
        render_key_value_table(asdict(metadata)),
        "",
        render_summary_section(report),
        "",
        "## Primary Metrics",
        "",
        render_key_value_table(report.metrics),
        "",
        "## Token Breakdown",
        "",
        render_key_value_table(report.token_breakdown),
        "",
        "## Cost Breakdown",
        "",
        render_key_value_table(report.cost_breakdown),
        "",
        "## Latency Metrics",
        "",
        render_key_value_table(report.latency_metrics),
        "",
        "## Supporting Artifacts",
        "",
        render_artifact_links(report.supporting_artifacts),
        "",
        "## Notes",
        "",
        "\n".join(f"- {note}" for note in report.notes) if report.notes else "No notes provided.",
        "",
        "## Decision",
        "",
        f"- Recommendation: {metadata.recommendation}",
        f"- Decision: {metadata.decision}",
    ]
    return "\n".join(sections).rstrip() + "\n"


def output_folder_name(report: ReportInput) -> str:
    metadata = report.metadata
    return "_".join(
        [
            generated_date(metadata),
            slugify(metadata.report_type),
            slugify(metadata.dataset_version),
            slugify(metadata.model),
            slugify(metadata.prompt_version),
        ]
    )


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_report_bundle(report: ReportInput, output_dir: Path | str, *, overwrite: bool = False) -> Path:
    base_dir = Path(output_dir)
    target_dir = base_dir / output_folder_name(report)
    if target_dir.exists() and not overwrite:
        raise FileExistsError(f"Report output already exists: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "report.md").write_text(render_report_markdown(report), encoding="utf-8")
    write_json(target_dir / "metadata.json", asdict(report.metadata))
    write_json(target_dir / "metrics.json", report.metrics)
    write_json(target_dir / "token_breakdown.json", report.token_breakdown)
    write_json(target_dir / "cost_breakdown.json", report.cost_breakdown)
    write_json(target_dir / "latency_metrics.json", report.latency_metrics)
    write_json(target_dir / "summary_payload.json", build_summary_payload(report))
    write_json(
        target_dir / "source_input.json",
        {
            "metadata": asdict(report.metadata),
            "metrics": report.metrics,
            "token_breakdown": report.token_breakdown,
            "cost_breakdown": report.cost_breakdown,
            "latency_metrics": report.latency_metrics,
            "supporting_artifacts": [asdict(artifact) for artifact in report.supporting_artifacts],
            "notes": report.notes,
            "ai_summary": report.ai_summary,
        },
    )
    return target_dir


def write_report_from_json(input_path: Path | str, output_dir: Path | str, *, overwrite: bool = False) -> Path:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    return write_report_bundle(report_input_from_dict(payload), output_dir, overwrite=overwrite)
