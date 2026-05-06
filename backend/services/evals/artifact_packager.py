"""Standardized feature eval artifact bundle writer."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.reports.report_templates import report_input_from_dict
from backend.services.reports.report_writer import write_json, write_report_bundle


def current_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_ready(value: Any) -> Any:
    json.dumps(value, default=str)
    return value


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")


def normalize_feature_artifact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") or {})
    generated_at = metadata.get("generated_at") or utc_now_iso()
    metadata.setdefault("generated_at", generated_at)
    metadata.setdefault("git_sha", current_git_sha())
    metadata.setdefault("release_version", "local-feature-artifacts")
    metadata.setdefault("recommendation", "review_artifact")
    metadata.setdefault("decision", "needs_review")

    required = {
        "report_type",
        "title",
        "dataset_version",
        "model",
        "prompt_version",
    }
    missing = sorted(key for key in required if not str(metadata.get(key) or "").strip())
    if missing:
        raise ValueError(f"metadata missing required fields: {', '.join(missing)}")

    report_payload = {
        "metadata": metadata,
        "metrics": dict(payload.get("metrics") or {}),
        "token_breakdown": dict(payload.get("token_breakdown") or {}),
        "cost_breakdown": dict(payload.get("cost_breakdown") or {}),
        "latency_metrics": dict(payload.get("latency_metrics") or {}),
        "supporting_artifacts": list(payload.get("supporting_artifacts") or []),
        "notes": list(payload.get("notes") or []),
    }
    if payload.get("ai_summary"):
        report_payload["ai_summary"] = str(payload["ai_summary"])

    return {
        "report": report_payload,
        "case_results": list(payload.get("case_results") or []),
        "failure_summary": dict(payload.get("failure_summary") or {}),
        "cost_projection": dict(payload.get("cost_projection") or {}),
        "source_input_extra": dict(payload.get("source_input_extra") or {}),
    }


def write_feature_artifact_bundle(
    payload: dict[str, Any],
    output_dir: Path | str,
    *,
    overwrite: bool = False,
) -> Path:
    normalized = normalize_feature_artifact_payload(payload)
    report = report_input_from_dict(normalized["report"])
    target_dir = write_report_bundle(report, output_dir, overwrite=overwrite)

    case_results = [_json_ready(row) for row in normalized["case_results"]]
    failure_summary = _json_ready(normalized["failure_summary"])
    cost_projection = _json_ready(normalized["cost_projection"])
    source_extra = _json_ready(normalized["source_input_extra"])

    _write_jsonl(target_dir / "case_results.jsonl", case_results)
    write_json(target_dir / "failure_summary.json", failure_summary)
    write_json(target_dir / "cost_projection.json", cost_projection)
    write_json(
        target_dir / "feature_artifact_source.json",
        {
            "report_source": normalized["report"],
            "case_result_count": len(case_results),
            "failure_summary": failure_summary,
            "cost_projection": cost_projection,
            "source_input_extra": source_extra,
        },
    )
    return target_dir


def load_payload(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
