"""Sprint 13: Google Calendar sync helpers for interview detection."""

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Application, Company, Interview

logger = logging.getLogger(__name__)

# Keywords that indicate an interview event
INTERVIEW_KEYWORDS = [
    "interview", "phone screen", "technical screen", "onsite",
    "panel", "final round", "coding challenge", "take-home",
    "hiring manager", "recruiter call", "behavioral",
]

# Map keywords to interview types
TYPE_MAP = {
    "phone screen": "phone",
    "recruiter call": "phone",
    "technical screen": "technical",
    "coding challenge": "technical",
    "take-home": "technical",
    "onsite": "onsite",
    "panel": "panel",
    "final round": "onsite",
    "behavioral": "phone",
}

PUBLIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "proton.me",
    "protonmail.com",
}


def _detect_interview_type(summary: str, description: str = "") -> str | None:
    """Detect interview type from calendar event text."""
    text = f"{summary} {description}".lower()
    for keyword, itype in TYPE_MAP.items():
        if keyword in text:
            return itype
    if "interview" in text:
        return "phone"  # default
    return None


def _is_interview_event(summary: str, description: str = "") -> bool:
    """Check if a calendar event looks like an interview."""
    text = f"{summary} {description}".lower()
    return any(kw in text for kw in INTERVIEW_KEYWORDS)


def _parse_event_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    from dateutil import parser as dateparser

    parsed = dateparser.isoparse(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _extract_external_attendees(event: dict, user_email: str | None) -> tuple[str | None, str | None]:
    user_email_lower = (user_email or "").lower()
    candidates: list[tuple[str | None, str]] = []

    for attendee in event.get("attendees", []):
        email = (attendee.get("email") or "").lower()
        if not email or attendee.get("self") or email == user_email_lower:
            continue
        candidates.append((attendee.get("displayName"), email))

    organizer = event.get("organizer") or {}
    organizer_email = (organizer.get("email") or "").lower()
    if organizer_email and organizer_email != user_email_lower:
        candidates.append((organizer.get("displayName"), organizer_email))

    if not candidates:
        return None, None

    for name, email in candidates:
        domain = email.split("@", 1)[-1]
        if domain not in PUBLIC_EMAIL_DOMAINS:
            return name, email

    return candidates[0]


def _extract_candidate_domains(event: dict, user_email: str | None) -> set[str]:
    user_email_lower = (user_email or "").lower()
    domains: set[str] = set()

    for attendee in event.get("attendees", []):
        email = (attendee.get("email") or "").lower()
        if not email or attendee.get("self") or email == user_email_lower or "@" not in email:
            continue
        domain = email.split("@", 1)[-1]
        if domain not in PUBLIC_EMAIL_DOMAINS:
            domains.add(domain)

    organizer = event.get("organizer") or {}
    organizer_email = (organizer.get("email") or "").lower()
    if organizer_email and organizer_email != user_email_lower and "@" in organizer_email:
        domain = organizer_email.split("@", 1)[-1]
        if domain not in PUBLIC_EMAIL_DOMAINS:
            domains.add(domain)

    return domains


async def _match_application_for_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    event: dict,
    user_email: str | None,
) -> uuid.UUID | None:
    domains = _extract_candidate_domains(event, user_email)
    if not domains:
        return None

    stmt = (
        select(Application.id)
        .join(Company, Application.company_id == Company.id)
        .where(
            Application.user_id == user_id,
            Application.archived_at.is_(None),
            Company.domain.in_(domains),
        )
        .order_by(Application.applied_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def sync_calendar_events(
    db: AsyncSession,
    calendar_service,
    user_id: uuid.UUID,
    user_email: str | None = None,
) -> dict:
    """Scan Google Calendar for interview events and upsert Interview records."""
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=30)).isoformat()
    time_max = (now + timedelta(days=90)).isoformat()

    events_result = (
        calendar_service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=100,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    created = 0
    updated = 0
    skipped = 0
    synced: list[dict] = []

    for event in events:
        summary = event.get("summary", "")
        description = event.get("description", "")
        event_id = event.get("id", "")

        if event.get("status") == "cancelled" or not event_id or not _is_interview_event(summary, description):
            skipped += 1
            continue

        start = event.get("start", {})
        end = event.get("end", {})
        scheduled_at = _parse_event_datetime(start.get("dateTime") or start.get("date"))
        end_at = _parse_event_datetime(end.get("dateTime") or end.get("date"))
        duration_minutes = None
        if scheduled_at and end_at:
            duration_minutes = int((end_at - scheduled_at).total_seconds() / 60)

        interviewer_name, interviewer_email = _extract_external_attendees(event, user_email)
        location = event.get("location") or event.get("hangoutLink")
        interview_type = _detect_interview_type(summary, description) or "phone"
        application_id = await _match_application_for_event(db, user_id, event, user_email)
        auto_note = f"Auto-synced from Google Calendar: {summary}"

        existing_stmt = select(Interview).where(
            Interview.user_id == user_id,
            Interview.calendar_event_id == event_id,
        )
        existing_result = await db.execute(existing_stmt)
        interview = existing_result.scalar_one_or_none()

        if interview:
            interview.interview_type = interview_type
            interview.scheduled_at = scheduled_at
            interview.duration_minutes = duration_minutes
            interview.interviewer_name = interviewer_name or interview.interviewer_name
            interview.interviewer_email = interviewer_email or interview.interviewer_email
            interview.location_or_link = location or interview.location_or_link
            if application_id and interview.application_id is None:
                interview.application_id = application_id
            if not interview.notes or interview.notes.startswith("Auto-synced from Google Calendar:"):
                interview.notes = auto_note
            updated += 1
        else:
            db.add(
                Interview(
                    user_id=user_id,
                    application_id=application_id,
                    interview_type=interview_type,
                    scheduled_at=scheduled_at,
                    duration_minutes=duration_minutes,
                    interviewer_name=interviewer_name,
                    interviewer_email=interviewer_email,
                    location_or_link=location,
                    notes=auto_note,
                    calendar_event_id=event_id,
                )
            )
            created += 1

        synced.append(
            {
                "event_id": event_id,
                "summary": summary,
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                "interview_type": interview_type,
            }
        )

    if created or updated:
        await db.commit()

    logger.info(
        "Synced %s Google Calendar interviews for user %s (%s created, %s updated, %s skipped)",
        created + updated,
        user_id,
        created,
        updated,
        skipped,
    )
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_events": len(events),
        "synced": synced,
    }


def extract_interview_datetime(email_body: str, email_subject: str = "") -> dict | None:
    """Extract interview date/time from email text.

    Returns dict with scheduled_at, duration_minutes, location_or_link if found.
    """
    import re

    text = f"{email_subject}\n{email_body}"

    # Common datetime patterns
    # "January 15, 2026 at 2:00 PM"
    # "Mon, Jan 15 at 2pm"
    # "2026-01-15 14:00"
    datetime_patterns = [
        r"(\w+ \d{1,2},?\s*\d{4}\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))",
        r"(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})",
        r"(\w+,?\s+\w+ \d{1,2}\s+at\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)",
    ]

    for pattern in datetime_patterns:
        match = re.search(pattern, text)
        if match:
            # Found a date - try to parse
            date_str = match.group(1)
            from dateutil import parser as dateparser
            try:
                scheduled_at = dateparser.parse(date_str)
                if scheduled_at:
                    result: dict = {"scheduled_at": scheduled_at.isoformat()}

                    # Look for duration
                    dur_match = re.search(r"(\d+)\s*(?:min|minute)", text, re.IGNORECASE)
                    if dur_match:
                        result["duration_minutes"] = int(dur_match.group(1))

                    # Look for zoom/teams/meet link
                    link_match = re.search(r"(https?://(?:zoom\.us|teams\.microsoft\.com|meet\.google\.com)\S+)", text)
                    if link_match:
                        result["location_or_link"] = link_match.group(1)

                    return result
            except (ValueError, TypeError):
                continue

    return None
