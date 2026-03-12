"""Sprint 12: Tests for email sending."""

import base64
import uuid
from datetime import datetime, timezone
from email import message_from_bytes

import pytest
from unittest.mock import MagicMock
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_send_email_no_gmail(client):
    """POST /api/emails/send returns 400 when Gmail not connected."""
    resp = await client.post(
        "/api/emails/send",
        json={
            "to": "someone@example.com",
            "subject": "Hello",
            "body": "Test email",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_email_rejects_invalid_recipient(client):
    """POST /api/emails/send rejects invalid or header-injection email input."""
    resp = await client.post(
        "/api/emails/send",
        json={
            "to": "victim@example.com\nBcc: attacker@example.com",
            "subject": "Hello",
            "body": "Test email",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_email_sender_service(db_session):
    """send_email creates EmailEvent and Contact records."""
    from backend.models import Application, EmailEvent, Contact
    from backend.services.email_sender import send_email
    from sqlalchemy import select

    # Create an application
    app = Application(company="SendCo", role_title="Engineer")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    # Mock Gmail service
    mock_service = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {
        "id": "sent_msg_123",
        "threadId": "thread_456",
    }
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send

    result = await send_email(
        db=db_session,
        gmail_service=mock_service,
        to="recruiter@sendco.com",
        cc=[],
        subject="Following up",
        body="Hi, just following up on my application.",
        application_id=str(app.id),
    )

    assert result["status"] == "sent"
    assert result["gmail_message_id"] == "sent_msg_123"

    # Verify EmailEvent created
    stmt = select(EmailEvent).where(EmailEvent.gmail_message_id == "sent_msg_123")
    email_result = await db_session.execute(stmt)
    event = email_result.scalar_one()
    assert event.is_from_user is True
    assert event.subject == "Following up"

    # Verify Contact created
    contact_stmt = select(Contact).where(Contact.email == "recruiter@sendco.com")
    contact_result = await db_session.execute(contact_stmt)
    contact = contact_result.scalar_one()
    assert contact.reached_out is True
    assert contact.source == "outbound"


@pytest.mark.asyncio
async def test_email_sender_threading(db_session):
    """send_email with reply_to threads correctly."""
    from backend.models import EmailEvent
    from backend.services.email_sender import send_email

    mock_service = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "reply_msg_789", "threadId": "thread_existing"}
    mock_messages = mock_service.users.return_value.messages.return_value
    mock_messages.send.return_value = mock_send
    mock_messages.get.return_value.execute.return_value = {
        "threadId": "thread_existing",
        "payload": {
            "headers": [
                {"name": "From", "value": "Recruiter <person@example.com>"},
                {"name": "To", "value": "Test User <test-user@apptrail.test>"},
                {"name": "Cc", "value": "Hiring Manager <manager@example.com>"},
                {"name": "Subject", "value": "Discussion"},
                {"name": "Message-ID", "value": "<message-123@example.com>"},
                {"name": "References", "value": "<older@example.com>"},
            ]
        },
    }

    original = EmailEvent(
        id=uuid.uuid4(),
        gmail_message_id="original_gmail_id",
        thread_id="thread_existing",
        sender="Recruiter",
        sender_email="person@example.com",
        subject="Discussion",
    )
    db_session.add(original)
    await db_session.commit()

    result = await send_email(
        db=db_session,
        gmail_service=mock_service,
        to="person@example.com",
        cc=["manager@example.com"],
        subject="Re: Discussion",
        body="Thanks for your reply.",
        reply_to_email_id=str(original.id),
        thread_id="thread_existing",
        user_email="test-user@apptrail.test",
    )

    assert result["thread_id"] == "thread_existing"
    # Verify the send was called with threadId
    call_args = mock_service.users().messages().send.call_args
    assert call_args[1]["body"]["threadId"] == "thread_existing"
    decoded = message_from_bytes(base64.urlsafe_b64decode(call_args[1]["body"]["raw"].encode()))
    assert decoded["In-Reply-To"] == "<message-123@example.com>"
    assert decoded["References"] == "<older@example.com> <message-123@example.com>"
    assert decoded["Cc"] == "manager@example.com"


@pytest.mark.asyncio
async def test_email_sender_no_duplicate_contact(db_session):
    """send_email doesn't create duplicate contact for same email."""
    from backend.models import Application, Contact
    from backend.services.email_sender import send_email
    from sqlalchemy import select

    app = Application(company="NoDupCo", role_title="PM")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    # Pre-create contact
    existing = Contact(
        application_id=app.id,
        email="existing@nodupco.com",
        source="hunter",
    )
    db_session.add(existing)
    await db_session.commit()

    mock_service = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "nodup_msg", "threadId": "t"}
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send

    await send_email(
        db=db_session,
        gmail_service=mock_service,
        to="existing@nodupco.com",
        cc=[],
        subject="Hi",
        body="Hello",
        application_id=str(app.id),
    )

    # Should still only have 1 contact
    stmt = select(Contact).where(Contact.email == "existing@nodupco.com")
    result = await db_session.execute(stmt)
    contacts = result.scalars().all()
    assert len(contacts) == 1


@pytest.mark.asyncio
async def test_reply_context_endpoint_builds_reply_all(client, db_session):
    from unittest.mock import patch

    from backend.models import EmailEvent, GmailToken
    from backend.gmail_token_crypto import encrypt_gmail_token

    gmail_token = GmailToken(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc),
    )
    event = EmailEvent(
        id=uuid.uuid4(),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        gmail_message_id="gmail-msg-1",
        thread_id="gmail-thread-1",
        sender="Recruiter",
        sender_email="recruiter@example.com",
        subject="Interview update",
        email_type="conversation",
    )
    db_session.add_all([gmail_token, event])
    await db_session.commit()

    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "threadId": "gmail-thread-1",
        "payload": {
            "headers": [
                {"name": "Reply-To", "value": "Recruiter <reply@example.com>"},
                {"name": "From", "value": "Recruiter <recruiter@example.com>"},
                {"name": "To", "value": "Test User <test-user@apptrail.test>, Coordinator <coord@example.com>"},
                {"name": "Cc", "value": "Manager <manager@example.com>"},
                {"name": "Subject", "value": "Interview update"},
                {"name": "Message-ID", "value": "<reply-context@example.com>"},
                {"name": "References", "value": "<older@example.com>"},
            ]
        },
    }

    with patch("backend.main._build_gmail_service_for_user", return_value=mock_service):
        response = await client.get(
            f"/api/emails/{event.id}/reply-context?reply_all=true",
            headers=AUTH_HEADER,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["to"] == "reply@example.com"
    assert payload["cc"] == ["coord@example.com", "manager@example.com"]
    assert payload["subject"] == "Re: Interview update"
