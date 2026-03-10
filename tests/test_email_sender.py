"""Sprint 12: Tests for email sending."""

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
    from backend.services.email_sender import send_email

    mock_service = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "reply_msg_789", "threadId": "thread_existing"}
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send

    result = await send_email(
        db=db_session,
        gmail_service=mock_service,
        to="person@example.com",
        subject="Re: Discussion",
        body="Thanks for your reply.",
        reply_to_message_id="original_msg_id",
        thread_id="thread_existing",
    )

    assert result["thread_id"] == "thread_existing"
    # Verify the send was called with threadId
    call_args = mock_service.users().messages().send.call_args
    assert call_args[1]["body"]["threadId"] == "thread_existing"


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
        subject="Hi",
        body="Hello",
        application_id=str(app.id),
    )

    # Should still only have 1 contact
    stmt = select(Contact).where(Contact.email == "existing@nodupco.com")
    result = await db_session.execute(stmt)
    contacts = result.scalars().all()
    assert len(contacts) == 1
