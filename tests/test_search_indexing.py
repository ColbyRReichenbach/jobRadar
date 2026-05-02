import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models import Application, Contact, EmailEvent, ResearchReport, SearchDocument
from backend.services.search.documents import (
    SOURCE_APPLICATION,
    SOURCE_CONTACT,
    SOURCE_EMAIL,
    SOURCE_RADAR_REPORT,
    build_email_document,
)
from backend.services.search.indexer import index_record, reindex_user_documents, search_backend_health, search_user_documents
from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_reindex_user_documents_indexes_core_surfaces(db_session):
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    app = Application(
        user_id=TEST_USER_ID,
        company="TraceBank",
        role_title="Data Scientist",
        location="Charlotte",
        status="applied",
        description_text="Build assistant search quality models and NLP evaluation workflows.",
        tech_stack=["Python", "LLM evals"],
    )
    contact = Contact(
        user_id=TEST_USER_ID,
        name="Jordan Rivera",
        title="AI Platform Lead",
        email="jordan@example.com",
        company_name="TraceBank",
    )
    email = EmailEvent(
        user_id=TEST_USER_ID,
        subject="Assistant search interview",
        sender="Jordan Rivera",
        sender_email="jordan@example.com",
        summary="Interview invitation for the assistant search data science role.",
        snippet="Interview invitation",
        body="Private raw body should not be indexed.",
        received_at=now,
        classification="interview",
        email_type="conversation",
        company_name="TraceBank",
    )
    report = ResearchReport(
        user_id=TEST_USER_ID,
        title="Assistant Search Radar",
        summary_markdown="Radar found new assistant search and NLP hiring signals.",
        report_date=now,
        status="published",
        finding_count=2,
        source_count=3,
    )
    db_session.add_all([app, contact, email, report])
    await db_session.flush()

    counts = await reindex_user_documents(db_session, user_id=TEST_USER_ID)
    await db_session.commit()

    assert counts == {
        SOURCE_APPLICATION: 1,
        SOURCE_CONTACT: 1,
        SOURCE_EMAIL: 1,
        SOURCE_RADAR_REPORT: 1,
    }
    docs = (await db_session.execute(select(SearchDocument))).scalars().all()
    assert len(docs) == 4

    results = await search_user_documents(db_session, user_id=TEST_USER_ID, query="assistant search", limit=10)
    result_types = {result.source_type for result in results}
    assert {SOURCE_APPLICATION, SOURCE_EMAIL, SOURCE_RADAR_REPORT}.issubset(result_types)

    health = await search_backend_health(db_session, user_id=TEST_USER_ID)
    assert health["backend"] == "postgres"
    assert health["document_count"] == 4
    assert health["stale_document_count"] == 0


@pytest.mark.asyncio
async def test_index_record_upserts_and_email_builder_skips_raw_body(db_session):
    email = EmailEvent(
        user_id=TEST_USER_ID,
        subject="Offer discussion",
        sender="Recruiter",
        summary="Offer discussion for the data science role.",
        body="raw-body-token-should-not-appear",
        classification="offer",
    )
    db_session.add(email)
    await db_session.flush()

    document_input = build_email_document(email)
    assert "raw-body-token-should-not-appear" not in document_input.search_text

    first = await index_record(db_session, email)
    first_hash = first.content_hash
    email.summary = "Updated offer discussion for assistant analytics."
    second = await index_record(db_session, email)
    await db_session.commit()

    docs = (await db_session.execute(select(SearchDocument))).scalars().all()
    assert len(docs) == 1
    assert second.id == first.id
    assert second.content_hash != first_hash
    assert "assistant analytics" in second.search_text
