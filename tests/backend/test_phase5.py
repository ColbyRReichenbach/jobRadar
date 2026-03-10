"""Phase 5A: Email Intelligence — classifier, parser, company identity, feedback."""
import base64
import json

import pytest
from httpx import AsyncClient

from tests.conftest import AUTH_HEADER


# --- Email Parser Tests ---

def test_parse_plain_text_body():
    from backend.services.email_parser import parse_email_body

    payload = {
        "mimeType": "text/plain",
        "body": {
            "data": base64.urlsafe_b64encode(b"Hello, you have an interview!").decode()
        },
    }
    result = parse_email_body(payload)
    assert "interview" in result


def test_parse_multipart_prefers_plain():
    from backend.services.email_parser import parse_email_body

    plain_data = base64.urlsafe_b64encode(b"Plain text content").decode()
    html_data = base64.urlsafe_b64encode(b"<html><body><b>HTML content</b></body></html>").decode()

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": plain_data}},
            {"mimeType": "text/html", "body": {"data": html_data}},
        ],
    }
    result = parse_email_body(payload)
    assert result == "Plain text content"


def test_parse_html_fallback():
    from backend.services.email_parser import parse_email_body

    html_data = base64.urlsafe_b64encode(
        b"<html><body><p>Interview scheduled</p><p>Please confirm</p></body></html>"
    ).decode()

    payload = {
        "mimeType": "text/html",
        "body": {"data": html_data},
    }
    result = parse_email_body(payload)
    assert "Interview scheduled" in result
    assert "Please confirm" in result
    assert "<html>" not in result


def test_parse_nested_multipart():
    from backend.services.email_parser import parse_email_body

    plain_data = base64.urlsafe_b64encode(b"Nested plain text").decode()

    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": plain_data}},
                    {"mimeType": "text/html", "body": {"data": ""}},
                ],
            },
            {"mimeType": "application/pdf", "body": {"data": ""}},
        ],
    }
    result = parse_email_body(payload)
    assert result == "Nested plain text"


def test_strip_signature():
    from backend.services.email_parser import strip_signature

    text = "Hey, we'd like to schedule an interview.\n\n--\nJohn Doe\nRecruiter at Stripe"
    result = strip_signature(text)
    assert "schedule an interview" in result
    assert "John Doe" not in result


def test_strip_quoted_reply():
    from backend.services.email_parser import strip_signature

    text = "Thanks for applying!\n\n> On Mar 5, you wrote:\n> Hi, I'm interested in the role"
    result = strip_signature(text)
    assert "Thanks for applying" in result
    assert "interested in the role" not in result


def test_extract_sender_parts():
    from backend.services.email_parser import extract_sender_parts

    name, email = extract_sender_parts('"Jane Smith" <jane@stripe.com>')
    assert name == "Jane Smith"
    assert email == "jane@stripe.com"

    name2, email2 = extract_sender_parts("noreply@greenhouse.io")
    assert email2 == "noreply@greenhouse.io"

    name3, email3 = extract_sender_parts("John Doe <john@example.com>")
    assert name3 == "John Doe"
    assert email3 == "john@example.com"


# --- Company Identity Tests ---

def test_company_identity_from_email():
    from backend.services.company_identity import get_company_info

    info = get_company_info("recruiter@stripe.com")
    assert info["company_name"] == "Stripe"
    assert info["logo_url"] == "https://logo.clearbit.com/stripe.com"
    assert info["is_company"] is True


def test_company_identity_platform_domain():
    from backend.services.company_identity import get_company_info

    info = get_company_info("noreply@greenhouse.io")
    assert info["company_name"] is None
    assert info["logo_url"] is None
    assert info["is_company"] is False


def test_company_identity_unknown_company():
    from backend.services.company_identity import get_company_info

    info = get_company_info("hr@acmecorp.com")
    assert info["company_name"] == "Acmecorp"
    assert info["logo_url"] == "https://logo.clearbit.com/acmecorp.com"
    assert info["is_company"] is True


def test_company_identity_gmail():
    from backend.services.company_identity import get_company_info

    info = get_company_info("someone@gmail.com")
    assert info["is_company"] is False


def test_extract_domain():
    from backend.services.company_identity import extract_domain

    assert extract_domain("user@stripe.com") == "stripe.com"
    assert extract_domain("someone@sub.domain.co.uk") == "sub.domain.co.uk"
    assert extract_domain("") == ""
    assert extract_domain("nodomain") == ""


# --- Email Classifier Tests ---

def test_fallback_classify_interview():
    from backend.services.email_classifier import _fallback_classify

    result = _fallback_classify(
        "Interview Scheduled - Software Engineer",
        "We'd like to schedule an interview...",
        "recruiter@stripe.com"
    )
    assert result["classification"] == "interview_request"
    assert result["action_needed"] is True


def test_fallback_classify_rejection():
    from backend.services.email_classifier import _fallback_classify

    result = _fallback_classify(
        "Your application update",
        "Unfortunately, we have decided not to move forward with your application.",
        "noreply@greenhouse.io"
    )
    assert result["classification"] == "rejection"


def test_fallback_classify_offer():
    from backend.services.email_classifier import _fallback_classify

    result = _fallback_classify(
        "Offer Letter - Senior Engineer",
        "We are pleased to offer you...",
        "hr@company.com"
    )
    assert result["classification"] == "offer"
    assert result["action_needed"] is True


def test_fallback_classify_action():
    from backend.services.email_classifier import _fallback_classify

    result = _fallback_classify(
        "Action Required: Complete Assessment",
        "Please complete the coding assessment by...",
        "talent@company.com"
    )
    assert result["classification"] == "action_item"
    assert result["action_needed"] is True


def test_fallback_classify_automated():
    from backend.services.email_classifier import _fallback_classify

    result = _fallback_classify(
        "Application Received",
        "Thank you for your application.",
        "noreply@company.com"
    )
    assert result["is_automated"] is True


def test_classification_mappings():
    from backend.services.email_classifier import (
        CLASSIFICATION_TO_FRONTEND,
        CLASSIFICATION_TO_COLOR,
        CLASSIFICATION_TO_EMAIL_TYPE,
    )

    assert CLASSIFICATION_TO_FRONTEND["interview_request"] == "interview"
    assert CLASSIFICATION_TO_FRONTEND["rejection"] == "rejection"
    assert CLASSIFICATION_TO_FRONTEND["offer"] == "action_item"
    assert CLASSIFICATION_TO_COLOR["interview_request"] == "green"
    assert CLASSIFICATION_TO_COLOR["rejection"] == "red"
    assert CLASSIFICATION_TO_EMAIL_TYPE["conversation"] == "conversation"
    assert CLASSIFICATION_TO_EMAIL_TYPE["not_relevant"] is None


# --- Email Feedback Endpoint Tests ---

@pytest.mark.anyio
async def test_email_feedback_not_job_related(client: AsyncClient, db_session):
    """Test marking an email as not job related."""
    from backend.models import EmailEvent
    from datetime import datetime, timezone

    event = EmailEvent(
        gmail_message_id="feedback-test-1",
        sender="GitHub",
        sender_email="noreply@github.com",
        subject="New commit on main",
        body="A commit was pushed to main branch",
        received_at=datetime.now(timezone.utc),
        classification="update",
        sender_domain="github.com",
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    response = await client.post("/api/emails/feedback", headers=AUTH_HEADER, json={
        "email_id": str(event.id),
        "is_job_related": False,
    })
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"

    # Verify event was collapsed
    await db_session.refresh(event)
    assert event.collapsed is True
    assert event.classification == "not_relevant"


@pytest.mark.anyio
async def test_pipeline_check_not_in_pipeline(client: AsyncClient, db_session):
    """Test pipeline check for email from company not in pipeline."""
    from backend.models import EmailEvent
    from datetime import datetime, timezone

    event = EmailEvent(
        gmail_message_id="pipeline-test-1",
        sender="HR Team",
        sender_email="hr@newcompany.com",
        subject="Interview Invitation",
        body="We'd like to schedule an interview",
        received_at=datetime.now(timezone.utc),
        classification="interview_request",
        company_name="Newcompany",
        sender_domain="newcompany.com",
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    response = await client.get(f"/api/emails/{event.id}/pipeline-check", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["in_pipeline"] is False
    assert "Newcompany" in data["suggestion"]


@pytest.mark.anyio
async def test_pipeline_check_in_pipeline(client: AsyncClient, db_session):
    """Test pipeline check for email already linked to application."""
    from backend.models import Application, EmailEvent
    from datetime import datetime, timezone

    app = Application(company="TestCo", role_title="Engineer")
    db_session.add(app)
    await db_session.flush()

    event = EmailEvent(
        application_id=app.id,
        gmail_message_id="pipeline-test-2",
        sender="HR",
        sender_email="hr@testco.com",
        subject="Update",
        received_at=datetime.now(timezone.utc),
        classification="update",
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    response = await client.get(f"/api/emails/{event.id}/pipeline-check", headers=AUTH_HEADER)
    assert response.status_code == 200
    data = response.json()
    assert data["in_pipeline"] is True
