import uuid

import pytest
from sqlalchemy import select

from backend.models import Application, RetrievalTrace, User
from backend.services.copilot.retrieval import retrieve_copilot_context
from backend.services.retrieval.shadow import run_retrieval_shadow_comparison
from backend.services.search.indexer import index_record, search_user_documents
from tests.conftest import TEST_USER_ID


async def _seed_application(db_session, *, company: str = "TraceBank") -> Application:
    app = Application(
        user_id=TEST_USER_ID,
        company=company,
        role_title="Assistant Search Data Scientist",
        description_text="Build NLP search quality models and lexical retrieval for assistant conversations.",
    )
    db_session.add(app)
    await db_session.flush()
    await index_record(db_session, app)
    await db_session.commit()
    return app


@pytest.mark.asyncio
async def test_shadow_comparison_persists_comparable_source_and_chunk_traces(db_session):
    await _seed_application(db_session)

    comparison = await run_retrieval_shadow_comparison(
        db_session,
        user_id=TEST_USER_ID,
        query="assistant search retrieval",
        source_types=["application"],
        surface="radar",
        limit=5,
    )

    assert comparison.surface == "radar_shadow"
    assert comparison.source_returned_count == 1
    assert comparison.chunk_returned_count == 1

    traces = (
        await db_session.execute(
            select(RetrievalTrace)
            .where(RetrievalTrace.surface == "radar_shadow")
            .order_by(RetrievalTrace.retriever_version.asc())
        )
    ).scalars().all()
    assert {trace.retriever_version for trace in traces} == {
        "lexical_chunks_v1",
        "source_search_documents_v1",
    }
    by_version = {trace.retriever_version: trace for trace in traces}
    source_trace = by_version["source_search_documents_v1"]
    chunk_trace = by_version["lexical_chunks_v1"]
    assert source_trace.id == comparison.source_trace_id
    assert chunk_trace.id == comparison.chunk_trace_id
    assert source_trace.query == chunk_trace.query == "assistant search retrieval"
    assert source_trace.normalized_query == chunk_trace.normalized_query
    assert source_trace.source_types == chunk_trace.source_types == ["application"]
    assert source_trace.status == chunk_trace.status == "ok"
    assert source_trace.scores_json[0]["source_id"] == chunk_trace.scores_json[0]["source_id"]
    assert source_trace.selected_chunk_ids == []
    assert chunk_trace.selected_chunk_ids


@pytest.mark.asyncio
async def test_copilot_shadow_tracing_is_opt_in_and_does_not_change_context(db_session, monkeypatch):
    app = await _seed_application(db_session)
    monkeypatch.delenv("RETRIEVAL_SHADOW_ENABLED", raising=False)
    monkeypatch.delenv("COPILOT_RETRIEVAL_SHADOW_ENABLED", raising=False)

    baseline = await retrieve_copilot_context(
        db_session,
        user_id=TEST_USER_ID,
        query="assistant search roles",
        source_types=["application"],
    )
    assert baseline[0].source_id == app.id
    trace_count = len((await db_session.execute(select(RetrievalTrace))).scalars().all())
    assert trace_count == 0

    source_results = await search_user_documents(
        db_session,
        user_id=TEST_USER_ID,
        query="assistant search roles",
        source_types=["application"],
        limit=8,
    )
    monkeypatch.setenv("COPILOT_RETRIEVAL_SHADOW_ENABLED", "true")
    shadowed = await retrieve_copilot_context(
        db_session,
        user_id=TEST_USER_ID,
        query="assistant search roles",
        source_types=["application"],
    )

    assert [item.to_dict() for item in shadowed] == [item.to_dict() for item in baseline]
    assert [str(item.source_id) for item in shadowed] == [str(result.source_id) for result in source_results]

    traces = (
        await db_session.execute(
            select(RetrievalTrace)
            .where(RetrievalTrace.surface == "copilot_shadow")
            .order_by(RetrievalTrace.retriever_version.asc())
        )
    ).scalars().all()
    assert {trace.retriever_version for trace in traces} == {
        "lexical_chunks_v1",
        "source_search_documents_v1",
    }
    assert {trace.user_id for trace in traces} == {TEST_USER_ID}
    assert all(trace.query == "assistant search roles" for trace in traces)


@pytest.mark.asyncio
async def test_copilot_shadow_failure_does_not_change_context(db_session, monkeypatch):
    app = await _seed_application(db_session)
    monkeypatch.setenv("COPILOT_RETRIEVAL_SHADOW_ENABLED", "true")

    async def fail_shadow(*args, **kwargs):
        raise RuntimeError("shadow unavailable")

    monkeypatch.setattr("backend.services.copilot.retrieval.run_retrieval_shadow_comparison", fail_shadow)

    citations = await retrieve_copilot_context(
        db_session,
        user_id=TEST_USER_ID,
        query="assistant search roles",
        source_types=["application"],
    )

    assert len(citations) == 1
    assert citations[0].source_id == app.id
    traces = list((await db_session.execute(select(RetrievalTrace))).scalars().all())
    assert traces == []


@pytest.mark.asyncio
async def test_shadow_comparison_preserves_user_isolation(db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="shadow-other", email="shadow-other@apptrail.test", name="Other"))
    db_session.add(
        Application(
            user_id=other_user_id,
            company="OtherBank",
            role_title="Shadowleak Zebra Scientist",
            description_text="Foreign-only shibboleth zephyr marker.",
        )
    )
    await db_session.flush()
    other_app = (await db_session.execute(select(Application).where(Application.user_id == other_user_id))).scalar_one()
    await index_record(db_session, other_app)
    await db_session.commit()

    comparison = await run_retrieval_shadow_comparison(
        db_session,
        user_id=TEST_USER_ID,
        query="shadowleak zebra shibboleth",
        surface="copilot",
        limit=5,
    )

    assert comparison.source_returned_count == 0
    assert comparison.chunk_returned_count == 0
    traces = (
        await db_session.execute(
            select(RetrievalTrace)
            .where(RetrievalTrace.surface == "copilot_shadow")
            .order_by(RetrievalTrace.retriever_version.asc())
        )
    ).scalars().all()
    assert {trace.returned_count for trace in traces} == {0}
