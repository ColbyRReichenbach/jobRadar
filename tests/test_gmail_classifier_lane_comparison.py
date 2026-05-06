import json
from pathlib import Path

from backend.services.evals.artifact_packager import write_feature_artifact_bundle
from backend.services.evals.gmail_classifier_lane_comparison import build_lane_comparison_payload


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _artifact_dir(tmp_path: Path, name: str, *, model: str, failed: bool, latency: float, cost: float) -> Path:
    artifact_dir = tmp_path / name
    artifact_dir.mkdir()
    passed = not failed
    failure_types = ["wrong_category", "wrong_stage"] if failed else []
    actual_classification = "conversation" if failed else "interview_request"
    rows = [
        {
            "case_id": "case-1",
            "expected": {
                "job_related": True,
                "classification": "interview_request",
                "stage": "interview",
            },
            "actual": {
                "job_related": True,
                "classification": actual_classification,
                "stage": "follow_up" if failed else "interview",
            },
            "passed": passed,
            "failure_types": failure_types,
            "latency_ms": latency,
            "cost_estimate_cents": cost,
            "prompt_tokens": 100 if model == "gpt-4o-mini" else 0,
            "output_tokens": 20 if model == "gpt-4o-mini" else 0,
        }
    ]
    _write_json(
        artifact_dir / "metadata.json",
        {
            "dataset_version": "email_classifier_synthetic_v1",
            "model": model,
            "prompt_version": "v1",
        },
    )
    _write_json(
        artifact_dir / "metrics.json",
        {
            "category_accuracy": 0.0 if failed else 1.0,
            "stage_accuracy": 0.0 if failed else 1.0,
            "job_related_recall": 1.0,
            "false_negatives": 0,
            "llm_call_rate": 1.0 if model == "gpt-4o-mini" else 0.0,
        },
    )
    _write_json(artifact_dir / "failure_summary.json", {"failed_case_count": 1 if failed else 0})
    _write_json(artifact_dir / "latency_metrics.json", {"avg_ms": latency, "p95_ms": latency})
    _write_json(artifact_dir / "cost_breakdown.json", {"total_cost_cents": cost, "cost_per_1000_emails_cents": cost * 1000})
    _write_json(
        artifact_dir / "token_breakdown.json",
        {
            "live_model_calls": 1 if model == "gpt-4o-mini" else 0,
            "prompt_tokens": 100 if model == "gpt-4o-mini" else 0,
            "output_tokens": 20 if model == "gpt-4o-mini" else 0,
            "total_tokens": 120 if model == "gpt-4o-mini" else 0,
        },
    )
    _write_jsonl(artifact_dir / "case_results.jsonl", rows)
    return artifact_dir


def test_build_lane_comparison_payload_identifies_resolved_failures(tmp_path: Path):
    rules_dir = _artifact_dir(tmp_path, "rules", model="fallback-rules", failed=True, latency=0.1, cost=0.0)
    live_dir = _artifact_dir(tmp_path, "live", model="gpt-4o-mini", failed=False, latency=2000.0, cost=0.01)

    payload = build_lane_comparison_payload(rules_dir=rules_dir, live_dir=live_dir)

    assert payload["metrics"]["failures_resolved_by_live"] == 1
    assert payload["metrics"]["live_regressions"] == 0
    assert payload["metrics"]["category_accuracy_delta"] == 1.0
    assert payload["failure_summary"]["resolved_failure_type_counts"]["wrong_category"] == 1
    assert payload["case_results"][0]["status"] == "resolved_by_live_llm"
    assert payload["token_breakdown"]["live_model_calls"] == 1


def test_lane_comparison_payload_writes_feature_bundle(tmp_path: Path):
    rules_dir = _artifact_dir(tmp_path, "rules", model="fallback-rules", failed=True, latency=0.1, cost=0.0)
    live_dir = _artifact_dir(tmp_path, "live", model="gpt-4o-mini", failed=False, latency=2000.0, cost=0.01)
    payload = build_lane_comparison_payload(rules_dir=rules_dir, live_dir=live_dir)

    output_dir = write_feature_artifact_bundle(payload, tmp_path / "generated", overwrite=True)

    assert (output_dir / "report.md").exists()
    assert (output_dir / "case_results.jsonl").exists()
    assert json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))["failures_resolved_by_live"] == 1

