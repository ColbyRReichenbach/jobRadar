"""Sprint 13: Google Calendar sync for interview detection."""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Interview

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


async def sync_calendar_events(
    db: AsyncSession,
    calendar_service,
    user_id: str | None = None,
) -> list[dict]:
    """Scan Google Calendar for interview events and create Interview records."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    # Look at events from past 7 days to next 30 days
    time_min = (now - timedelta(days=7)).isoformat()
    time_max = (now + timedelta(days=30)).isoformat()

    events_result = calendar_service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=100,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    synced = []

    for event in events:
        summary = event.get("summary", "")
        description = event.get("description", "")
        event_id = event.get("id", "")

        if not _is_interview_event(summary, description):
            continue

        # Check if already synced
        existing_stmt = select(Interview).where(Interview.calendar_event_id == event_id)
        existing_result = await db.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            continue

        # Parse datetime
        start = event.get("start", {})
        scheduled_at = None
        if "dateTime" in start:
            scheduled_at = datetime.fromisoformat(start["dateTime"])
        elif "date" in start:
            scheduled_at = datetime.fromisoformat(start["date"]).replace(tzinfo=timezone.utc)

        # Parse duration
        duration_minutes = None
        end = event.get("end", {})
        if scheduled_at and "dateTime" in end:
            end_dt = datetime.fromisoformat(end["dateTime"])
            duration_minutes = int((end_dt - scheduled_at).total_seconds() / 60)

        # Extract attendees
        attendees = event.get("attendees", [])
        interviewer_email = None
        interviewer_name = None
        for a in attendees:
            if not a.get("self", False):
                interviewer_email = a.get("email")
                interviewer_name = a.get("displayName")
                break

        # Location/link
        location = event.get("location") or event.get("hangoutLink")

        interview_type = _detect_interview_type(summary, description) or "phone"

        interview = Interview(
            user_id=user_id,
            interview_type=interview_type,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            interviewer_name=interviewer_name,
            interviewer_email=interviewer_email,
            location_or_link=location,
            notes=f"Auto-detected from calendar: {summary}",
            calendar_event_id=event_id,
        )
        db.add(interview)
        synced.append({
            "summary": summary,
            "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
            "interview_type": interview_type,
        })

    if synced:
        await db.commit()

    return synced


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
