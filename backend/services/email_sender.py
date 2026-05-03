"""Sprint 12: Send emails via Gmail API."""

import base64
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Contact, EmailEvent

REPLY_CONTEXT_HEADERS = [
    "From",
    "Reply-To",
    "To",
    "Cc",
    "Subject",
    "Message-ID",
    "References",
]


def _header_lookup(message: dict) -> dict[str, str]:
    headers = message.get("payload", {}).get("headers", []) or []
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in headers
        if header.get("name")
    }


def _parse_addresses(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    seen: set[str] = set()
    addresses: list[str] = []
    for _, email in getaddresses([raw_value]):
        normalized = email.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        addresses.append(normalized)
    return addresses


def _normalize_reply_subject(subject: str | None) -> str:
    clean_subject = (subject or "").strip()
    if clean_subject.lower().startswith("re:"):
        return clean_subject
    return f"Re: {clean_subject}" if clean_subject else "Re:"


def _fetch_gmail_message_metadata(gmail_service, gmail_message_id: str | None) -> dict:
    if not gmail_message_id:
        return {}
    return (
        gmail_service.users()
        .messages()
        .get(
            userId="me",
            id=gmail_message_id,
            format="metadata",
            metadataHeaders=REPLY_CONTEXT_HEADERS,
        )
        .execute()
    )


async def build_reply_context(
    *,
    gmail_service,
    event: EmailEvent,
    user_email: str,
    reply_all: bool = False,
) -> dict:
    gmail_message = _fetch_gmail_message_metadata(gmail_service, event.gmail_message_id)
    headers = _header_lookup(gmail_message)

    from_addrs = _parse_addresses(headers.get("reply-to") or headers.get("from"))
    to_addrs = _parse_addresses(headers.get("to"))
    cc_addrs = _parse_addresses(headers.get("cc"))
    self_emails = {user_email.strip().lower()} if user_email else set()

    primary_candidates = [addr for addr in from_addrs if addr not in self_emails]
    if not primary_candidates:
        primary_candidates = [addr for addr in to_addrs if addr not in self_emails]
    if not primary_candidates and event.sender_email:
        primary_candidates = [event.sender_email.strip().lower()]

    primary_to = primary_candidates[0] if primary_candidates else ""

    cc: list[str] = []
    if reply_all:
        seen = {primary_to} if primary_to else set()
        for addr in [*to_addrs, *cc_addrs, *from_addrs]:
            if not addr or addr in self_emails or addr in seen:
                continue
            seen.add(addr)
            cc.append(addr)

    message_id_header = headers.get("message-id", "").strip()
    references_header = headers.get("references", "").strip()
    references_parts = [part for part in references_header.split() if part]
    if message_id_header and message_id_header not in references_parts:
        references_parts.append(message_id_header)

    subject = _normalize_reply_subject(headers.get("subject") or event.subject)

    return {
        "to": primary_to,
        "cc": cc,
        "subject": subject,
        "thread_id": gmail_message.get("threadId") or event.thread_id,
        "in_reply_to": message_id_header,
        "references": " ".join(references_parts),
        "reply_to_email_id": str(event.id),
    }


async def send_email(
    db: AsyncSession,
    gmail_service,
    to: str,
    cc: list[str] | None,
    subject: str,
    body: str,
    application_id: str | None = None,
    reply_to_email_id: str | None = None,
    reply_to_message_id: str | None = None,
    thread_id: str | None = None,
    user_email: str | None = None,
    user_id=None,
) -> dict:
    """Compose and send an email via Gmail API.

    Creates a local EmailEvent record with is_from_user=True.
    If replying, sets threading headers.
    """
    message = EmailMessage()
    message["to"] = to
    if cc:
        message["cc"] = ", ".join(cc)
    message["subject"] = subject

    reply_context: dict[str, str] = {}
    original_event: EmailEvent | None = None
    if reply_to_email_id:
        import uuid as _uuid

        original_event = await db.get(EmailEvent, _uuid.UUID(reply_to_email_id))
    elif reply_to_message_id:
        original_event_result = await db.execute(
            select(EmailEvent).where(EmailEvent.gmail_message_id == reply_to_message_id)
        )
        original_event = original_event_result.scalar_one_or_none()

    if original_event and user_email:
        reply_context = await build_reply_context(
            gmail_service=gmail_service,
            event=original_event,
            user_email=user_email,
            reply_all=bool(cc),
        )
        thread_id = thread_id or reply_context.get("thread_id")

    in_reply_to = reply_context.get("in_reply_to")
    references = reply_context.get("references")
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references

    message.set_content(body)

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
    contact_to_index = existing_contact
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
        contact_to_index = contact

    await db.flush()
    from backend.services.search.indexer import index_record
    await index_record(db, event)
    if contact_to_index:
        await index_record(db, contact_to_index)
    await db.commit()
    await db.refresh(event)

    return {
        "id": str(event.id),
        "gmail_message_id": gmail_msg_id,
        "thread_id": sent_thread_id,
        "subject": subject,
        "to": to,
        "cc": cc or [],
        "status": "sent",
        "application_id": str(event.application_id) if event.application_id else None,
        "sender": event.sender,
        "sender_email": event.sender_email,
        "body": event.body,
        "snippet": event.snippet,
        "received_at": event.received_at.isoformat() if event.received_at else None,
        "classification": event.classification,
        "email_type": event.email_type,
        "is_from_user": event.is_from_user,
        "company_name": event.company_name,
        "sender_domain": event.sender_domain,
    }
