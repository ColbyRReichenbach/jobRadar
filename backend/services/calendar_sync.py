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
        sync_status = "skipped"

        if interview:
            changed = False
            if interview.interview_type != interview_type:
                interview.interview_type = interview_type
                changed = True
            if interview.scheduled_at != scheduled_at:
                interview.scheduled_at = scheduled_at
                changed = True
            if interview.duration_minutes != duration_minutes:
                interview.duration_minutes = duration_minutes
                changed = True
            if interviewer_name and interview.interviewer_name != interviewer_name:
                interview.interviewer_name = interviewer_name
                changed = True
            if interviewer_email and interview.interviewer_email != interviewer_email:
                interview.interviewer_email = interviewer_email
                changed = True
            if location and interview.location_or_link != location:
                interview.location_or_link = location
                changed = True
            if application_id and interview.application_id is None:
                interview.application_id = application_id
                changed = True
            if (
                (not interview.notes or interview.notes.startswith("Auto-synced from Google Calendar:"))
                and interview.notes != auto_note
            ):
                interview.notes = auto_note
                changed = True
            if changed:
                updated += 1
                sync_status = "updated"
            else:
                skipped += 1
                continue
        else:
            interview = Interview(
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
            db.add(interview)
            await db.flush()
            created += 1
            sync_status = "created"

        synced.append(
            {
                "event_id": event_id,
                "interview_id": str(interview.id),
                "summary": summary,
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                "interview_type": interview_type,
                "status": sync_status,
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


def extract_interview_datetime(email_body: str, email_subject: str = "", reference_datetime: datetime | None = None) -> dict | None:
    """Extract interview date/time from email text.

    Returns dict with scheduled_at, duration_minutes, location_or_link if found.
    """
    import html
    import re

    from dateutil import parser as dateparser
    from dateutil.tz import tzoffset

    raw_text = html.unescape(f"{email_subject}\n{email_body}")
    text = re.sub(r"<[^>]+>", " ", raw_text)
    text = re.sub(r"\s+", " ", text).strip()
    reference = reference_datetime or datetime.now(timezone.utc)
    default = reference.replace(hour=9, minute=0, second=0, microsecond=0)
    tzinfos = {
        "UTC": timezone.utc,
        "GMT": timezone.utc,
        "ET": tzoffset("ET", -5 * 3600),
        "EST": tzoffset("EST", -5 * 3600),
        "EDT": tzoffset("EDT", -4 * 3600),
        "CT": tzoffset("CT", -6 * 3600),
        "CST": tzoffset("CST", -6 * 3600),
        "CDT": tzoffset("CDT", -5 * 3600),
        "MT": tzoffset("MT", -7 * 3600),
        "MST": tzoffset("MST", -7 * 3600),
        "MDT": tzoffset("MDT", -6 * 3600),
        "PT": tzoffset("PT", -8 * 3600),
        "PST": tzoffset("PST", -8 * 3600),
        "PDT": tzoffset("PDT", -7 * 3600),
    }

    # Common datetime patterns. Require a time to avoid converting generic
    # scheduling emails into calendar events before the user has a slot.
    datetime_patterns = [
        r"\b((?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)?,?\s*(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\s*(?:at|@|,|-|•)?\s*\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)(?:\s*(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|UTC|GMT))?)\b",
        r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\s*(?:at|@|,|-|•)?\s*\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)(?:\s*(?:ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT|UTC|GMT))?)\b",
        r"\b(\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)\b",
    ]

    for pattern in datetime_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            try:
                scheduled_at = dateparser.parse(date_str, fuzzy=True, default=default, tzinfos=tzinfos)
                if scheduled_at:
                    if scheduled_at.tzinfo is None and reference.tzinfo is not None:
                        scheduled_at = scheduled_at.replace(tzinfo=reference.tzinfo)
                    explicit_year = bool(re.search(r"\b\d{4}\b", date_str))
                    if not explicit_year and scheduled_at.date() < reference.date():
                        try:
                            scheduled_at = scheduled_at.replace(year=scheduled_at.year + 1)
                        except ValueError:
                            scheduled_at = scheduled_at + timedelta(days=365)
                    result: dict = {"scheduled_at": scheduled_at.isoformat()}

                    dur_match = re.search(r"(\d+)\s*[- ]?\s*(?:min|minute)s?", text, re.IGNORECASE)
                    if dur_match:
                        result["duration_minutes"] = int(dur_match.group(1))

                    link_match = re.search(r"(https?://(?:zoom\.us|teams\.microsoft\.com|meet\.google\.com)\S+)", text)
                    if link_match:
                        result["location_or_link"] = link_match.group(1).rstrip(").,")

                    return result
            except (ValueError, TypeError):
                continue

    return None
