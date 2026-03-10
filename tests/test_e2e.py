"""Full end-to-end integration test for AppTrail pipeline."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_full_pipeline(client, db_session):
    """E2E: parse job -> create app -> find contacts -> rejection email -> status denied."""

    # 1. Parse a Greenhouse job (mocked to avoid live API dependency)
    mock_job_data = {
        "title": "Data Analyst",
        "company": "E2ECorp",
        "location": "Remote",
        "department": "Data",
        "description": "Analyze data for insights at E2ECorp.",
    }
    with patch("backend.main.extract_job", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = mock_job_data
        parse_resp = await client.post(
            "/api/jobs/parse",
            json={"url": "https://boards.greenhouse.io/e2ecorp/jobs/123"},
            headers=AUTH_HEADER,
        )
        assert parse_resp.status_code == 200
        parsed = parse_resp.json()
        assert parsed["data"]["company"] == "E2ECorp"

    # 2. Create application record
    create_resp = await client.post(
        "/api/jobs",
        json={
            "company": "E2ECorp",
            "role_title": "Data Analyst",
            "job_url": "https://boards.greenhouse.io/e2ecorp/jobs/123",
            "source": "greenhouse",
            "department": "Data",
        },
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201
    app_data = create_resp.json()
    app_id = app_data["id"]
    assert app_data["status"] == "saved"

    # 3. Find Hunter.io contacts (mocked)
    mock_hunter_response = {
        "data": {
            "emails": [
                {
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "value": "jane@e2ecorp.com",
                    "position": "Data Lead",
                    "department": "data",
                    "seniority": "senior",
                    "confidence": 92,
                }
            ]
        }
    }

    with patch("backend.services.hunter.HUNTER_API_KEY", "test-key"):
        with patch("backend.services.hunter.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = mock_hunter_response
            contacts_resp = await client.post(
                "/api/contacts/find",
                json={
                    "application_id": app_id,
                    "company": "E2ECorp",
                    "domain": "e2ecorp.com",
                },
                headers=AUTH_HEADER,
            )
            assert contacts_resp.status_code == 200
            contacts_data = contacts_resp.json()
            assert len(contacts_data["contacts"]) == 1
            assert contacts_data["contacts"][0]["name"] == "Jane Doe"

    # 4. Simulate incoming rejection email
    email = {
        "message_id": "e2e-rejection-msg-001",
        "sender": "noreply@myworkday.com",
        "subject": "Application Update from E2ECorp",
        "body": "Dear candidate, we regret to inform you that E2ECorp has decided not to move forward with your application for the Data Analyst position. We appreciate your interest.",
        "received_at": datetime.now(timezone.utc),
    }

    # 5. Pre-filter: ATS domain should pass
    from backend.services.email_filter import should_classify

    assert should_classify(email, set()) is True  # myworkday.com is ATS

    # 6. Classify with Claude (mocked)
    mock_classification = {
        "classification": "rejected",
        "color_code": "red",
        "urgency": "low",
        "action_needed": False,
        "key_sentence": "We regret to inform you",
        "summary": "Application rejected for Data Analyst at E2ECorp",
    }

    with patch("backend.services.claude_client.client") as mock_client:
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"classification": "rejected", "color_code": "red", "urgency": "low", "action_needed": false, "key_sentence": "We regret to inform you", "summary": "Application rejected for Data Analyst at E2ECorp"}')
        ]
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        from backend.services.claude_client import classify_email

        result = await classify_email(email["body"])
        assert result["classification"] == "rejected"
        assert result["color_code"] == "red"

    # 7. Match email to application
    from backend.services.email_matcher import (
        create_email_event,
        match_email_to_application,
        update_application_status,
    )

    matched_id = await match_email_to_application(db_session, email, mock_classification)
    assert matched_id == app_id

    # 8-9. Create email event + confirm status = denied
    event = await create_email_event(db_session, email, mock_classification, matched_id)
    assert event.classification == "rejected"
    assert event.color_code == "red"
    assert event.gmail_message_id == "e2e-rejection-msg-001"

    await update_application_status(db_session, matched_id, mock_classification)

    # Verify application status updated
    from backend.models import Application

    from sqlalchemy import select

    stmt = select(Application).where(Application.id == uuid.UUID(app_id))
    result = await db_session.execute(stmt)
    updated_app = result.scalar_one()

    assert updated_app.status == "rejected"
    assert updated_app.status_updated_at is not None

    # 10. Confirm archived_at set 30 days in future
    assert updated_app.archived_at is not None
    archived = updated_app.archived_at
    now = datetime.now(timezone.utc)
    # SQLite may return naive datetime - make both aware for comparison
    if archived.tzinfo is None:
        archived = archived.replace(tzinfo=timezone.utc)
    days_until_archive = (archived - now).days
    assert 29 <= days_until_archive <= 30
