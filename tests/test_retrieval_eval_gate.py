from pathlib import Path

import pytest
from sqlalchemy import select

from backend.models import RetrievalTrace
from backend.services.retrieval.eval_gate import (
    EVAL_CASES,
    run_retrieval_eval_gate,
    write_retrieval_eval_gate_artifact,
)


def _strategy(result, name: str):
    return next(strategy for strategy in result.strategies if strategy.name == name)


@pytest.mark.asyncio
async def test_retrieval_eval_gate_compares_both_retrievers_on_same_cases(db_session):
    result = await run_retrieval_eval_gate(db_session)

    expected_labeled_count = sum(1 for case in EVAL_CASES if case.expected_document_keys)
    expected_empty_count = sum(1 for case in EVAL_CASES if case.expected_empty_reason)

    assert result.dataset_version == "retrieval_eval_gate_v2"
    assert result.case_count == len(EVAL_CASES)
    assert result.case_count >= 10
    source = _strategy(result, "source_search_documents")
    chunks = _strategy(result, "lexical_document_chunks")
    assert [case.case_id for case in source.cases] == [case.case_id for case in chunks.cases]
    assert [case.query for case in source.cases] == [case.query for case in chunks.cases]
    assert source.retriever_version == "source_search_documents_v1"
    assert chunks.retriever_version == "lexical_chunks_v1"

    for strategy in [source, chunks]:
        assert strategy.metrics["labeled_case_count"] == expected_labeled_count
        assert strategy.metrics["expected_empty_case_count"] == expected_empty_count
        assert strategy.metrics["user_isolation_failures"] == 0
        assert strategy.metrics["user_isolation_query_returned_empty"] is True
        assert strategy.metrics["empty_query_returned_empty"] is True
        assert strategy.metrics["unsupported_source_returned_empty"] is True
        assert strategy.metrics["empty_result_correctness"] == 1.0
        assert strategy.metrics["recall_at_3"] > 0
        assert strategy.metrics["mrr"] > 0
        assert strategy.metrics["citation_precision_at_3"] > 0
        assert strategy.metrics["source_precision_at_3"] > 0
        for case in strategy.cases:
            assert case.returned_document_keys == list(dict.fromkeys(case.returned_document_keys))
            if case.expected_empty_reason:
                assert case.trace["status"] == case.expected_empty_reason
                if case.case_id == "q_unsupported_source":
                    assert case.trace["source_types"] == []

    assert result.comparison["both_user_isolated"] is True
    assert result.comparison["both_handle_empty_and_unsupported"] is True
    assert result.comparison["source_recall_at_3"] >= 0
    assert result.comparison["chunk_recall_at_3"] >= 0
    assert "chunk_recall_improved" in result.comparison
    assert "chunk_citation_precision_improved" in result.comparison
    assert result.comparison["recommended_strategy_for_promotion"] == "none_hold_for_labeled_production_outcomes"
    assert "do_not_promote_chunk_retrieval_yet" in result.promotion_recommendation


@pytest.mark.asyncio
async def test_retrieval_eval_gate_persists_chunk_retrieval_traces(db_session):
    result = await run_retrieval_eval_gate(db_session)
    chunks = _strategy(result, "lexical_document_chunks")

    traces = list((await db_session.execute(select(RetrievalTrace))).scalars().all())
    assert len(traces) == len(EVAL_CASES)
    assert {trace.surface for trace in traces} == {"retrieval_eval_gate"}
    assert {trace.retriever_version for trace in traces} == {"lexical_chunks_v1"}

    chunk_case_traces = {case.case_id: case.trace for case in chunks.cases}
    assert chunk_case_traces["q_empty"]["status"] == "empty_query"
    assert chunk_case_traces["q_unsupported_source"]["status"] == "no_allowed_source_types"
    assert chunk_case_traces["q_user_isolation_foreign_unique"]["status"] == "ok"
    assert chunk_case_traces["q_user_isolation_foreign_unique"]["scores"] == []
    assert chunk_case_traces["q_assistant_search_role"]["scores"]


@pytest.mark.asyncio
async def test_retrieval_eval_gate_artifact_writes_comparable_traces(tmp_path: Path):
    output = tmp_path / "retrieval-gate.json"
    written = await write_retrieval_eval_gate_artifact(output)

    payload = written.read_text(encoding="utf-8")
    assert '"artifact": "retrieval_eval_gate"' in payload
    assert '"name": "source_search_documents"' in payload
    assert '"name": "lexical_document_chunks"' in payload
    assert '"dataset_version": "retrieval_eval_gate_v2"' in payload
    assert '"retriever_version": "source_search_documents_v1"' in payload
    assert '"retriever_version": "lexical_chunks_v1"' in payload
    assert '"chunk_recall_improved"' in payload
    assert '"promotion_recommendation"' in payload
