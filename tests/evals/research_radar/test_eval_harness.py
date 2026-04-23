from tests.evals.research_radar.harness import run_all_evals


def test_research_radar_eval_harness_smoke():
    summary = run_all_evals()

    assert summary["passed"] is True
    assert summary["suite_count"] == 5
    assert {suite["suite"] for suite in summary["suites"]} == {
        "brief_normalization",
        "plan_quality",
        "evidence_extraction",
        "grounding",
        "report_usefulness",
    }
