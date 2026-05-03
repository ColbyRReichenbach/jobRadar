from pathlib import Path

from backend.services.evals.assistant_eval import (
    render_copilot_eval_report,
    run_copilot_eval,
    write_copilot_eval_outputs,
)


def test_copilot_eval_scores_groundedness_citations_and_refusals():
    result = run_copilot_eval()

    assert result.dataset_version == "copilot_questions_v1"
    assert result.metrics["case_count"] == 4
    assert result.metrics["pass_rate"] == 1.0
    assert result.metrics["groundedness"] == 1.0
    assert result.metrics["citation_coverage"] == 1.0
    assert result.metrics["unsupported_claim_rate"] == 0.0
    assert result.metrics["refusal_correctness"] == 1.0
    assert result.metrics["cost_estimate_cents"] == 0
    assert result.bad_examples
    assert "unsupported_claim" in result.bad_examples[0].failure_types


def test_copilot_eval_report_contains_good_and_bad_examples(tmp_path: Path):
    result = run_copilot_eval()
    report = render_copilot_eval_report(result)

    assert "# Copilot Eval Report" in report
    assert "## Good Example" in report
    assert "## Bad Examples Caught By Scorer" in report
    assert "unsupported_claim" in report

    report_path, metrics_path = write_copilot_eval_outputs(
        result,
        report_path=tmp_path / "copilot-eval.md",
        metrics_path=tmp_path / "copilot-eval.json",
    )
    assert "Copilot Eval Report" in report_path.read_text(encoding="utf-8")
    assert '"pass_rate": 1.0' in metrics_path.read_text(encoding="utf-8")
