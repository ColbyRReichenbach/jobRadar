from scripts.run_gmail_llm_label_eval import (
    LlmEvalResult,
    build_user_prompt,
    compute_metrics,
    normalize_prediction,
)


def test_build_user_prompt_omits_expected_labels():
    row = {
        "sender_domain": "joinhandshake.com",
        "redacted_subject": "A recruiter messaged you about a job",
        "redacted_body_preview": "View the message from a recruiter.",
        "expected_route": "conversation",
        "expected_subtype": "recruiter_outreach",
    }

    prompt = build_user_prompt(row)

    assert "A recruiter messaged you about a job" in prompt
    assert "expected_route" not in prompt
    assert "expected_subtype" not in prompt
    assert "conversation" not in prompt
    assert "recruiter_outreach" not in prompt


def test_normalize_prediction_guards_invalid_labels():
    route, subtype, confidence, rationale, fallback = normalize_prediction(
        {
            "route": "made_up",
            "subtype": "also_bad",
            "confidence": "1.4",
            "rationale": "Because.",
        }
    )

    assert route == "unsure"
    assert subtype == "unsure"
    assert confidence == 1.0
    assert rationale == "Because."
    assert "invalid_route" in fallback
    assert "invalid_subtype" in fallback


def test_compute_metrics_scores_route_subtype_and_cost(tmp_path):
    results = [
        LlmEvalResult(
            case_id="one",
            sender_domain="joinhandshake.com",
            expected_route="filter",
            expected_subtype="job_alert",
            llm_route="filter",
            llm_subtype="job_alert",
            llm_confidence=0.92,
            route_match=True,
            subtype_match=True,
            full_match=True,
            rationale="Generic alert.",
            model="gpt-4o-mini",
            prompt_version="test",
            latency_ms=100,
            prompt_tokens=100,
            output_tokens=20,
            cost_estimate_cents=0.01,
            fallback_reason="",
            redacted_subject="Job alert",
            redacted_body_preview="Jobs for you",
        ),
        LlmEvalResult(
            case_id="two",
            sender_domain="gmail.com",
            expected_route="conversation",
            expected_subtype="recruiter_outreach",
            llm_route="action_review",
            llm_subtype="unknown_other",
            llm_confidence=0.83,
            route_match=False,
            subtype_match=False,
            full_match=False,
            rationale="Ambiguous.",
            model="gpt-4o-mini",
            prompt_version="test",
            latency_ms=300,
            prompt_tokens=120,
            output_tokens=30,
            cost_estimate_cents=0.02,
            fallback_reason="",
            redacted_subject="Interview",
            redacted_body_preview="Can we talk?",
        ),
    ]

    metrics = compute_metrics(results, label_path=tmp_path / "labels.csv")

    assert metrics["totals"]["labeled_rows"] == 2
    assert metrics["totals"]["route_accuracy_pct"] == 50.0
    assert metrics["totals"]["subtype_exact_match_pct"] == 50.0
    assert metrics["totals"]["full_exact_match_pct"] == 50.0
    assert metrics["totals"]["high_confidence_wrong_count"] == 1
    assert metrics["tokens"]["total_tokens"] == 270
    assert metrics["cost"]["total_cost_cents"] == 0.03
