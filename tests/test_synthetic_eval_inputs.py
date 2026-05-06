from __future__ import annotations

import json
from pathlib import Path

from backend.services.evals.assistant_eval import run_copilot_eval
from backend.services.evals.classifier_eval import run_classifier_eval_sync
from backend.services.evals.copilot_router_eval import run_copilot_router_eval
from backend.services.evals.radar_evidence_eval import run_radar_evidence_eval
from backend.services.evals.search_eval import run_search_eval
from backend.services.evals.synthetic_fixtures import generate_all_synthetic_eval_inputs
from backend.services.red_team import run_red_team_eval


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_generate_synthetic_eval_inputs_has_component_coverage(tmp_path: Path):
    manifest = generate_all_synthetic_eval_inputs(tmp_path)
    counts = {item["component"]: item["count"] for item in manifest["datasets"]}

    assert counts["copilot_router"] >= 150
    assert counts["copilot_grounded_answers"] >= 50
    assert counts["gmail_classifier"] >= 150
    assert counts["radar_evidence"] >= 100
    assert counts["search_documents"] >= 80
    assert counts["search_queries"] >= 80
    assert counts["red_team"] >= 50

    router_rows = _jsonl(tmp_path / "evals/copilot/copilot_router_synthetic_v1.jsonl")
    routes = {row["expected_route"] for row in router_rows}
    assert routes >= {
        "radar_tracker_create_or_update",
        "radar_run_diagnostics",
        "job_search",
        "application_pipeline_question",
        "gmail_sync_diagnostics",
        "source_privacy_settings",
        "job_source_question",
        "unsupported_action",
        "unknown",
    }

    email_rows = _jsonl(tmp_path / "evals/email_classifier/email_classifier_synthetic_v1.jsonl")
    assert {row["expected_classification"] for row in email_rows} >= {
        "job_update",
        "interview_request",
        "action_item",
        "offer",
        "rejection",
        "conversation",
        "not_relevant",
    }
    assert all(".example" in row["sender_email"] for row in email_rows)


def test_synthetic_datasets_run_through_current_evals(tmp_path: Path):
    generate_all_synthetic_eval_inputs(tmp_path)

    router_result = run_copilot_router_eval(tmp_path / "evals/copilot/copilot_router_synthetic_v1.jsonl")
    assert router_result["candidate"]["metrics"]["case_count"] >= 150
    assert router_result["failure_summary"]["failed_case_count"] > 0

    copilot_result = run_copilot_eval(tmp_path / "evals/copilot/copilot_questions_synthetic_v1.jsonl")
    assert copilot_result.dataset_version == "copilot_questions_synthetic_v1"
    assert copilot_result.metrics["case_count"] >= 50

    classifier_result = run_classifier_eval_sync(tmp_path / "evals/email_classifier/email_classifier_synthetic_v1.jsonl")
    assert classifier_result["variants"]["fallback_rules_v1"]["metrics"]["example_count"] >= 150

    radar_result = run_radar_evidence_eval(tmp_path / "evals/radar/radar_evidence_quality_synthetic_v1.jsonl")
    assert radar_result["metrics"]["case_count"] >= 100
    assert radar_result["failure_summary"]["failure_type_counts"]["empty_page"] > 0

    search_result = run_search_eval(
        documents_path=tmp_path / "evals/search/search_documents_synthetic_v1.json",
        queries_path=tmp_path / "evals/search/search_queries_synthetic_v1.jsonl",
        baselines_path=tmp_path / "evals/search/search_baselines_synthetic_v1.json",
    )
    assert search_result.query_count >= 80
    assert search_result.user_isolation["passed"] is True

    red_team_result = run_red_team_eval([tmp_path / "evals/red_team/synthetic_safety_v1.jsonl"])
    assert red_team_result.case_count >= 50
    assert red_team_result.fail_closed_gate is True

