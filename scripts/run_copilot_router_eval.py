#!/usr/bin/env python3
"""Run Copilot route-intent artifact eval."""

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
from backend.services.evals.copilot_router_eval import run_copilot_router_eval


def build_artifact_payload(eval_result: dict[str, Any]) -> dict[str, Any]:
    candidate = eval_result["candidate"]
    baseline = eval_result["baseline"]
    metrics = {
        **candidate["metrics"],
        "baseline_route_accuracy": baseline["metrics"]["route_accuracy"],
        "baseline_missing_route_rate": baseline["metrics"]["missing_route_rate"],
    }
    message_count = candidate["metrics"]["case_count"]
    return {
        "metadata": {
            "report_type": "copilot-router-eval",
            "title": "Copilot Router Artifact Eval",
            "generated_at": utc_now_iso(),
            "git_sha": current_git_sha(),
            "release_version": "feature-artifacts",
            "dataset_version": eval_result["dataset_version"],
            "model": "deterministic-router",
            "prompt_version": "route-rules-v1",
            "recommendation": "ship_router_behind_flag_for_internal_testing",
            "decision": "baseline_artifact_ready",
        },
        "metrics": metrics,
        "token_breakdown": {
            "route_model_calls": 0,
            "answer_model_calls": 0,
            "evidence_status": "deterministic_router_fixture_eval",
        },
        "cost_breakdown": {
            "total_cost_cents": 0,
            "cost_per_case_cents": 0,
        },
        "latency_metrics": {},
        "case_results": candidate["case_results"],
        "failure_summary": eval_result["failure_summary"],
        "cost_projection": {
            "feature": "copilot_router",
            "period": "per_dataset_scaled",
            "evidence_status": "fixture_projection",
            "baseline": {
                "messages": message_count,
                "generic_answer_call_rate": 1.0,
                "route_model_call_rate": 0.0,
                "estimated_total_cost_cents": 0.0,
            },
            "candidate": {
                "messages": message_count,
                "generic_answer_call_rate": 0.0,
                "route_model_call_rate": 0.0,
                "estimated_total_cost_cents": 0.0,
            },
            "delta": {
                "generic_answers_avoided": message_count,
                "cost_delta_cents": 0.0,
            },
        },
        "supporting_artifacts": [
            {"label": "Copilot router eval dataset", "path": eval_result["dataset_path"]},
            {"label": "Copilot failure taxonomy", "path": "evals/copilot/failure-taxonomy.md"},
            {"label": "Feature changelog", "path": "docs/ai-artifacts/feature-changelogs/copilot-routing-changelog.md"},
        ],
        "notes": [
            eval_result["decision_note"],
            "Candidate route rules are deterministic eval logic; product route execution still needs backend integration before user-visible rollout.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evals/copilot/copilot_router_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/ai-artifacts/generated"))
    parser.add_argument("--payload-output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    eval_result = run_copilot_router_eval(args.dataset)
    payload = build_artifact_payload(eval_result)
    if args.payload_output:
        args.payload_output.parent.mkdir(parents=True, exist_ok=True)
        args.payload_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = write_feature_artifact_bundle(payload, args.output_dir, overwrite=args.overwrite)
    print(output)


if __name__ == "__main__":
    main()
