import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Application, EmailEvent
from backend.services.email_filter import ATS_DOMAINS, extract_domain

logger = logging.getLogger(__name__)

# Map ATS domains to application source values
ATS_DOMAIN_TO_SOURCE = {
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
    "myworkday.com": "workday",
    "ashbyhq.com": "ashby",
    "icims.com": "icims",
    "jobvite.com": "jobvite",
    "smartrecruiters.com": "smartrecruiters",
    "taleo.net": "taleo",
}

# Classification → application status mapping
STATUS_UPDATES = {
    "rejected": "rejected",
    "interview_request": "interviewing",
    "offer": "offer",
    "under_review": "applied",
    "applied_confirmed": "applied",
    "action_required": "applied",
    "human_outreach": "applied",
}


async def email_already_processed(
    db: AsyncSession,
    gmail_message_id: str,
    user_id=None,
) -> bool:
    stmt = select(EmailEvent).where(EmailEvent.gmail_message_id == gmail_message_id)
    if user_id:
        stmt = stmt.where(EmailEvent.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_active_company_domains(db: AsyncSession, user_id=None) -> set[str]:
    """Get set of domains from all non-archived applications."""
    stmt = select(Application.job_url, Application.company).where(
        Application.archived_at.is_(None)
    )
    if user_id:
        stmt = stmt.where(Application.user_id == user_id)
    result = await db.execute(stmt)
    rows = result.all()

    domains = set()
    for job_url, company in rows:
        if job_url:
            domain = extract_domain_from_url(job_url)
            if domain:
                domains.add(domain)
        if company:
            # Simple heuristic: company name → domain
            clean = re.sub(r"[^a-zA-Z0-9]", "", company.lower())
            domains.add(f"{clean}.com")
    return domains


def extract_domain_from_url(url: str) -> str:
    """Extract domain from URL."""
    match = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    if match:
        parts = match.group(1).split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
    return ""


async def match_email_to_application(
    db: AsyncSession,
    email: dict,
    classification: dict,
    user_id=None,
) -> str | None:
    """Match an email to an application using 4-step priority.

    1. Company name from email body/sender → match applications.company
    2. ATS sender → most recent open app on that ATS
    3. Multiple candidates → most recently applied_at
    4. Ambiguous → None
    """
    sender = email.get("sender", "")
    body = email.get("body", "")
    subject = email.get("subject", "")
    sender_domain = extract_domain(sender)

    # Step 1: Match by company name in body/subject
    stmt = select(Application).where(Application.archived_at.is_(None)).order_by(
        Application.applied_at.desc()
    )
    if user_id:
        stmt = stmt.where(Application.user_id == user_id)
    result = await db.execute(stmt)
    apps = result.scalars().all()

    if not apps:
        return None

    # Try to find company name in email content
    search_text = f"{subject} {body} {sender}".lower()
    matches = []
    for app in apps:
        if app.company.lower() in search_text:
            matches.append(app)

    if len(matches) == 1:
        return str(matches[0].id)
    if len(matches) > 1:
        # Multiple matches — return most recent
        return str(matches[0].id)  # already sorted by applied_at desc

    # Step 2: ATS sender → most recent open app using that ATS
    if sender_domain in ATS_DOMAINS:
        ats_source = ATS_DOMAIN_TO_SOURCE.get(sender_domain)
        if ats_source:
            for app in apps:
                if app.source == ats_source:
                    return str(app.id)

    # Step 3: No match found
    return None


async def create_email_event(
    db: AsyncSession,
    email: dict,
    classification: dict,
    application_id: str | None,
    user_id=None,
) -> EmailEvent:
    """Create an email_event record."""
    import uuid

    sender_domain = extract_domain(email.get("sender", ""))
    is_ats = sender_domain in ATS_DOMAINS

    event = EmailEvent(
        user_id=user_id,
        application_id=uuid.UUID(application_id) if application_id else None,
        gmail_message_id=email.get("message_id"),
        sender=email.get("sender"),
        received_at=email.get("received_at") or datetime.now(timezone.utc),
        pipeline="ats" if is_ats else "human",
        classification=classification.get("classification", "unknown"),
        color_code=classification.get("color_code", "gray"),
        urgency=classification.get("urgency", "low"),
        action_needed=classification.get("action_needed", False),
        action_url=classification.get("action_url"),
        is_human=not is_ats,
        key_sentence=classification.get("key_sentence"),
        summary=classification.get("summary"),
    )
    db.add(event)
    await db.flush()
    from backend.services.search.indexer import index_record
    await index_record(db, event)
    await db.commit()
    await db.refresh(event)
    return event


async def update_application_status(
    db: AsyncSession,
    application_id: str | None,
    classification: dict,
    user_id=None,
):
    """Update application status based on email classification."""
    if not application_id:
        return

    import uuid

    new_status = STATUS_UPDATES.get(classification.get("classification"))
    if not new_status:
        return

    stmt = select(Application).where(Application.id == uuid.UUID(application_id))
    if user_id:
        stmt = stmt.where(Application.user_id == user_id)
    result = await db.execute(stmt)
    app = result.scalar_one_or_none()
    if not app:
        return

    app.status = new_status
    app.status_updated_at = datetime.now(timezone.utc)
    app.last_email_at = datetime.now(timezone.utc)

    # Auto-archive denied/withdrawn after 30 days
    if new_status == "rejected":
        from datetime import timedelta
        app.archived_at = datetime.now(timezone.utc) + timedelta(days=30)

    from backend.services.search.indexer import index_record
    await index_record(db, app)
    await db.commit()
