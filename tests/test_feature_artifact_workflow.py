from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from backend.services.evals.artifact_packager import write_feature_artifact_bundle
from backend.services.evals.copilot_router_eval import run_copilot_router_eval
from backend.services.evals.radar_evidence_eval import run_radar_evidence_eval


def _load_script(path: str, name: str):
    script_path = Path(__file__).resolve().parents[1] / path
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_feature_artifact_packager_writes_standard_bundle(tmp_path: Path):
    payload = {
        "metadata": {
            "report_type": "unit-feature-eval",
            "title": "Unit Feature Eval",
            "dataset_version": "unit_v1",
            "model": "deterministic",
            "prompt_version": "rules-v1",
            "recommendation": "review",
            "decision": "unit_test",
        },
        "metrics": {"pass_rate": 1.0},
        "token_breakdown": {"model_calls": 0},
        "cost_breakdown": {"total_cost_cents": 0},
        "latency_metrics": {"p95_ms": 1},
        "case_results": [{"case_id": "case-1", "passed": True}],
        "failure_summary": {"failed_case_count": 0},
        "cost_projection": {"evidence_status": "unit_test"},
        "supporting_artifacts": [{"label": "Fixture", "path": "evals/unit.jsonl"}],
        "notes": ["Unit test payload."],
    }

    output = write_feature_artifact_bundle(payload, tmp_path, overwrite=False)

    assert (output / "report.md").exists()
    assert json.loads((output / "metrics.json").read_text(encoding="utf-8"))["pass_rate"] == 1.0
    assert json.loads((output / "failure_summary.json").read_text(encoding="utf-8"))["failed_case_count"] == 0
    assert json.loads((output / "cost_projection.json").read_text(encoding="utf-8"))["evidence_status"] == "unit_test"
    assert (output / "case_results.jsonl").read_text(encoding="utf-8").strip()
    assert (output / "feature_artifact_source.json").exists()


def test_copilot_router_eval_shows_candidate_route_gain():
    result = run_copilot_router_eval()

    assert result["baseline"]["metrics"]["route_accuracy"] < result["candidate"]["metrics"]["route_accuracy"]
    assert result["candidate"]["metrics"]["route_accuracy"] >= 0.75
    assert result["candidate"]["metrics"]["clarification_accuracy"] >= 0.75


def test_radar_evidence_eval_flags_empty_generic_and_wrong_sources():
    result = run_radar_evidence_eval()
    failures = result["failure_summary"]["failure_type_counts"]

    assert result["metrics"]["pass_rate"] == 1.0
    assert failures["empty_page"] == 1
    assert failures["generic_evidence"] == 1
    assert failures["wrong_company"] == 1
    assert failures["wrong_role"] == 1
    assert failures["stale_evidence"] == 1


def test_gmail_artifact_payload_contains_cost_and_failure_sections():
    module = _load_script("scripts/run_gmail_classifier_artifact_eval.py", "run_gmail_classifier_artifact_eval")

    payload = module.build_artifact_payload(
        dataset_path=Path("evals/email_classifier/email_classifier_v1.jsonl"),
        baseline_model_call_rate=1.0,
        candidate_model_call_rate=0.25,
        avg_cost_cents_per_model_call=2.0,
    )

    assert payload["metadata"]["report_type"] == "gmail-classifier-artifact-eval"
    assert payload["cost_projection"]["delta"]["model_calls_avoided"] > 0
    assert "failure_type_counts" in payload["failure_summary"]
    assert payload["case_results"]


def test_source_retrieval_payload_contains_recommended_strategy_and_cases():
    module = _load_script("scripts/run_source_retrieval_eval.py", "run_source_retrieval_eval")
    from backend.services.evals.search_eval import run_search_eval

    result = run_search_eval()
    payload = module.build_artifact_payload(
        result,
        documents_path=Path("evals/search/search_documents_v1.json"),
        queries_path=Path("evals/search/search_queries_v1.jsonl"),
        baselines_path=Path("evals/search/search_baselines_v1.json"),
    )

    assert payload["metadata"]["report_type"] == "source-retrieval-eval"
    assert payload["metrics"]["recommended_strategy"]
    assert payload["case_results"]
    assert "failure_type_counts" in payload["failure_summary"]
