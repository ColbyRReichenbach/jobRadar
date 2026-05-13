#!/usr/bin/env python3
"""Run Gmail classifier LLM preflight safety eval."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.artifact_packager import current_git_sha, utc_now_iso, write_feature_artifact_bundle
from backend.services.evals.gmail_preflight_eval import run_preflight_eval


def build_artifact_payload(*, dataset_path: Path, result: dict[str, Any] | None = None) -> dict[str, Any]:
    result = result or run_preflight_eval(dataset_path)
    metrics = result["metrics"]
    return {
        "metadata": {
            "report_type": "gmail-classifier-llm-preflight-eval",
            "title": "Gmail Classifier LLM Preflight Eval",
            "generated_at": utc_now_iso(),
            "git_sha": current_git_sha(),
            "release_version": "feature-artifacts",
            "dataset_version": result["dataset_version"],
            "model": "no-model-preflight",
            "prompt_version": "classifier-thresholds-v1",
            "recommendation": "require_preflight_before_real_gmail_llm_calls",
            "decision": "preflight_ready_for_real_gmail_dry_run" if metrics["pass_rate"] == 1.0 else "preflight_needs_fixes",
        },
        "metrics": {
            "case_count": metrics["case_count"],
            "pass_rate": metrics["pass_rate"],
            "failed_case_count": metrics["failed_case_count"],
            "expected_llm_escalation_rate": metrics["expected_llm_escalation_rate"],
            "actual_llm_escalation_rate": metrics["actual_llm_escalation_rate"],
            "expected_block_rate": metrics["expected_block_rate"],
            "actual_block_rate": metrics["actual_block_rate"],
            "prompt_leak_rate": metrics["prompt_leak_rate"],
            "redaction_pass_rate": metrics["redaction_pass_rate"],
            "prompt_injection_block_rate": metrics["prompt_injection_block_rate"],
            "model_call_count": metrics["model_call_count"],
        },
        "token_breakdown": {
            "live_model_calls": 0,
            "prompt_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "evidence_status": "preflight_no_model_calls",
        },
        "cost_breakdown": {
            "total_cost_cents": 0,
            "cost_per_1000_emails_cents": 0,
        },
        "latency_metrics": {},
        "case_results": result["case_results"],
        "failure_summary": result["failure_summary"],
        "cost_projection": {
            "feature": "gmail_classifier_llm_preflight",
            "period": "per_eval_run",
            "model_calls": 0,
            "estimated_total_cost_cents": 0,
            "evidence_status": "preflight_no_model_calls",
        },
        "supporting_artifacts": [
            {"label": "Preflight synthetic dataset", "path": str(dataset_path)},
            {"label": "Feature changelog", "path": "docs/ai-artifacts/feature-changelogs/gmail-classifier-changelog.md"},
            {"label": "Dataset governance", "path": "evals/dataset-governance.md"},
        ],
        "notes": [
            "This artifact does not call an LLM. It verifies whether real Gmail content would be blocked, redacted, or minimized before any possible classifier adjudication call.",
            "The preflight gate is specific to Gmail classification: no tools, no browsing, no database mutation, one bounded JSON classification task only.",
            "A redacted_prompt_review.md file is emitted next to case_results.jsonl so the exact would-be LLM payload can be inspected without opening raw fixture data.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evals/email_classifier/gmail_llm_preflight_synthetic_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/ai-artifacts/generated"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    result = run_preflight_eval(args.dataset)
    payload = build_artifact_payload(dataset_path=args.dataset, result=result)
    output = write_feature_artifact_bundle(payload, args.output_dir, overwrite=args.overwrite)
    (output / "redacted_prompt_review.md").write_text(
        result["redacted_prompt_review_markdown"],
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
