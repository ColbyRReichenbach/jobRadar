"""Sprint 12: Send emails via Gmail API."""

import base64
from datetime import datetime, timezone
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Contact, EmailEvent


async def send_email(
    db: AsyncSession,
    gmail_service,
    to: str,
    subject: str,
    body: str,
    application_id: str | None = None,
    reply_to_message_id: str | None = None,
    thread_id: str | None = None,
    user_id=None,
) -> dict:
    """Compose and send an email via Gmail API.

    Creates a local EmailEvent record with is_from_user=True.
    If replying, sets threading headers.
    """
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    # Threading for replies
    if reply_to_message_id:
        message["In-Reply-To"] = reply_to_message_id
        message["References"] = reply_to_message_id

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    send_body: dict = {"raw": raw}
    if thread_id:
        send_body["threadId"] = thread_id

    # Send via Gmail API
    sent = gmail_service.users().messages().send(
        userId="me", body=send_body
    ).execute()

    gmail_msg_id = sent.get("id", "")
    sent_thread_id = sent.get("threadId", "")

    # Extract sender name from "to" for contact matching
    sender_domain = to.split("@")[-1].lower() if "@" in to else None

    # Create local EmailEvent
    import uuid as _uuid
    event = EmailEvent(
        user_id=user_id,
        application_id=_uuid.UUID(application_id) if application_id else None,
        gmail_message_id=gmail_msg_id,
        thread_id=sent_thread_id,
        sender="Me",
        sender_email=to,  # We store the recipient since this is outbound
        subject=subject,
        body=body,
        received_at=datetime.now(timezone.utc),
        classification="conversation",
        color_code="blue",
        email_type="conversation",
        is_from_user=True,
        is_human=True,
        read=True,
        sender_domain=sender_domain,
    )
    db.add(event)

    # Upsert contact from recipient
    app_id = _uuid.UUID(application_id) if application_id else None
    contact_stmt = select(Contact).where(Contact.email == to)
    if user_id:
        contact_stmt = contact_stmt.where(Contact.user_id == user_id)
    if app_id:
        contact_stmt = contact_stmt.where(
            (Contact.application_id == app_id) | (Contact.application_id.is_(None))
        )
    contact_result = await db.execute(contact_stmt.limit(1))
    existing_contact = contact_result.scalar_one_or_none()
    if existing_contact:
        existing_contact.reached_out = True
        existing_contact.reached_out_at = datetime.now(timezone.utc)
        if app_id and not existing_contact.application_id:
            existing_contact.application_id = app_id
        event.contact_id = existing_contact.id
    else:
        contact = Contact(
            user_id=user_id,
            application_id=app_id,
            email=to,
            source="outbound",
            reached_out=True,
            reached_out_at=datetime.now(timezone.utc),
        )
        db.add(contact)

    await db.commit()
    await db.refresh(event)

    return {
        "id": str(event.id),
        "gmail_message_id": gmail_msg_id,
        "thread_id": sent_thread_id,
        "subject": subject,
        "to": to,
        "status": "sent",
    }
