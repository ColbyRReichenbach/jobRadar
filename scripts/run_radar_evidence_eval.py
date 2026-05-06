#!/usr/bin/env python3
"""Run Radar evidence-quality artifact eval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.artifact_packager import current_git_sha, utc_now_iso, write_feature_artifact_bundle
from backend.services.evals.radar_evidence_eval import run_radar_evidence_eval


def build_artifact_payload(eval_result: dict[str, Any]) -> dict[str, Any]:
    case_count = eval_result["metrics"]["case_count"]
    return {
        "metadata": {
            "report_type": "radar-evidence-quality-eval",
            "title": "Radar Evidence Quality Artifact Eval",
            "generated_at": utc_now_iso(),
            "git_sha": current_git_sha(),
            "release_version": "feature-artifacts",
            "dataset_version": eval_result["dataset_version"],
            "model": "deterministic-evidence-quality",
            "prompt_version": "source-quality-gate-v1",
            "recommendation": "apply_evidence_quality_gate_before_report_generation",
            "decision": "baseline_artifact_ready",
        },
        "metrics": eval_result["metrics"],
        "token_breakdown": {
            "model_calls": 0,
            "evidence_status": "deterministic_fixture_eval",
        },
        "cost_breakdown": {
            "total_cost_cents": 0,
            "cost_per_case_cents": 0,
        },
        "latency_metrics": {},
        "case_results": eval_result["case_results"],
        "failure_summary": eval_result["failure_summary"],
        "cost_projection": {
            "feature": "radar_evidence_quality",
            "period": "per_dataset_scaled",
            "evidence_status": "fixture_projection",
            "baseline": {
                "cases": case_count,
                "llm_extraction_call_rate": 1.0,
                "estimated_total_cost_cents": 0.0,
            },
            "candidate": {
                "cases": case_count,
                "llm_extraction_call_rate": 0.0,
                "estimated_total_cost_cents": 0.0,
            },
            "delta": {
                "llm_extraction_calls_avoided_for_rejected_sources": sum(
                    1 for item in eval_result["case_results"] if not item["actual_publishable"]
                ),
                "cost_delta_cents": 0.0,
            },
        },
        "supporting_artifacts": [
            {"label": "Radar evidence eval dataset", "path": eval_result["dataset_path"]},
            {"label": "Feature changelog", "path": "docs/interview-artifacts/feature-changelogs/radar-research-changelog.md"},
        ],
        "notes": [
            eval_result["decision_note"],
            "This artifact evaluates deterministic evidence gating, not live Radar report generation.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evals/radar/radar_evidence_quality_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/interview-artifacts/generated"))
    parser.add_argument("--payload-output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    eval_result = run_radar_evidence_eval(args.dataset)
    payload = build_artifact_payload(eval_result)
    if args.payload_output:
        args.payload_output.parent.mkdir(parents=True, exist_ok=True)
        args.payload_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = write_feature_artifact_bundle(payload, args.output_dir, overwrite=args.overwrite)
    print(output)


if __name__ == "__main__":
    main()

