import uuid

import pytest
from sqlalchemy import select

from backend.models import Application, DocumentChunk, EmailEvent, RetrievalTrace, User, UserKnowledgeDocument
from backend.services.retrieval.chunking import chunk_text
from backend.services.retrieval.eval_artifacts import build_local_retrieval_eval_artifact
from backend.services.retrieval.lexical import retrieve_document_chunks
from backend.services.search.indexer import index_record, reindex_user_documents
from tests.conftest import TEST_USER_ID


def test_chunk_text_is_deterministic_and_overlapping():
    chunks = chunk_text("one two three four five six seven eight", max_tokens=4, overlap_tokens=1)

    assert [chunk.content for chunk in chunks] == [
        "one two three four",
        "four five six seven",
        "seven eight",
    ]
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert chunks == chunk_text("one two three four five six seven eight", max_tokens=4, overlap_tokens=1)


@pytest.mark.asyncio
async def test_index_record_creates_knowledge_document_and_chunks(db_session):
    app = Application(
        user_id=TEST_USER_ID,
        company="TraceBank",
        role_title="Assistant Search Data Scientist",
        description_text="Build lexical retrieval, chunk indexing, and NLP evaluation workflows.",
    )
    db_session.add(app)
    await db_session.flush()

    search_doc = await index_record(db_session, app)
    await db_session.commit()

    knowledge_doc = (await db_session.execute(select(UserKnowledgeDocument))).scalar_one()
    chunks = list((await db_session.execute(select(DocumentChunk))).scalars().all())
    assert knowledge_doc.search_document_id == search_doc.id
    assert knowledge_doc.source_type == "application"
    assert knowledge_doc.source_id == app.id
    assert "lexical retrieval" in knowledge_doc.content
    assert len(chunks) == 1
    assert chunks[0].document_id == knowledge_doc.id
    assert chunks[0].source_id == app.id


@pytest.mark.asyncio
async def test_email_knowledge_document_skips_raw_body(db_session):
    email = EmailEvent(
        user_id=TEST_USER_ID,
        subject="Offer discussion",
        sender="Recruiter",
        summary="Offer discussion for assistant analytics.",
        snippet="Offer discussion",
        body="raw-body-token-should-not-appear",
        classification="offer",
    )
    db_session.add(email)
    await db_session.flush()

    await index_record(db_session, email)
    await db_session.commit()

    knowledge_doc = (await db_session.execute(select(UserKnowledgeDocument))).scalar_one()
    chunk = (await db_session.execute(select(DocumentChunk))).scalar_one()
    assert "raw-body-token-should-not-appear" not in knowledge_doc.content
    assert "raw-body-token-should-not-appear" not in chunk.content


@pytest.mark.asyncio
async def test_reindex_user_documents_indexes_knowledge_chunks(db_session):
    db_session.add_all(
        [
            Application(
                user_id=TEST_USER_ID,
                company="TraceBank",
                role_title="NLP Analyst",
                description_text="Assistant search analytics and retrieval evaluation.",
            ),
            EmailEvent(
                user_id=TEST_USER_ID,
                subject="Assistant search interview",
                sender="Recruiter",
                summary="Interview invitation for assistant search analytics.",
                classification="interview_request",
            ),
        ]
    )
    await db_session.flush()

    counts = await reindex_user_documents(db_session, user_id=TEST_USER_ID, source_types=["application", "email"])
    await db_session.commit()

    assert counts == {"application": 1, "email": 1}
    knowledge_docs = list((await db_session.execute(select(UserKnowledgeDocument))).scalars().all())
    chunks = list((await db_session.execute(select(DocumentChunk))).scalars().all())
    assert len(knowledge_docs) == 2
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_lexical_chunk_retrieval_is_user_scoped_and_persists_trace(db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="retrieval-other", email="retrieval-other@apptrail.test", name="Other"))
    user_app = Application(
        user_id=TEST_USER_ID,
        company="TraceBank",
        role_title="Assistant Search Data Scientist",
        description_text="Build assistant search retrieval and chunk indexing.",
    )
    same_user_other_app = Application(
        user_id=TEST_USER_ID,
        company="FilterBank",
        role_title="Assistant Search Analyst",
        description_text="This same user's assistant search chunk should be filtered out.",
    )
    other_app = Application(
        user_id=other_user_id,
        company="OtherBank",
        role_title="Assistant Search Data Scientist",
        description_text="This other user's assistant search chunk must not appear.",
    )
    db_session.add_all([user_app, same_user_other_app, other_app])
    await db_session.flush()
    await index_record(db_session, user_app)
    await index_record(db_session, same_user_other_app)
    await index_record(db_session, other_app)
    await db_session.commit()

    results = await retrieve_document_chunks(
        db_session,
        user_id=TEST_USER_ID,
        query="assistant search chunk",
        source_types=["application"],
        filters={"source_ids": [str(user_app.id)]},
        surface="copilot_eval",
        limit=5,
    )

    assert [result.source_id for result in results] == [user_app.id]
    trace = (await db_session.execute(select(RetrievalTrace))).scalar_one()
    assert trace.user_id == TEST_USER_ID
    assert trace.surface == "copilot_eval"
    assert trace.retriever_version == "lexical_chunks_v1"
    assert trace.returned_count == 1
    assert trace.filters_json == {"source_ids": [str(user_app.id)]}
    assert trace.selected_chunk_ids == [str(results[0].chunk_id)]
    assert trace.scores_json[0]["source_id"] == str(user_app.id)
    assert trace.scores_json[0]["content_hash"] == results[0].content_hash
    assert trace.scores_json[0]["snippet"] == results[0].snippet


@pytest.mark.asyncio
async def test_lexical_chunk_retrieval_rejects_unsupported_filters(db_session):
    app = Application(
        user_id=TEST_USER_ID,
        company="TraceBank",
        role_title="Assistant Search Data Scientist",
        description_text="Build assistant search retrieval and chunk indexing.",
    )
    db_session.add(app)
    await db_session.flush()
    await index_record(db_session, app)
    await db_session.commit()

    results = await retrieve_document_chunks(
        db_session,
        user_id=TEST_USER_ID,
        query="assistant search",
        filters={"company": "TraceBank"},
    )

    assert results == []
    trace = (await db_session.execute(select(RetrievalTrace))).scalar_one()
    assert trace.status == "unsupported_filters"
    assert trace.filters_json == {"company": "TraceBank"}


def test_local_retrieval_eval_artifact_is_deterministic():
    artifact = build_local_retrieval_eval_artifact()

    assert artifact["artifact"] == "local_retrieval_eval"
    assert artifact["retriever_version"] == "lexical_chunks_v1"
    assert artifact["document_count"] == 3
    assert artifact["chunk_count"] == 3
    assert artifact["metrics"]["hit_rate_at_3"] == 1.0
