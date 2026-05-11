import asyncio
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import select

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


async def _track_contact_response(db, sender_email: str, user_id):
    """If sender matches a contact's email, mark response_received=True."""
    from backend.models import Contact

    if not sender_email:
        return
    email_match = re.search(r'<([^>]+)>', sender_email)
    clean_email = email_match.group(1) if email_match else sender_email

    stmt = select(Contact).where(
        Contact.email == clean_email,
        Contact.user_id == user_id,
    )
    result = await db.execute(stmt)
    contacts = result.scalars().all()
    for contact in contacts:
        if not contact.response_received:
            contact.response_received = True
    if contacts:
        await db.commit()


async def _get_feedback_blocklist(db, user_id) -> set[str]:
    """Get sender domains that the user has marked as not job-related."""
    from backend.models import EmailEvent, EmailFeedback

    stmt = select(EmailFeedback.sender_domain).join(
        EmailEvent,
        EmailFeedback.email_id == EmailEvent.id,
    ).where(
        EmailEvent.user_id == user_id,
        EmailFeedback.is_job_related.is_(False),
        EmailFeedback.sender_domain.isnot(None),
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


async def _poll_gmail_async():
    from googleapiclient.discovery import build

    from backend.database import async_session_factory
    from backend.services.company_identity import extract_domain, get_company_info
    from backend.services.email_classifier import (
        CLASSIFICATION_TO_COLOR,
        classify_email,
        email_type_for_classifier_result,
        should_store_classifier_result,
    )
    from backend.services.email_parser import extract_sender_parts, parse_email_body
    from backend.services.source_intelligence.discovery import process_stored_links_for_source_discovery
    from backend.services.source_intelligence.link_store import store_many_user_application_links
    from backend.services.source_intelligence.url_classifier import extract_urls_from_gmail_payload
    from backend.services.email_classification_traces import create_email_classification_trace
    from backend.services.email_matcher import (
        STATUS_UPDATES,
        email_already_processed,
        get_active_company_domains,
        match_email_to_application,
        update_application_status,
    )
    from backend.services.gmail_auth import get_valid_token
    from backend.services.search.indexer import index_record
    from backend.models import EmailEvent, GmailToken, User

    async with async_session_factory() as db:
        token_stmt = (
            select(GmailToken, User)
            .join(User, GmailToken.user_id == User.id)
            .where(GmailToken.user_id.isnot(None))
        )
        token_result = await db.execute(token_stmt)
        token_rows = token_result.all()

        if not token_rows:
            logger.info("No Gmail-connected users found")
            return 0

        total_processed = 0
        total_skipped_feedback = 0

        for gmail_token, user in token_rows:
            from backend.dependencies import check_ai_consent
            ai_enabled = await check_ai_consent(user.id, db)

            creds = await get_valid_token(db, user_id=user.id)
            service = build("gmail", "v1", credentials=creds)

            results = (
                service.users()
                .messages()
                .list(userId="me", q="newer_than:1d", maxResults=50)
                .execute()
            )
            messages = results.get("messages", [])

            if not messages:
                continue

            company_domains = await get_active_company_domains(db, user_id=user.id)
            feedback_blocklist = await _get_feedback_blocklist(db, user.id)
            processed = 0
            skipped_feedback = 0

            for msg_ref in messages:
                msg_id = msg_ref["id"]

                if await email_already_processed(db, msg_id, user.id):
                    continue

                full_msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )

                headers = full_msg.get("payload", {}).get("headers", [])
                from_header = _get_header(headers, "From")
                subject = _get_header(headers, "Subject")
                date_str = _get_header(headers, "Date")

                sender_name, sender_email = extract_sender_parts(from_header)
                sender_domain = extract_domain(sender_email)

                if sender_domain in feedback_blocklist:
                    skipped_feedback += 1
                    continue

                received_at = datetime.now(timezone.utc)
                if date_str:
                    try:
                        received_at = parsedate_to_datetime(date_str)
                        if received_at.tzinfo is None:
                            received_at = received_at.replace(tzinfo=timezone.utc)
                    except Exception:
                        pass

                gmail_payload = full_msg.get("payload", {})
                raw_candidate_urls = extract_urls_from_gmail_payload(gmail_payload)
                body = parse_email_body(gmail_payload)

                await _track_contact_response(db, sender_email, user.id)

                classification = await classify_email(
                    subject=subject,
                    body=body,
                    sender=sender_name,
                    sender_email=sender_email,
                    ai_enabled=ai_enabled,
                    raw_candidate_urls=tuple(raw_candidate_urls),
                )

                if not should_store_classifier_result(classification):
                    await create_email_classification_trace(
                        db,
                        user_id=user.id,
                        classification=classification,
                        gmail_message_id=msg_id,
                        candidate_source_url_count=len(raw_candidate_urls),
                    )
                    continue

                company_info = get_company_info(sender_email, include_logo=False)
                email_company_name = (
                    classification.get("company_name")
                    or company_info.get("company_name")
                )

                email_dict = {
                    "message_id": msg_id,
                    "sender": from_header,
                    "subject": subject,
                    "body": body,
                    "received_at": received_at,
                    "company_domains": company_domains,
                }

                application_id = await match_email_to_application(
                    db,
                    email_dict,
                    classification,
                    user_id=user.id,
                )

                cls = classification.get("classification", "job_update")
                event = EmailEvent(
                    user_id=user.id,
                    application_id=application_id,
                    gmail_message_id=msg_id,
                    thread_id=full_msg.get("threadId"),
                    sender=sender_name,
                    sender_email=sender_email,
                    subject=subject,
                    body=body[:10000] if body else None,
                    snippet=full_msg.get("snippet", ""),
                    received_at=received_at,
                    classification=cls,
                    color_code=CLASSIFICATION_TO_COLOR.get(cls, "gray"),
                    email_type=email_type_for_classifier_result(classification),
                    action_needed=classification.get("action_needed", False),
                    key_sentence=classification.get("key_sentence"),
                    summary=classification.get("summary"),
                    is_human=not classification.get("is_automated", False),
                    company_name=email_company_name,
                    company_logo_url=company_info.get("logo_url"),
                    sender_domain=sender_domain,
                    confidence=classification.get("confidence"),
                )
                db.add(event)
                await db.flush()
                await create_email_classification_trace(
                    db,
                    user_id=user.id,
                    classification=classification,
                    email_event=event,
                    gmail_message_id=msg_id,
                    candidate_source_url_count=len(raw_candidate_urls),
                )
                if raw_candidate_urls:
                    try:
                        async with db.begin_nested():
                            stored_links = await store_many_user_application_links(
                                db,
                                user_id=user.id,
                                raw_urls=raw_candidate_urls,
                                application_id=application_id,
                                email_event_id=event.id,
                                created_from="gmail_poll",
                            )
                            await process_stored_links_for_source_discovery(
                                db,
                                user_id=user.id,
                                stored_links=stored_links,
                                discovered_from="gmail_poll",
                            )
                    except Exception as exc:
                        logger.warning(
                            "Gmail source-link processing skipped",
                            extra={
                                "error_type": type(exc).__name__.replace("\r", " ").replace("\n", " "),
                                "candidate_url_count": len(raw_candidate_urls),
                            },
                        )
                try:
                    await index_record(db, event)
                except Exception as exc:
                    logger.warning(
                        "Gmail search indexing skipped",
                        extra={"error_type": type(exc).__name__.replace("\r", " ").replace("\n", " ")},
                    )

                if classification.get("status_update_allowed", cls in STATUS_UPDATES) and cls in STATUS_UPDATES and application_id:
                    await update_application_status(
                        db,
                        application_id,
                        classification,
                        user_id=user.id,
                    )

                processed += 1

            await db.commit()
            total_processed += processed
            total_skipped_feedback += skipped_feedback
            logger.info(
                "Processed %s emails for %s, skipped %s from feedback blocklist",
                processed,
                user.email,
                skipped_feedback,
            )

        logger.info(
            "Processed %s total emails, skipped %s from feedback blocklists",
            total_processed,
            total_skipped_feedback,
        )
        return total_processed


@celery_app.task(bind=True, max_retries=3)
def poll_gmail(self):
    """Poll Gmail for new job-related emails."""
    try:
        return _run_async(_poll_gmail_async())
    except Exception as exc:
        logger.error(f"Gmail poll failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
