"""Compare Gmail classifier eval artifacts across architecture lanes."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from backend.services.evals.artifact_packager import current_git_sha, utc_now_iso


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_artifact_dir(path: Path | str) -> dict[str, Any]:
    artifact_dir = Path(path)
    return {
        "path": str(artifact_dir),
        "metadata": _load_json(artifact_dir / "metadata.json"),
        "metrics": _load_json(artifact_dir / "metrics.json"),
        "failure_summary": _load_json(artifact_dir / "failure_summary.json"),
        "latency_metrics": _load_json(artifact_dir / "latency_metrics.json"),
        "cost_breakdown": _load_json(artifact_dir / "cost_breakdown.json"),
        "token_breakdown": _load_json(artifact_dir / "token_breakdown.json"),
        "case_results": _load_jsonl(artifact_dir / "case_results.jsonl"),
    }


def _case_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["case_id"]): row for row in rows}


def _status_for_case(rules_case: dict[str, Any], live_case: dict[str, Any]) -> str:
    rules_passed = bool(rules_case.get("passed"))
    live_passed = bool(live_case.get("passed"))
    if rules_passed and live_passed:
        return "unchanged_pass"
    if not rules_passed and live_passed:
        return "resolved_by_live_llm"
    if rules_passed and not live_passed:
        return "live_llm_regression"
    return "unchanged_fail"


def _flat_metrics(rules: dict[str, Any], live: dict[str, Any], case_count: int) -> dict[str, Any]:
    rules_metrics = rules["metrics"]
    live_metrics = live["metrics"]
    rules_latency = rules["latency_metrics"]
    live_latency = live["latency_metrics"]
    rules_cost = rules["cost_breakdown"]
    live_cost = live["cost_breakdown"]
    return {
        "case_count": case_count,
        "rules_category_accuracy": rules_metrics.get("category_accuracy", 0),
        "live_category_accuracy": live_metrics.get("category_accuracy", 0),
        "category_accuracy_delta": round(
            float(live_metrics.get("category_accuracy", 0)) - float(rules_metrics.get("category_accuracy", 0)),
            4,
        ),
        "rules_stage_accuracy": rules_metrics.get("stage_accuracy", 0),
        "live_stage_accuracy": live_metrics.get("stage_accuracy", 0),
        "stage_accuracy_delta": round(
            float(live_metrics.get("stage_accuracy", 0)) - float(rules_metrics.get("stage_accuracy", 0)),
            4,
        ),
        "rules_job_related_recall": rules_metrics.get("job_related_recall", 0),
        "live_job_related_recall": live_metrics.get("job_related_recall", 0),
        "rules_false_negatives": rules_metrics.get("false_negatives", 0),
        "live_false_negatives": live_metrics.get("false_negatives", 0),
        "rules_llm_call_rate": rules_metrics.get("llm_call_rate", 0),
        "live_llm_call_rate": live_metrics.get("llm_call_rate", 0),
        "rules_avg_latency_ms": rules_latency.get("avg_ms", 0),
        "live_avg_latency_ms": live_latency.get("avg_ms", 0),
        "avg_latency_delta_ms": round(float(live_latency.get("avg_ms", 0)) - float(rules_latency.get("avg_ms", 0)), 3),
        "rules_p95_latency_ms": rules_latency.get("p95_ms", 0),
        "live_p95_latency_ms": live_latency.get("p95_ms", 0),
        "p95_latency_delta_ms": round(float(live_latency.get("p95_ms", 0)) - float(rules_latency.get("p95_ms", 0)), 3),
        "rules_cost_per_1000_emails_cents": rules_cost.get("cost_per_1000_emails_cents", 0),
        "live_cost_per_1000_emails_cents": live_cost.get("cost_per_1000_emails_cents", 0),
        "cost_per_1000_delta_cents": round(
            float(live_cost.get("cost_per_1000_emails_cents", 0))
            - float(rules_cost.get("cost_per_1000_emails_cents", 0)),
            6,
        ),
    }


def build_lane_comparison_payload(
    *,
    rules_dir: Path | str,
    live_dir: Path | str,
) -> dict[str, Any]:
    rules = load_artifact_dir(rules_dir)
    live = load_artifact_dir(live_dir)
    rules_cases = _case_map(rules["case_results"])
    live_cases = _case_map(live["case_results"])
    missing = sorted(set(rules_cases) ^ set(live_cases))
    if missing:
        raise ValueError(f"Artifact case IDs do not match: {', '.join(missing[:10])}")

    comparison_rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    resolved_failure_types: Counter[str] = Counter()
    regression_failure_types: Counter[str] = Counter()
    rules_failure_types: Counter[str] = Counter()
    live_failure_types: Counter[str] = Counter()
    rules_confusion: Counter[str] = Counter()
    live_confusion: Counter[str] = Counter()

    for case_id in sorted(rules_cases):
        rules_case = rules_cases[case_id]
        live_case = live_cases[case_id]
        status = _status_for_case(rules_case, live_case)
        status_counts[status] += 1
        rules_failures = list(rules_case.get("failure_types") or [])
        live_failures = list(live_case.get("failure_types") or [])
        rules_failure_types.update(rules_failures)
        live_failure_types.update(live_failures)
        if status == "resolved_by_live_llm":
            resolved_failure_types.update(rules_failures)
        elif status == "live_llm_regression":
            regression_failure_types.update(live_failures)

        expected_classification = str((rules_case.get("expected") or {}).get("classification"))
        rules_classification = str((rules_case.get("actual") or {}).get("classification"))
        live_classification = str((live_case.get("actual") or {}).get("classification"))
        rules_confusion[f"{expected_classification}->{rules_classification}"] += 1
        live_confusion[f"{expected_classification}->{live_classification}"] += 1

        comparison_rows.append(
            {
                "case_id": case_id,
                "expected": rules_case.get("expected"),
                "rules_actual": rules_case.get("actual"),
                "live_actual": live_case.get("actual"),
                "status": status,
                "rules_failure_types": rules_failures,
                "live_failure_types": live_failures,
                "rules_latency_ms": rules_case.get("latency_ms"),
                "live_latency_ms": live_case.get("latency_ms"),
                "rules_cost_estimate_cents": rules_case.get("cost_estimate_cents"),
                "live_cost_estimate_cents": live_case.get("cost_estimate_cents"),
                "live_prompt_tokens": live_case.get("prompt_tokens"),
                "live_output_tokens": live_case.get("output_tokens"),
            }
        )

    case_count = len(comparison_rows)
    metrics = _flat_metrics(rules, live, case_count)
    metrics.update(
        {
            "rules_failed_case_count": int(rules["failure_summary"].get("failed_case_count", 0)),
            "live_failed_case_count": int(live["failure_summary"].get("failed_case_count", 0)),
            "failures_resolved_by_live": status_counts.get("resolved_by_live_llm", 0),
            "live_regressions": status_counts.get("live_llm_regression", 0),
            "unchanged_failures": status_counts.get("unchanged_fail", 0),
        }
    )

    return {
        "metadata": {
            "report_type": "gmail-classifier-lane-comparison",
            "title": "Gmail Classifier Lane Comparison",
            "generated_at": utc_now_iso(),
            "git_sha": current_git_sha(),
            "release_version": "feature-artifacts",
            "dataset_version": str(live["metadata"].get("dataset_version") or rules["metadata"].get("dataset_version")),
            "model": f"{rules['metadata'].get('model')} vs {live['metadata'].get('model')}",
            "prompt_version": f"{rules['metadata'].get('prompt_version')} vs {live['metadata'].get('prompt_version')}",
            "recommendation": "design_hybrid_prefilter_then_llm_adjudication_lane",
            "decision": "compare_before_architecture_change",
        },
        "metrics": metrics,
        "token_breakdown": {
            "rules_live_model_calls": rules["token_breakdown"].get("live_model_calls", 0),
            "live_model_calls": live["token_breakdown"].get("live_model_calls", 0),
            "live_prompt_tokens": live["token_breakdown"].get("prompt_tokens", 0),
            "live_output_tokens": live["token_breakdown"].get("output_tokens", 0),
            "live_total_tokens": live["token_breakdown"].get("total_tokens", 0),
        },
        "cost_breakdown": {
            "rules_total_cost_cents": rules["cost_breakdown"].get("total_cost_cents", 0),
            "live_total_cost_cents": live["cost_breakdown"].get("total_cost_cents", 0),
            "rules_cost_per_1000_emails_cents": rules["cost_breakdown"].get("cost_per_1000_emails_cents", 0),
            "live_cost_per_1000_emails_cents": live["cost_breakdown"].get("cost_per_1000_emails_cents", 0),
        },
        "latency_metrics": {
            "rules_avg_ms": rules["latency_metrics"].get("avg_ms", 0),
            "live_avg_ms": live["latency_metrics"].get("avg_ms", 0),
            "rules_p95_ms": rules["latency_metrics"].get("p95_ms", 0),
            "live_p95_ms": live["latency_metrics"].get("p95_ms", 0),
        },
        "case_results": comparison_rows,
        "failure_summary": {
            "case_count": case_count,
            "status_counts": dict(sorted(status_counts.items())),
            "rules_failure_type_counts": dict(sorted(rules_failure_types.items())),
            "live_failure_type_counts": dict(sorted(live_failure_types.items())),
            "resolved_failure_type_counts": dict(sorted(resolved_failure_types.items())),
            "live_regression_failure_type_counts": dict(sorted(regression_failure_types.items())),
            "rules_top_confusion_pairs": dict(rules_confusion.most_common(12)),
            "live_top_confusion_pairs": dict(live_confusion.most_common(12)),
            "highest_risk_failure": "live_llm_regression" if regression_failure_types else None,
        },
        "cost_projection": {
            "feature": "gmail_classifier",
            "period": "per_1000_emails",
            "rules_cost_cents": rules["cost_breakdown"].get("cost_per_1000_emails_cents", 0),
            "live_cost_cents": live["cost_breakdown"].get("cost_per_1000_emails_cents", 0),
            "delta_cents": metrics["cost_per_1000_delta_cents"],
            "evidence_status": "measured_from_synthetic_artifact_run",
        },
        "supporting_artifacts": [
            {"label": "Rules-only artifact", "path": str(rules_dir)},
            {"label": "Live LLM artifact", "path": str(live_dir)},
            {"label": "Classifier eval dataset", "path": "evals/email_classifier/email_classifier_synthetic_v1.jsonl"},
            {"label": "Feature changelog", "path": "docs/interview-artifacts/feature-changelogs/gmail-classifier-changelog.md"},
        ],
        "notes": [
            "Synthetic data is useful for obvious architecture failures and cost/latency comparison, not for final statistical confidence.",
            "The rules lane optimizes cost and privacy but currently misses specific category/stage routing cases.",
            "The live LLM lane handles the synthetic taxonomy but pays per-email latency, cost, and privacy review overhead.",
            "The next architecture should not pick one lane blindly; it should use deterministic prefilters and thresholds, then call the LLM only for ambiguous cases.",
        ],
    }

