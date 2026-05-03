from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select

from backend.gmail_token_crypto import encrypt_gmail_token
from tests.conftest import AUTH_HEADER, TEST_USER_ID


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
    from backend.models import Alert, EmailEvent, GmailToken, User

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
    assert network_alert.action_url == "/network?email=jamie.recruiter%40matchco.com"
    assert "Added Jamie Recruiter" in network_alert.title


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
