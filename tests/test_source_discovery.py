from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_source_consent_false_blocks_shared_source_discovery(db_session):
    from backend.models import CompanyJobSource, SourceDiscoveryEvent
    from backend.services.source_intelligence.discovery import process_stored_links_for_source_discovery
    from backend.services.source_intelligence.link_store import store_user_application_link

    stored = await store_user_application_link(
        db_session,
        user_id=TEST_USER_ID,
        raw_url="https://boards.greenhouse.io/acme/jobs/123?utm_source=email",
        created_from="unit",
    )
    results = await process_stored_links_for_source_discovery(
        db_session,
        user_id=TEST_USER_ID,
        stored_links=[stored],
        discovered_from="unit",
    )

    source_count = (await db_session.execute(select(func.count(CompanyJobSource.id)))).scalar_one()
    event_count = (await db_session.execute(select(func.count(SourceDiscoveryEvent.id)))).scalar_one()

    assert results == []
    assert source_count == 0
    assert event_count == 0


@pytest.mark.asyncio
async def test_source_consent_true_creates_redacted_discovery_event(db_session):
    from backend.models import CompanyJobSource, DataConsent, SourceDiscoveryEvent
    from backend.services.source_intelligence.discovery import process_stored_links_for_source_discovery
    from backend.services.source_intelligence.link_store import store_user_application_link

    db_session.add(DataConsent(user_id=TEST_USER_ID, consent_type="source_intelligence", granted=True, granted_at=datetime.now(timezone.utc)))
    await db_session.flush()
    stored = await store_user_application_link(
        db_session,
        user_id=TEST_USER_ID,
        raw_url="https://boards.greenhouse.io/acme/jobs/123?utm_source=email&gh_src=abc",
        created_from="unit",
    )
    results = await process_stored_links_for_source_discovery(
        db_session,
        user_id=TEST_USER_ID,
        stored_links=[stored],
        discovered_from="unit",
    )
    await db_session.flush()

    source = (await db_session.execute(select(CompanyJobSource))).scalar_one()
    event = (await db_session.execute(select(SourceDiscoveryEvent))).scalar_one()
    evidence_text = str(event.redacted_evidence)

    assert results[0].source_id == source.id
    assert source.provider_type == "greenhouse"
    assert source.provider_key == "acme"
    assert event.provider_type == "greenhouse"
    assert "utm_source" not in evidence_text
    assert "gh_src" not in evidence_text
    assert "jobs/123" not in evidence_text


@pytest.mark.asyncio
async def test_source_discovery_is_idempotent(db_session):
    from backend.models import DataConsent, SourceDiscoveryEvent
    from backend.services.source_intelligence.discovery import process_stored_links_for_source_discovery
    from backend.services.source_intelligence.link_store import store_user_application_link

    db_session.add(DataConsent(user_id=TEST_USER_ID, consent_type="source_intelligence", granted=True, granted_at=datetime.now(timezone.utc)))
    await db_session.flush()
    stored = await store_user_application_link(
        db_session,
        user_id=TEST_USER_ID,
        raw_url="https://jobs.lever.co/acme/abc",
        created_from="unit",
    )

    await process_stored_links_for_source_discovery(db_session, user_id=TEST_USER_ID, stored_links=[stored], discovered_from="unit")
    await process_stored_links_for_source_discovery(db_session, user_id=TEST_USER_ID, stored_links=[stored], discovered_from="unit")

    event_count = (await db_session.execute(select(func.count(SourceDiscoveryEvent.id)))).scalar_one()

    assert event_count == 1


@pytest.mark.asyncio
async def test_reprocess_source_intelligence_is_idempotent(db_session):
    from backend.models import Application, CompanyJobSource, DataConsent, EmailEvent, SourceDiscoveryEvent, UserApplicationLink
    from backend.tasks.reprocess_source_intelligence import reprocess_source_intelligence_in_session

    db_session.add(DataConsent(user_id=TEST_USER_ID, consent_type="source_intelligence", granted=True, granted_at=datetime.now(timezone.utc)))
    app = Application(
        user_id=TEST_USER_ID,
        company="Acme",
        role_title="Engineer",
        job_url="https://boards.greenhouse.io/acme/jobs/123",
        source="manual",
    )
    email = EmailEvent(
        user_id=TEST_USER_ID,
        gmail_message_id="msg-1",
        subject="Application received",
        action_url="https://jobs.lever.co/acme/abc",
    )
    db_session.add_all([app, email])
    await db_session.flush()

    first = await reprocess_source_intelligence_in_session(db_session, TEST_USER_ID)
    second = await reprocess_source_intelligence_in_session(db_session, TEST_USER_ID)

    private_link_count = (await db_session.execute(select(func.count(UserApplicationLink.id)))).scalar_one()
    source_count = (await db_session.execute(select(func.count(CompanyJobSource.id)))).scalar_one()
    event_count = (await db_session.execute(select(func.count(SourceDiscoveryEvent.id)))).scalar_one()

    assert first["links_stored"] == 2
    assert second["links_stored"] == 2
    assert private_link_count == 2
    assert source_count == 2
    assert event_count == 2
