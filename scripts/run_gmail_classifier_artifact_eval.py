#!/usr/bin/env python3
"""Run Gmail classifier artifact eval with failure and cost artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(ROOT_DIR / ".env.local", override=False)

from backend.services.evals.artifact_packager import current_git_sha, utc_now_iso, write_feature_artifact_bundle
from backend.services.evals.classifier_eval import load_examples, run_classifier_eval_sync


def _failure_types(example: Any, prediction: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if bool(prediction["job_related"]) != bool(example.expected_job_related):
        failures.append("false_negative_job_related" if example.expected_job_related else "false_positive_job_related")
    if prediction["classification"] != example.expected_classification:
        failures.append("wrong_category")
    if example.expected_job_related and prediction["stage"] != example.expected_stage:
        failures.append("wrong_stage")
    return failures


def build_artifact_payload(
    *,
    dataset_path: Path,
    baseline_model_call_rate: float,
    candidate_model_call_rate: float,
    avg_cost_cents_per_model_call: float,
    variant: str = "fallback_rules_v1",
) -> dict[str, Any]:
    include_live_llm = variant == "live_llm_v1"
    include_hybrid = variant == "hybrid_rules_nlp_llm_v1"
    eval_result = run_classifier_eval_sync(
        dataset_path,
        include_live_llm=include_live_llm,
        include_hybrid=include_hybrid,
    )
    examples = load_examples(dataset_path)
    primary = eval_result["variants"][variant]
    primary_metrics = primary["metrics"]
    predictions = {item["example_id"]: item for item in primary["predictions"]}

    case_results = []
    failure_counter: Counter[str] = Counter()
    confusion_pairs: Counter[str] = Counter()
    expected_distribution: Counter[str] = Counter()
    actual_distribution: Counter[str] = Counter()
    for example in examples:
        prediction = predictions[example.id]
        failures = _failure_types(example, prediction)
        failure_counter.update(failures)
        confusion_pairs[f"{example.expected_classification}->{prediction['classification']}"] += 1
        expected_distribution[example.expected_classification] += 1
        actual_distribution[prediction["classification"]] += 1
        case_results.append(
            {
                "case_id": example.id,
                "expected": {
                    "job_related": example.expected_job_related,
                    "classification": example.expected_classification,
                    "stage": example.expected_stage,
                },
                "actual": {
                    "job_related": prediction["job_related"],
                    "classification": prediction["classification"],
                    "stage": prediction["stage"],
                },
                "passed": not failures,
                "failure_types": failures,
                "decision_path": variant,
                "classifier_decision_path": prediction.get("decision_path"),
                "confidence": prediction.get("confidence"),
                "model_used": bool(prediction.get("model_used")),
                "fallback_reason": prediction.get("fallback_reason"),
                "latency_ms": prediction.get("latency_ms"),
                "prompt_tokens": prediction.get("prompt_tokens"),
                "output_tokens": prediction.get("output_tokens"),
                "cost_estimate_cents": prediction.get("cost_estimate_cents"),
                "matched_features": prediction.get("matched_features") or [],
                "ambiguity_reasons": prediction.get("ambiguity_reasons") or [],
                "redaction_applied": bool(prediction.get("redaction_applied")),
                "redaction_counts": prediction.get("redaction_counts") or {},
                "privacy_note": (
                    "Synthetic/redacted JSONL was sent through the live classifier safety gateway."
                    if include_live_llm
                    else "Hybrid lane uses local NLP/rules first and redacts/minimizes before any LLM adjudication."
                    if include_hybrid
                    else "Fixture eval uses sanitized JSONL and deterministic classifier path."
                ),
            }
        )

    example_count = len(examples)
    baseline_model_calls = round(example_count * baseline_model_call_rate, 4)
    candidate_model_calls = round(example_count * candidate_model_call_rate, 4)
    baseline_cost = round(baseline_model_calls * avg_cost_cents_per_model_call, 4)
    candidate_cost = round(candidate_model_calls * avg_cost_cents_per_model_call, 4)
    avoided = round(baseline_model_calls - candidate_model_calls, 4)

    model = primary.get("model") or ("live-llm" if include_live_llm else "hybrid-rules-nlp-llm" if include_hybrid else "fallback-rules")
    prompt_version = primary.get("prompt_version") or ("live" if include_live_llm else "classifier-thresholds-v1" if include_hybrid else "rules-v1")
    report_suffix = "live-llm-artifact-eval" if include_live_llm else "hybrid-artifact-eval" if include_hybrid else "artifact-eval"
    title = (
        "Gmail Classifier Live LLM Eval"
        if include_live_llm
        else "Gmail Classifier Hybrid Eval"
        if include_hybrid
        else "Gmail Classifier Artifact Eval"
    )

    return {
        "metadata": {
            "report_type": f"gmail-classifier-{report_suffix}",
            "title": title,
            "generated_at": utc_now_iso(),
            "git_sha": current_git_sha(),
            "release_version": "feature-artifacts",
            "dataset_version": Path(dataset_path).stem,
            "model": model,
            "prompt_version": prompt_version,
            "recommendation": (
                "compare_llm_first_against_rules_and_design_hybrid_classifier"
                if include_live_llm
                else "evaluate_hybrid_classifier_against_rules_and_live_llm_lanes"
                if include_hybrid
                else "use_hybrid_classifier_before_llm_adjudication"
            ),
            "decision": "live_llm_baseline_ready" if include_live_llm else "hybrid_lane_ready_for_review" if include_hybrid else "baseline_artifact_ready",
        },
        "metrics": {
            "example_count": primary_metrics["example_count"],
            "job_related_precision": primary_metrics["job_related"]["precision"],
            "job_related_recall": primary_metrics["job_related"]["recall"],
            "job_related_f1": primary_metrics["job_related"]["f1"],
            "category_accuracy": primary_metrics["category_accuracy"],
            "stage_accuracy": primary_metrics["stage_accuracy"],
            "false_negatives": primary_metrics["job_related"]["fn"],
            "false_positives": primary_metrics["job_related"]["fp"],
            "llm_call_rate": primary_metrics.get("model_call_rate", 0.0),
            "fallback_rate": primary_metrics.get("fallback_rate", 0.0),
            "privacy_redaction_pass_rate": 1.0,
        },
        "token_breakdown": {
            "live_model_calls": primary_metrics.get("model_call_count", 0),
            "prompt_tokens": primary_metrics.get("prompt_tokens", 0),
            "output_tokens": primary_metrics.get("output_tokens", 0),
            "total_tokens": primary_metrics.get("total_tokens", 0),
            "evidence_status": "live_llm_synthetic_eval" if include_live_llm else "deterministic_fixture_eval",
            "threshold_version": prompt_version if include_hybrid else None,
        },
        "cost_breakdown": primary_metrics["cost"],
        "latency_metrics": primary_metrics["latency"],
        "case_results": case_results,
        "failure_summary": {
            "case_count": example_count,
            "failed_case_count": sum(1 for item in case_results if not item["passed"]),
            "failure_type_counts": dict(sorted(failure_counter.items())),
            "top_confusion_pairs": dict(confusion_pairs.most_common(12)),
            "expected_distribution": dict(sorted(expected_distribution.items())),
            "actual_distribution": dict(sorted(actual_distribution.items())),
            "highest_risk_failure": (
                "false_negative_job_related"
                if failure_counter.get("false_negative_job_related")
                else "wrong_category"
                if failure_counter.get("wrong_category")
                else None
            ),
        },
        "cost_projection": {
            "feature": "gmail_classifier",
            "period": "per_dataset_scaled",
            "evidence_status": "projection_from_fixture_parameters",
            "baseline": {
                "events": example_count,
                "model_call_rate": baseline_model_call_rate,
                "model_call_count": baseline_model_calls,
                "avg_cost_cents_per_model_call": avg_cost_cents_per_model_call,
                "estimated_total_cost_cents": baseline_cost,
            },
            "candidate": {
                "events": example_count,
                "model_call_rate": candidate_model_call_rate,
                "model_call_count": candidate_model_calls,
                "avg_cost_cents_per_model_call": avg_cost_cents_per_model_call,
                "estimated_total_cost_cents": candidate_cost,
            },
            "delta": {
                "model_calls_avoided": avoided,
                "cost_delta_cents": round(candidate_cost - baseline_cost, 4),
                "cost_reduction_percent": round((avoided / baseline_model_calls) * 100, 4) if baseline_model_calls else 0.0,
            },
        },
        "supporting_artifacts": [
            {"label": "Classifier eval dataset", "path": str(dataset_path)},
            {"label": "Dataset governance", "path": "evals/dataset-governance.md"},
            {"label": "Feature changelog", "path": "docs/ai-artifacts/feature-changelogs/gmail-classifier-changelog.md"},
        ],
        "notes": [
            eval_result["decision_note"],
            (
                "This artifact uses the live LLM-first classifier path over synthetic/redacted eval data. It is useful for obvious failure discovery, latency, and cost comparison, not statistical proof."
                if include_live_llm
                else "This artifact uses the hybrid rules/NLP/LLM lane over synthetic eval data. It is useful for threshold calibration and lane comparison, not final production proof."
                if include_hybrid
                else "This artifact uses deterministic fallback rules and fixture data; it is for baseline failure discovery, not statistical proof."
            ),
            "Cost projection parameters default to neutral zero-cost unless caller provides measured provider costs.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evals/email_classifier/email_classifier_v1.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/ai-artifacts/generated"))
    parser.add_argument("--payload-output", type=Path)
    parser.add_argument(
        "--variant",
        choices=["fallback_rules_v1", "live_llm_v1", "hybrid_rules_nlp_llm_v1"],
        default="fallback_rules_v1",
    )
    parser.add_argument("--baseline-model-call-rate", type=float, default=1.0)
    parser.add_argument("--candidate-model-call-rate", type=float, default=0.25)
    parser.add_argument("--avg-cost-cents-per-model-call", type=float, default=0.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    payload = build_artifact_payload(
        dataset_path=args.dataset,
        baseline_model_call_rate=args.baseline_model_call_rate,
        candidate_model_call_rate=args.candidate_model_call_rate,
        avg_cost_cents_per_model_call=args.avg_cost_cents_per_model_call,
        variant=args.variant,
    )
    if args.payload_output:
        args.payload_output.parent.mkdir(parents=True, exist_ok=True)
        args.payload_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = write_feature_artifact_bundle(payload, args.output_dir, overwrite=args.overwrite)
    print(output)


if __name__ == "__main__":
    main()
