from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select

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
        access_token="access-token",
        refresh_token="refresh-token",
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
