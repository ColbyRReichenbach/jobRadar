import base64
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select

from backend.gmail_token_crypto import encrypt_gmail_token
from tests.conftest import AUTH_HEADER, TEST_USER_ID


@pytest.mark.asyncio
async def test_gmail_sync_uses_incremental_query_after_previous_sync(client, db_session):
    from backend.models import EmailSyncAudit, GmailToken

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    previous_sync_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.add_all([
        token,
        EmailSyncAudit(
            sync_run_id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            gmail_message_id="previous-msg",
            decision="stored",
            reason="job_related",
            created_at=previous_sync_at,
        ),
    ])
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {"messages": []}

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_mode"] == "incremental"
    expected_cutoff = (previous_sync_at - timedelta(days=1)).strftime("%Y/%m/%d")
    gmail_service.users.return_value.messages.return_value.list.assert_called_once()
    assert gmail_service.users.return_value.messages.return_value.list.call_args.kwargs["q"] == f"after:{expected_cutoff}"


@pytest.mark.asyncio
async def test_gmail_sync_explicit_days_uses_lookback_query(client, db_session):
    from backend.models import EmailSyncAudit, GmailToken

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add_all([
        token,
        EmailSyncAudit(
            sync_run_id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            gmail_message_id="previous-msg",
            decision="stored",
            reason="job_related",
            created_at=datetime.now(timezone.utc) - timedelta(days=2),
        ),
    ])
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {"messages": []}

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        resp = await client.post("/api/gmail/sync?days=30", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_mode"] == "lookback"
    gmail_service.users.return_value.messages.return_value.list.assert_called_once()
    assert gmail_service.users.return_value.messages.return_value.list.call_args.kwargs["q"] == "newer_than:30d"


@pytest.mark.asyncio
async def test_gmail_sync_allows_large_dry_run_scan_limits(client, db_session):
    from backend.models import GmailToken

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {"messages": []}

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        resp = await client.post("/api/gmail/sync?days=365&max_messages=1200", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["max_messages"] == 1200
    assert body["requested_max_messages"] == 1200
    assert body["hard_max_messages"] >= 1200
    gmail_service.users.return_value.messages.return_value.list.assert_called_once()
    assert gmail_service.users.return_value.messages.return_value.list.call_args.kwargs["maxResults"] == 500


@pytest.mark.asyncio
async def test_gmail_sync_reset_clears_current_user_gmail_state(client, db_session):
    from backend.models import (
        ActionCandidate,
        Alert,
        EmailEvent,
        EmailSyncAudit,
        DocumentChunk,
        SearchDocument,
        SourceDiscoveryEvent,
        UserApplicationLink,
        UserKnowledgeDocument,
    )

    email = EmailEvent(
        user_id=TEST_USER_ID,
        gmail_message_id="reset-msg-1",
        sender="Recruiting Team",
        sender_email="jobs@example.com",
        subject="Interview request",
        body="Can you interview tomorrow?",
        classification="interview_request",
        received_at=datetime.now(timezone.utc),
    )
    db_session.add(email)
    await db_session.flush()

    db_session.add_all([
        EmailSyncAudit(
            sync_run_id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            email_event_id=email.id,
            gmail_message_id=email.gmail_message_id,
            decision="stored",
            reason="job_related",
        ),
        UserApplicationLink(
            user_id=TEST_USER_ID,
            email_event_id=email.id,
            raw_url_hash="reset-hash",
            raw_url_hash_version="test-v1",
            link_type="public_job_posting",
            sanitization_status="safe_public",
        ),
        SourceDiscoveryEvent(
            user_id=TEST_USER_ID,
            email_event_id=email.id,
            event_type="source_candidate",
        ),
        SearchDocument(
            user_id=TEST_USER_ID,
            source_type="email",
            source_id=email.id,
            title="Interview request",
            search_text="Interview request",
            content_hash="a" * 64,
        ),
        UserKnowledgeDocument(
            user_id=TEST_USER_ID,
            source_type="email",
            source_id=email.id,
            title="Interview request",
            content="Interview request",
            content_hash="b" * 64,
            chunks=[
                DocumentChunk(
                    user_id=TEST_USER_ID,
                    source_type="email",
                    source_id=email.id,
                    chunk_index=0,
                    content="Interview request",
                    token_count=2,
                    char_start=0,
                    char_end=17,
                    content_hash="c" * 64,
                )
            ],
        ),
        Alert(
            user_id=TEST_USER_ID,
            alert_type="interview_request",
            title="Interview request",
            action_url=f"/emails?email_id={email.id}",
        ),
        ActionCandidate(
            user_id=TEST_USER_ID,
            source_type="email_event",
            source_id=str(email.id),
            action_type="schedule_interview",
            target_entity_type="interview",
            target_fingerprint="interview:reset-msg-1",
            dedupe_key="reset-action-candidate",
        ),
    ])
    await db_session.commit()

    missing_confirm = await client.post("/api/gmail/sync/reset", headers=AUTH_HEADER)
    assert missing_confirm.status_code == 400

    resp = await client.post("/api/gmail/sync/reset?confirm=true", headers=AUTH_HEADER)
    assert resp.status_code == 200
    deleted = resp.json()["deleted"]
    assert deleted["email_events"] == 1
    assert deleted["email_sync_audit"] == 1
    assert deleted["user_application_links"] == 1
    assert deleted["source_discovery_events"] == 1
    assert deleted["search_documents"] == 1
    assert deleted["knowledge_documents"] == 1
    assert deleted["document_chunks"] == 1
    assert deleted["email_alerts"] == 1
    assert deleted["action_candidates"] == 1

    for model in [
        EmailEvent,
        EmailSyncAudit,
        UserApplicationLink,
        SourceDiscoveryEvent,
        SearchDocument,
        UserKnowledgeDocument,
        DocumentChunk,
        Alert,
        ActionCandidate,
    ]:
        result = await db_session.execute(select(model))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_gmail_sync_keeps_email_when_source_link_crypto_missing(client, db_session):
    from backend.models import EmailEvent, GmailToken, UserApplicationLink

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    html = '<a href="https://boards.greenhouse.io/acme/jobs/123?utm_source=email">View job</a>'
    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "sync-msg-missing-source-crypto"}]
    }
    gmail_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "thread-missing-source-crypto",
        "snippet": "Application update",
        "payload": {
            "mimeType": "text/html",
            "headers": [
                {"name": "From", "value": "Recruiting Team <jobs@acme.com>"},
                {"name": "Subject", "value": "Application update"},
                {"name": "Date", "value": "Wed, 11 Mar 2026 10:00:00 +0000"},
            ],
            "body": {"data": base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")},
        },
    }

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        with patch(
            "backend.services.email_parser.parse_email_body",
            return_value="We received your application.",
        ):
            with patch(
                "backend.services.email_classifier.classify_email",
                new=AsyncMock(return_value={
                    "classification": "job_update",
                    "action_needed": False,
                    "summary": "Application update",
                    "confidence": 0.85,
                }),
            ):
                with patch(
                    "backend.services.source_intelligence.link_store.hash_source_link",
                    side_effect=RuntimeError("SOURCE_LINK_HASH_KEY is required for source-link hashing"),
                ):
                    resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["new_emails"] == 1
    assert body["stats"]["source_link_errors"] == 1

    event_result = await db_session.execute(
        select(EmailEvent).where(EmailEvent.gmail_message_id == "sync-msg-missing-source-crypto")
    )
    assert event_result.scalar_one_or_none() is not None

    link_result = await db_session.execute(select(UserApplicationLink))
    assert link_result.scalars().all() == []


@pytest.mark.asyncio
async def test_gmail_sync_keeps_email_when_search_indexing_fails(client, db_session):
    from backend.models import EmailEvent, GmailToken

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "sync-msg-index-fail"}]
    }
    gmail_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "thread-index-fail",
        "snippet": "Application update",
        "payload": {
            "headers": [
                {"name": "From", "value": "Recruiting Team <jobs@acme.com>"},
                {"name": "Subject", "value": "Application update"},
                {"name": "Date", "value": "Wed, 11 Mar 2026 10:00:00 +0000"},
            ],
            "body": {"data": ""},
        },
    }

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        with patch(
            "backend.services.email_parser.parse_email_body",
            return_value="We received your application.",
        ):
            with patch(
                "backend.services.email_classifier.classify_email",
                new=AsyncMock(return_value={
                    "classification": "job_update",
                    "action_needed": False,
                    "summary": "Application update",
                    "confidence": 0.85,
                }),
            ):
                with patch(
                    "backend.services.search.indexer.index_record",
                    new=AsyncMock(side_effect=RuntimeError("index down")),
                ):
                    resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["new_emails"] == 1
    assert body["stats"]["index_errors"] == 1

    event_result = await db_session.execute(
        select(EmailEvent).where(EmailEvent.gmail_message_id == "sync-msg-index-fail")
    )
    assert event_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_gmail_sync_matches_application_by_company_domain(client, db_session):
    from backend.models import Application, Company, EmailEvent, GmailToken

    company = Company(domain="matchco.com", name="MatchCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app = Application(
        user_id=TEST_USER_ID,
        company="Match Co",
        role_title="Engineer",
        company_id=company.id,
    )
    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add_all([app, token])
    await db_session.commit()
    await db_session.refresh(app)

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "sync-msg-1"}]
    }
    gmail_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "thread-1",
        "snippet": "Interview update",
        "payload": {
            "headers": [
                {"name": "From", "value": "Recruiter <recruiter@matchco.com>"},
                {"name": "Subject", "value": "Interview update"},
                {"name": "Date", "value": "Wed, 11 Mar 2026 10:00:00 +0000"},
            ],
            "body": {"data": ""},
        },
    }

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        with patch(
            "backend.services.email_parser.parse_email_body",
            return_value="Thanks for your application.",
        ):
            with patch(
                "backend.services.email_classifier.classify_email",
                new=AsyncMock(return_value={
                    "classification": "interview",
                    "action_needed": False,
                    "summary": "Interview update",
                    "confidence": 0.95,
                }),
            ):
                with patch(
                    "backend.services.company_identity.get_company_info",
                    return_value={"company_name": "MatchCo", "logo_url": None},
                ):
                    resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["new_emails"] == 1

    event_result = await db_session.execute(select(EmailEvent).where(EmailEvent.gmail_message_id == "sync-msg-1"))
    event = event_result.scalar_one()
    assert event.application_id == app.id


@pytest.mark.asyncio
async def test_gmail_sync_skips_obvious_tooling_noise(client, db_session):
    from backend.models import EmailEvent, EmailSyncAudit, GmailToken

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "sync-msg-noise-1"}]
    }
    gmail_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "thread-noise-1",
        "snippet": "Build failed",
        "payload": {
            "headers": [
                {"name": "From", "value": "Railway <hello@notify.railway.app>"},
                {"name": "Subject", "value": "Build failed for AppTrail"},
                {"name": "Date", "value": "Wed, 11 Mar 2026 10:00:00 +0000"},
            ],
            "body": {"data": ""},
        },
    }

    classifier = AsyncMock(return_value={"classification": "job_update"})

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        with patch(
            "backend.services.email_parser.parse_email_body",
            return_value="One of your builds failed to leave the wheelhouse. View build logs.",
        ):
            with patch("backend.services.email_classifier.classify_email", new=classifier):
                resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["new_emails"] == 0
    assert resp.json()["stats"]["skipped_noise"] == 1
    classifier.assert_not_awaited()

    event_result = await db_session.execute(select(EmailEvent).where(EmailEvent.gmail_message_id == "sync-msg-noise-1"))
    assert event_result.scalar_one_or_none() is None
    audit_result = await db_session.execute(
        select(EmailSyncAudit).where(EmailSyncAudit.gmail_message_id == "sync-msg-noise-1")
    )
    audit = audit_result.scalar_one()
    assert audit.decision == "skipped"
    assert audit.reason == "obvious_noise"
    audit_resp = await client.get("/api/gmail/sync/audit", headers=AUTH_HEADER)
    assert audit_resp.status_code == 200
    assert audit_resp.json()[0]["gmail_message_id"] == "sync-msg-noise-1"


@pytest.mark.asyncio
async def test_gmail_sync_does_not_hard_block_real_employer_domains(client, db_session):
    from backend.models import EmailEvent, GmailToken

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "sync-msg-amazon-1"}]
    }
    gmail_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "thread-amazon-1",
        "snippet": "Interview invite",
        "payload": {
            "headers": [
                {"name": "From", "value": "Jane Recruiter <jane@amazon.com>"},
                {"name": "Subject", "value": "Schedule your interview"},
                {"name": "Date", "value": "Wed, 11 Mar 2026 10:00:00 +0000"},
            ],
            "body": {"data": ""},
        },
    }

    classifier = AsyncMock(
        return_value={
            "classification": "interview_request",
            "action_needed": True,
            "summary": "Interview scheduling email",
            "confidence": 0.95,
        }
    )

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        with patch(
            "backend.services.email_parser.parse_email_body",
            return_value="Please choose a time for your Software Engineer interview next week.",
        ):
            with patch("backend.services.email_classifier.classify_email", new=classifier):
                with patch(
                    "backend.services.company_identity.get_company_info",
                    return_value={"company_name": "Amazon", "logo_url": None},
                ):
                    resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["new_emails"] == 1
    classifier.assert_awaited()

    event_result = await db_session.execute(select(EmailEvent).where(EmailEvent.gmail_message_id == "sync-msg-amazon-1"))
    assert event_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_gmail_sync_creates_actionable_alerts_for_new_conversation(client, db_session):
    from backend.models import ActionCandidate, Alert, EmailEvent, GmailToken, User

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    user_result = await db_session.execute(select(User).where(User.id == TEST_USER_ID))
    user = user_result.scalar_one()
    user.notifications_started_at = datetime.now(timezone.utc)
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "sync-msg-convo-1"}]
    }
    gmail_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "thread-convo-1",
        "snippet": "Can you chat this week?",
        "payload": {
            "headers": [
                {"name": "From", "value": "Jamie Recruiter <jamie.recruiter@matchco.com>"},
                {"name": "Subject", "value": "Quick follow up"},
                {"name": "Date", "value": "Wed, 11 Mar 2026 10:00:00 +0000"},
            ],
            "body": {"data": ""},
        },
    }

    classifier = AsyncMock(
        return_value={
            "classification": "conversation",
            "action_needed": True,
            "summary": "Recruiter follow-up asking to chat this week.",
            "confidence": 0.93,
            "is_automated": False,
        }
    )

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        with patch(
            "backend.services.email_parser.parse_email_body",
            return_value="Great speaking with you. Can you chat this week about next steps?",
        ):
            with patch("backend.services.email_classifier.classify_email", new=classifier):
                with patch(
                    "backend.services.company_identity.get_company_info",
                    return_value={"company_name": "MatchCo", "logo_url": None},
                ):
                    resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["new_emails"] == 1

    event_result = await db_session.execute(
        select(EmailEvent).where(EmailEvent.gmail_message_id == "sync-msg-convo-1")
    )
    event = event_result.scalar_one()

    alert_result = await db_session.execute(
        select(Alert)
        .where(Alert.user_id == TEST_USER_ID)
        .order_by(Alert.created_at.asc())
    )
    alerts = alert_result.scalars().all()

    assert len(alerts) == 2

    email_alert = next(alert for alert in alerts if alert.alert_type == "conversation_message")
    assert email_alert.action_url == f"/conversations?tab=conversations&email_id={event.id}&thread_id=thread-convo-1"
    assert "Jamie Recruiter" in email_alert.title

    network_alert = next(alert for alert in alerts if alert.alert_type == "network_contact")
    assert network_alert.action_url == f"/conversations?tab=conversations&email_id={event.id}&thread_id=thread-convo-1"
    assert "Suggested contact: Jamie Recruiter" in network_alert.title
    assert network_alert.action_candidate_id is not None

    candidate = (await db_session.execute(select(ActionCandidate))).scalar_one()
    assert network_alert.action_candidate_id == candidate.id
    assert candidate.action_type == "add_network_contact"
    assert candidate.status == "proposed"
    assert candidate.requires_confirmation is True


@pytest.mark.asyncio
async def test_first_gmail_sync_enables_notifications_without_backfilling_alerts(client, db_session):
    from backend.models import Alert, GmailToken, User

    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(token)
    await db_session.commit()

    gmail_service = Mock()
    gmail_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "sync-msg-first-1"}]
    }
    gmail_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "thread-first-1",
        "snippet": "Application update",
        "payload": {
            "headers": [
                {"name": "From", "value": "Recruiting Team <jobs@matchco.com>"},
                {"name": "Subject", "value": "Application update"},
                {"name": "Date", "value": "Wed, 11 Mar 2026 10:00:00 +0000"},
            ],
            "body": {"data": ""},
        },
    }

    with patch("googleapiclient.discovery.build", return_value=gmail_service):
        with patch(
            "backend.services.email_parser.parse_email_body",
            return_value="We received your application and will be in touch soon.",
        ):
            with patch(
                "backend.services.email_classifier.classify_email",
                new=AsyncMock(return_value={
                    "classification": "job_update",
                    "action_needed": False,
                    "summary": "Application update",
                    "confidence": 0.85,
                }),
            ):
                with patch(
                    "backend.services.company_identity.get_company_info",
                    return_value={"company_name": "MatchCo", "logo_url": None},
                ):
                    resp = await client.post("/api/gmail/sync", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["new_emails"] == 1

    alert_result = await db_session.execute(select(Alert).where(Alert.user_id == TEST_USER_ID))
    assert alert_result.scalars().all() == []

    user_result = await db_session.execute(select(User).where(User.id == TEST_USER_ID))
    user = user_result.scalar_one()
    assert user.notifications_started_at is not None
