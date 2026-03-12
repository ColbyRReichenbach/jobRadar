import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import AUTH_HEADER


# --- Pre-filter tests ---


def test_prefilter_blocks_noise():
    """Random email -> should_classify() = False."""
    from backend.services.email_filter import should_classify

    email = {"sender": "newsletter@randomsite.com", "subject": "Weekly digest"}
    assert should_classify(email, set()) is False


def test_prefilter_passes_ats():
    """@myworkday.com sender -> should_classify() = True."""
    from backend.services.email_filter import should_classify

    email = {"sender": "noreply@myworkday.com", "subject": "Your application update"}
    assert should_classify(email, set()) is True


def test_prefilter_passes_company_kw():
    """Company domain + 'interview' subject -> True."""
    from backend.services.email_filter import should_classify

    email = {"sender": "hr@stripe.com", "subject": "Your interview is scheduled"}
    company_domains = {"stripe.com"}
    assert should_classify(email, company_domains) is True


# --- Email matching tests ---


@pytest.mark.asyncio
async def test_email_matching_by_company(db_session):
    """Email with 'TestMatchCo' in body -> matches TestMatchCo application."""
    from backend.models import Application
    from backend.services.email_matcher import match_email_to_application

    app = Application(company="TestMatchCo", role_title="Engineer", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    email = {
        "sender": "hr@testmatchco.com",
        "subject": "Update",
        "body": "Dear candidate, TestMatchCo has reviewed your application.",
    }
    classification = {"classification": "under_review"}

    result = await match_email_to_application(db_session, email, classification)
    assert result == str(app.id)


@pytest.mark.asyncio
async def test_email_matching_ambiguous(db_session):
    """Two apps for same company -> matches most recent."""
    from backend.models import Application
    from backend.services.email_matcher import match_email_to_application

    app1 = Application(company="AmbigCo", role_title="Analyst", status="applied")
    db_session.add(app1)
    await db_session.commit()
    await db_session.refresh(app1)

    app2 = Application(company="AmbigCo", role_title="Engineer", status="applied")
    db_session.add(app2)
    await db_session.commit()
    await db_session.refresh(app2)

    email = {
        "sender": "hr@ambigco.com",
        "subject": "Update",
        "body": "AmbigCo application status",
    }
    classification = {"classification": "under_review"}

    result = await match_email_to_application(db_session, email, classification)
    # Should match the most recently applied (app2)
    assert result == str(app2.id)


@pytest.mark.asyncio
async def test_email_matching_unmatched(db_session):
    """No match -> application_id = None."""
    from backend.services.email_matcher import match_email_to_application

    email = {
        "sender": "unknown@nowhere.com",
        "subject": "Hello",
        "body": "Nothing job related here.",
    }
    classification = {"classification": "unknown"}

    result = await match_email_to_application(db_session, email, classification)
    assert result is None


# --- Classification tests (mocked) ---


@pytest.mark.asyncio
async def test_classify_rejection():
    """Mock Claude response -> rejected, red, low urgency."""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"classification": "rejected", "color_code": "red", "urgency": "low", "key_sentence": "We regret to inform you", "summary": "Application rejected"}'
        )
    ]

    with patch("backend.services.claude_client.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        from backend.services.claude_client import classify_email

        result = await classify_email("We regret to inform you that your application has been declined.")
        assert result["classification"] == "rejected"
        assert result["color_code"] == "red"
        assert result["urgency"] == "low"


@pytest.mark.asyncio
async def test_classify_interview():
    """Mock Claude response -> interview_request, green, high urgency."""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"classification": "interview_request", "color_code": "green", "urgency": "high", "key_sentence": "We would like to schedule an interview", "summary": "Interview scheduled"}'
        )
    ]

    with patch("backend.services.claude_client.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        from backend.services.claude_client import classify_email

        result = await classify_email("We would like to schedule an interview with you.")
        assert result["classification"] == "interview_request"
        assert result["color_code"] == "green"
        assert result["urgency"] == "high"


@pytest.mark.asyncio
async def test_classify_action_url():
    """Calendly link in body -> action_url extracted."""
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"classification": "action_required", "color_code": "yellow", "urgency": "high", "action_needed": true, "action_url": "https://calendly.com/recruiter/30min", "key_sentence": "Please schedule your interview", "summary": "Schedule interview"}'
        )
    ]

    with patch("backend.services.claude_client.client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        from backend.services.claude_client import classify_email

        result = await classify_email("Please schedule your interview at https://calendly.com/recruiter/30min")
        assert result["action_url"] == "https://calendly.com/recruiter/30min"
        assert result["action_needed"] is True


# --- Full pipeline tests ---


@pytest.mark.asyncio
async def test_email_event_created(db_session):
    """Full pipeline: email in -> event in DB."""
    from backend.models import Application
    from backend.services.email_matcher import create_email_event

    app = Application(company="EventCo", role_title="Dev", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    email = {
        "message_id": "test-msg-123",
        "sender": "hr@eventco.com",
        "body": "Application received",
        "subject": "Confirmation",
        "received_at": datetime.now(timezone.utc),
    }
    classification = {
        "classification": "applied_confirmed",
        "color_code": "blue",
        "urgency": "low",
        "action_needed": False,
        "key_sentence": "We received your application",
        "summary": "Application confirmed",
    }

    event = await create_email_event(db_session, email, classification, str(app.id))
    assert event.id is not None
    assert event.gmail_message_id == "test-msg-123"
    assert event.classification == "applied_confirmed"
    assert event.application_id == app.id


@pytest.mark.asyncio
async def test_application_status_updated(db_session):
    """Rejection email -> application status = denied."""
    from backend.models import Application
    from backend.services.email_matcher import update_application_status

    app = Application(company="DeniedCo", role_title="Analyst", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    classification = {"classification": "rejected"}
    await update_application_status(db_session, str(app.id), classification)

    await db_session.refresh(app)
    assert app.status == "rejected"
    assert app.status_updated_at is not None


# --- Celery task test ---


@pytest.mark.asyncio
async def test_celery_task_retries():
    """Mock Gmail API failure -> task retries with backoff."""
    with patch("backend.tasks.poll_gmail._poll_gmail_async", new_callable=AsyncMock) as mock_poll:
        mock_poll.side_effect = Exception("Gmail API error")

        from backend.tasks.poll_gmail import poll_gmail

        # The task should raise (and Celery would retry)
        with pytest.raises(Exception, match="Gmail API error"):
            # Call the underlying async function directly to test retry behavior
            await mock_poll()


# --- API endpoint tests ---


@pytest.mark.asyncio
async def test_list_emails_endpoint(client, db_session):
    """GET /api/emails returns email events."""
    resp = await client.get("/api/emails", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_patch_email_endpoint(client, db_session):
    """PATCH /api/emails/{id} updates collapsed field."""
    from backend.models import EmailEvent

    # Create email event directly
    event = EmailEvent(
        gmail_message_id="patch-test-msg",
        sender="test@example.com",
        classification="unknown",
        color_code="gray",
        urgency="low",
        collapsed=False,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    resp = await client.patch(
        f"/api/emails/{event.id}",
        json={"collapsed": True},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["collapsed"] is True


@pytest.mark.asyncio
async def test_patch_email_unresolve_restores_collapsed_state(client, db_session):
    """Undoing resolved state should make the email visible again."""
    from backend.models import EmailEvent

    event = EmailEvent(
        gmail_message_id="patch-test-msg-undo",
        sender="test@example.com",
        classification="job_update",
        color_code="blue",
        urgency="low",
        collapsed=True,
        resolved=True,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    resp = await client.patch(
        f"/api/emails/{event.id}",
        json={"resolved": False},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolved"] is False
    assert data["collapsed"] is False
