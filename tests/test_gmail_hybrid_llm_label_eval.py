from scripts.run_gmail_hybrid_llm_label_eval import HybridLayerResult, compute_metrics


def _result(
    *,
    case_id: str,
    expected_route: str,
    expected_subtype: str,
    hybrid_route: str,
    hybrid_subtype: str,
    model_used: bool,
    prompt_tokens: int = 0,
    output_tokens: int = 0,
    cost_estimate_cents: float = 0.0,
) -> HybridLayerResult:
    return HybridLayerResult(
        case_id=case_id,
        sender_domain="gmail.com",
        expected_route=expected_route,
        expected_subtype=expected_subtype,
        hybrid_route=hybrid_route,
        hybrid_subtype=hybrid_subtype,
        hybrid_confidence=0.9,
        route_match=expected_route == hybrid_route,
        subtype_match=expected_subtype == hybrid_subtype,
        full_match=expected_route == hybrid_route and expected_subtype == hybrid_subtype,
        decision_source="llm_adjudicated" if model_used else "deterministic_classifier",
        model_used=model_used,
        model="gpt-4o-mini" if model_used else "",
        latency_ms=100 if model_used else 0,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        cost_estimate_cents=cost_estimate_cents,
        fallback_reason="",
        original_route="action_review",
        original_subtype="unknown_other",
        original_would_call_llm=str(model_used).lower(),
        rationale="",
        redacted_subject="Subject",
        redacted_body_preview="Preview",
    )


def test_compute_metrics_tracks_model_call_savings(tmp_path):
    llm_first_metrics = tmp_path / "llm_first.json"
    llm_first_metrics.write_text(
        """
        {
          "totals": {"labeled_rows": 2},
          "tokens": {"total_tokens": 1000},
          "cost": {"total_cost_cents": 1.0},
          "latency": {"avg_ms": 500}
        }
        """,
        encoding="utf-8",
    )
    metrics = compute_metrics(
        [
            _result(
                case_id="one",
                expected_route="conversation",
                expected_subtype="recruiter_outreach",
                hybrid_route="conversation",
                hybrid_subtype="recruiter_outreach",
                model_used=True,
                prompt_tokens=100,
                output_tokens=25,
                cost_estimate_cents=0.1,
            ),
            _result(
                case_id="two",
                expected_route="filter",
                expected_subtype="job_alert",
                hybrid_route="filter",
                hybrid_subtype="job_alert",
                model_used=False,
            ),
        ],
        label_path=tmp_path / "labels.csv",
        llm_first_metrics_path=llm_first_metrics,
    )

    assert metrics["totals"]["route_accuracy_pct"] == 100.0
    assert metrics["totals"]["model_call_count"] == 1
    assert metrics["tokens"]["total_tokens"] == 125
    assert metrics["llm_first_comparison"]["tokens_saved"] == 875
    assert metrics["llm_first_comparison"]["cost_saved_cents"] == 0.9
