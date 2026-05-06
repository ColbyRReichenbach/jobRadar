import json
from pathlib import Path

from backend.services.evals import classifier_eval
from backend.services.evals.classifier_eval import build_report_payload, load_examples, run_classifier_eval_sync, stage_from_classification
from backend.services.reports.report_templates import report_input_from_dict
from backend.services.reports.report_writer import render_report_markdown


def test_load_examples_uses_sanitized_dataset():
    examples = load_examples("evals/email_classifier/email_classifier_v1.jsonl")

    assert len(examples) >= 10
    assert all(".example" in example.sender_email for example in examples)
    assert not any("@gmail.com" in example.sender_email for example in examples)
    assert {example.expected_stage for example in examples} >= {
        "applied",
        "interview",
        "assessment",
        "offer",
        "rejection",
        "follow_up",
        "unknown",
    }


def test_stage_mapping_is_stable():
    assert stage_from_classification("job_update") == "applied"
    assert stage_from_classification("interview_request") == "interview"
    assert stage_from_classification("action_item") == "assessment"
    assert stage_from_classification("offer") == "offer"
    assert stage_from_classification("rejection") == "rejection"
    assert stage_from_classification("conversation") == "follow_up"
    assert stage_from_classification("not_relevant") == "unknown"
    assert stage_from_classification("unexpected") == "unknown"


def test_run_classifier_eval_produces_metrics_and_variant_comparison():
    result = run_classifier_eval_sync("evals/email_classifier/email_classifier_v1.jsonl")

    assert result["dataset_version"] == "email_classifier_v1"
    assert "fallback_rules_v1" in result["variants"]
    assert "subject_only_baseline_v1" in result["variants"]
    primary = result["variants"]["fallback_rules_v1"]["metrics"]
    assert primary["example_count"] >= 10
    assert "confusion_matrix" in primary
    assert "precision" in primary["job_related"]
    assert "recall" in primary["job_related"]
    assert "stage_accuracy" in primary
    assert "latency" in primary
    assert "cost" in primary


def test_run_classifier_eval_can_include_live_llm_variant(monkeypatch, tmp_path: Path):
    dataset = tmp_path / "email_classifier_live_fixture.jsonl"
    dataset.write_text(
        json.dumps({
            "id": "live-1",
            "sender": "Recruiting Team",
            "sender_email": "jobs@example.com",
            "subject": "Interview request",
            "body": "Please schedule your interview.",
            "expected_job_related": True,
            "expected_classification": "interview_request",
            "expected_stage": "interview",
        })
        + "\n",
        encoding="utf-8",
    )

    async def _fake_live_predict(example):
        return classifier_eval.Prediction(
            example_id=example.id,
            classification="interview_request",
            stage="interview",
            job_related=True,
            latency_ms=123.4,
            cost_estimate_cents=0.0123,
            model_used=True,
            prompt_tokens=200,
            output_tokens=40,
        )

    monkeypatch.setattr(classifier_eval.ai_orchestrator, "has_configured_api_key", lambda: True)
    monkeypatch.setattr(classifier_eval, "live_llm_predict", _fake_live_predict)

    result = run_classifier_eval_sync(dataset, include_live_llm=True)
    live = result["variants"]["live_llm_v1"]

    assert live["model"] == classifier_eval.email_classifier.CLASSIFIER_MODEL
    assert live["metrics"]["model_call_count"] == 1
    assert live["metrics"]["model_call_rate"] == 1.0
    assert live["metrics"]["prompt_tokens"] == 200
    assert live["metrics"]["cost"]["total_cost_cents"] == 0.0123


def test_run_classifier_eval_can_include_hybrid_variant(tmp_path: Path):
    dataset = tmp_path / "email_classifier_hybrid_fixture.jsonl"
    dataset.write_text(
        json.dumps({
            "id": "hybrid-1",
            "sender": "TraceBank Recruiting",
            "sender_email": "recruiting@tracebank.example",
            "subject": "Complete your assessment",
            "body": "Your next step is a SQL and Python assessment for the Data Scientist opening.",
            "expected_job_related": True,
            "expected_classification": "action_item",
            "expected_stage": "assessment",
        })
        + "\n",
        encoding="utf-8",
    )

    result = run_classifier_eval_sync(dataset, include_hybrid=True)
    hybrid = result["variants"]["hybrid_rules_nlp_llm_v1"]
    prediction = hybrid["predictions"][0]

    assert hybrid["model"] == "hybrid-rules-nlp-llm"
    assert hybrid["metrics"]["category_accuracy"] == 1.0
    assert hybrid["metrics"]["model_call_count"] == 0
    assert prediction["classification"] == "action_item"
    assert prediction["decision_path"] == "deterministic_high_confidence"
    assert prediction["matched_features"]


def test_classifier_eval_report_payload_renders_with_recall_tradeoff_note():
    result = run_classifier_eval_sync("evals/email_classifier/email_classifier_v1.jsonl")
    payload = build_report_payload(result, generated_at="2026-05-02T12:00:00Z", git_sha="abc123")

    report = report_input_from_dict(payload)
    markdown = render_report_markdown(report)

    assert "| recall |" in markdown
    assert "| false_negatives |" in markdown
    assert "| confusion_matrix |" in markdown
    assert "Recall is weighted above precision" in markdown
    assert "subject-only baseline" in markdown


def test_eval_result_can_be_written_as_metrics_json(tmp_path: Path):
    result = run_classifier_eval_sync("evals/email_classifier/email_classifier_v1.jsonl")
    output = tmp_path / "metrics.json"

    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    loaded = json.loads(output.read_text(encoding="utf-8"))

    assert loaded["variants"]["fallback_rules_v1"]["metrics"]["example_count"] == len(
        load_examples("evals/email_classifier/email_classifier_v1.jsonl")
    )
