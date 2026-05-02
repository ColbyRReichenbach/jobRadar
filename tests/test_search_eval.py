from pathlib import Path

from backend.services.evals.search_eval import (
    render_search_eval_report,
    run_search_eval,
    write_search_eval_outputs,
)


def _strategy(result, name: str):
    return next(item for item in result.strategies if item.name == name)


def test_search_eval_scores_retrieval_strategies_without_live_services():
    result = run_search_eval()

    assert result.dataset_version == "search_eval_v1"
    assert result.query_count == 6
    assert result.document_count == 7
    assert result.indexing_failure_count == 0
    assert result.stale_document_count == 1
    assert result.user_isolation["passed"] is True
    assert result.user_isolation["foreign_document_count"] == 1
    assert result.user_isolation["leaked_document_keys"] == []

    title = _strategy(result, "title_keyword_v1")
    full_text = _strategy(result, "full_text_keyword_v1")
    semantic = _strategy(result, "semantic_expansion_v1")
    hybrid = _strategy(result, "hybrid_plus_boost_v1")
    vector = _strategy(result, "vector_embedding_v1")

    assert title.status == "completed"
    assert full_text.status == "completed"
    assert semantic.status == "completed"
    assert hybrid.status == "completed"
    assert vector.status == "skipped"
    assert "Embeddings are not provisioned" in (vector.skip_reason or "")

    assert hybrid.metrics["recall_at_5"] >= full_text.metrics["recall_at_5"]
    assert semantic.metrics["recall_at_5"] >= title.metrics["recall_at_5"]
    assert hybrid.metrics["zero_result_rate"] <= title.metrics["zero_result_rate"]
    assert result.recommended_strategy == "semantic_expansion_v1"


def test_search_eval_report_renders_decision_and_guardrails(tmp_path: Path):
    result = run_search_eval()
    report = render_search_eval_report(result)

    assert "# Search Eval Report" in report
    assert "`hybrid_plus_boost_v1`" in report
    assert "User isolation passed: `True`" in report
    assert "vector_embedding_v1" in report
    assert "deterministic expansion proxy" in report

    report_path, metrics_path = write_search_eval_outputs(
        result,
        report_path=tmp_path / "search-eval.md",
        metrics_path=tmp_path / "metrics.json",
    )
    assert report_path.read_text(encoding="utf-8").startswith("# Search Eval Report")
    assert '"recommended_strategy": "semantic_expansion_v1"' in metrics_path.read_text(encoding="utf-8")
