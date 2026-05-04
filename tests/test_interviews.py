"""Sprint 13: Tests for interview calendar."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import select

from backend.gmail_token_crypto import encrypt_gmail_token
from tests.conftest import AUTH_HEADER, TEST_USER_ID


@pytest.mark.asyncio
async def test_interview_model(db_session):
    """Interview model stores all fields correctly."""
    from backend.models import Application, Interview

    app = Application(company="CalCo", role_title="Engineer")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    interview = Interview(
        application_id=app.id,
        interview_type="technical",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=3),
        duration_minutes=60,
        interviewer_name="Jane Smith",
        interviewer_email="jane@calco.com",
        location_or_link="https://zoom.us/j/123",
        notes="Prepare system design",
        outcome="pending",
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    assert interview.interview_type == "technical"
    assert interview.duration_minutes == 60
    assert interview.outcome == "pending"


@pytest.mark.asyncio
async def test_create_interview(client):
    """POST /api/interviews creates interview."""
    resp = await client.post(
        "/api/interviews",
        json={
            "interview_type": "phone",
            "interviewer_name": "Bob Recruiter",
            "duration_minutes": 30,
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["interview_type"] == "phone"
    assert data["interviewer_name"] == "Bob Recruiter"
    assert data["outcome"] == "pending"


@pytest.mark.asyncio
async def test_create_interview_rejects_invalid_interviewer_email(client):
    """POST /api/interviews rejects invalid interviewer emails."""
    resp = await client.post(
        "/api/interviews",
        json={
            "interview_type": "phone",
            "interviewer_email": "not-an-email",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_interviews(client):
    """GET /api/interviews returns list."""
    # Create one first
    await client.post(
        "/api/interviews",
        json={"interview_type": "technical"},
        headers=AUTH_HEADER,
    )
    resp = await client.get("/api/interviews", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_upcoming_interviews(client):
    """GET /api/interviews/upcoming returns future pending interviews."""
    future_dt = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    await client.post(
        "/api/interviews",
        json={"interview_type": "onsite", "scheduled_at": future_dt},
        headers=AUTH_HEADER,
    )
    resp = await client.get("/api/interviews/upcoming", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["interview_type"] == "onsite"


@pytest.mark.asyncio
async def test_update_interview(client):
    """PATCH /api/interviews/{id} updates fields."""
    create_resp = await client.post(
        "/api/interviews",
        json={"interview_type": "phone"},
        headers=AUTH_HEADER,
    )
    iid = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/interviews/{iid}",
        json={"outcome": "passed", "notes": "Went great!"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "passed"
    assert data["notes"] == "Went great!"


@pytest.mark.asyncio
async def test_delete_interview(client):
    """DELETE /api/interviews/{id} removes interview."""
    create_resp = await client.post(
        "/api/interviews",
        json={"interview_type": "panel"},
        headers=AUTH_HEADER,
    )
    iid = create_resp.json()["id"]

    resp = await client.delete(f"/api/interviews/{iid}", headers=AUTH_HEADER)
    assert resp.status_code == 200

    # Verify it's gone
    get_resp = await client.patch(f"/api/interviews/{iid}", json={}, headers=AUTH_HEADER)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_interview_from_email(client, db_session):
    """POST /api/interviews/from-email/{email_id} creates from email."""
    from backend.models import EmailEvent

    email = EmailEvent(
        subject="Interview scheduled - January 15, 2026 at 2:00 PM",
        body="Hi, your interview is scheduled for January 15, 2026 at 2:00 PM. Please join at https://zoom.us/j/test123",
        sender="recruiter@company.com",
        sender_email="recruiter@company.com",
        classification="interview_request",
    )
    db_session.add(email)
    await db_session.commit()
    await db_session.refresh(email)

    resp = await client.post(
        f"/api/interviews/from-email/{email.id}",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["interviewer_email"] == "recruiter@company.com"
    assert "Created from email" in data["notes"]


@pytest.mark.asyncio
async def test_calendar_sync_detection():
    """Calendar sync detects interview events."""
    from backend.services.calendar_sync import _is_interview_event, _detect_interview_type

    assert _is_interview_event("Phone Screen with Jane")
    assert _is_interview_event("Technical Interview - Round 2")
    assert not _is_interview_event("Team standup")
    assert not _is_interview_event("Lunch meeting")

    assert _detect_interview_type("Phone Screen") == "phone"
    assert _detect_interview_type("Technical coding challenge") == "technical"
    assert _detect_interview_type("Onsite Interview") == "onsite"
    assert _detect_interview_type("Panel Interview") == "panel"


@pytest.mark.asyncio
async def test_extract_interview_datetime():
    """extract_interview_datetime finds date/time in email text."""
    from backend.services.calendar_sync import extract_interview_datetime

    result = extract_interview_datetime(
        "Your interview is scheduled for January 15, 2026 at 2:00 PM. "
        "The call will be 45 minutes. Join at https://zoom.us/j/123"
    )
    assert result is not None
    assert "scheduled_at" in result
    assert result.get("duration_minutes") == 45
    assert "zoom.us" in result.get("location_or_link", "")


@pytest.mark.asyncio
async def test_extract_interview_datetime_handles_numeric_dates_and_timezones():
    """extract_interview_datetime handles common recruiter email formats."""
    from backend.services.calendar_sync import extract_interview_datetime

    result = extract_interview_datetime(
        "You are confirmed for an interview on 05/07/2026 • 2:30 PM ET. "
        "This will be a 30-minute video call. Join at https://meet.google.com/abc-defg-hij",
        reference_datetime=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
    )

    assert result is not None
    assert result["scheduled_at"].startswith("2026-05-07T14:30:00")
    assert result["duration_minutes"] == 30
    assert result["location_or_link"] == "https://meet.google.com/abc-defg-hij"


@pytest.mark.asyncio
async def test_extract_interview_datetime_requires_actual_time():
    """Scheduling portal emails without a selected slot should stay unscheduled."""
    from backend.services.calendar_sync import extract_interview_datetime

    result = extract_interview_datetime(
        "Select a timeslot for your interview at Bank of America on 05/07/2026. "
        "Your verification code is 113812.",
        reference_datetime=datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc),
    )

    assert result is None


@pytest.mark.asyncio
async def test_calendar_sync_creates_and_updates_interview(client, db_session):
    """POST /api/calendar/sync upserts interview events from Google Calendar."""
    from backend.models import Alert, Application, Company, GmailToken, Interview, User

    company = Company(domain="matchco.com", name="MatchCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app = Application(
        user_id=TEST_USER_ID,
        company="MatchCo",
        role_title="Engineer",
        company_id=company.id,
    )
    token = GmailToken(
        user_id=TEST_USER_ID,
        access_token=encrypt_gmail_token("access-token"),
        refresh_token=encrypt_gmail_token("refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add_all([app, token])
    await db_session.commit()

    user_result = await db_session.execute(select(User).where(User.id == TEST_USER_ID))
    user = user_result.scalar_one()
    user.calendar_connected = True
    user.notifications_started_at = datetime.now(timezone.utc)
    await db_session.commit()

    calendar_service = MagicMock()
    first_events = {
        "items": [
            {
                "id": "calendar-event-1",
                "summary": "Technical Interview with MatchCo",
                "description": "Coding interview",
                "start": {"dateTime": "2026-03-20T15:00:00+00:00"},
                "end": {"dateTime": "2026-03-20T16:00:00+00:00"},
                "attendees": [
                    {"email": "test-user@apptrail.test", "self": True},
                    {"email": "recruiter@matchco.com", "displayName": "Recruiter"},
                ],
                "organizer": {"email": "recruiter@matchco.com", "displayName": "Recruiter"},
                "hangoutLink": "https://meet.google.com/first-sync",
            }
        ]
    }
    second_events = {
        "items": [
            {
                "id": "calendar-event-1",
                "summary": "Technical Interview with MatchCo (Updated)",
                "description": "Coding interview",
                "start": {"dateTime": "2026-03-20T16:30:00+00:00"},
                "end": {"dateTime": "2026-03-20T17:15:00+00:00"},
                "attendees": [
                    {"email": "test-user@apptrail.test", "self": True},
                    {"email": "recruiter@matchco.com", "displayName": "Recruiter"},
                ],
                "organizer": {"email": "recruiter@matchco.com", "displayName": "Recruiter"},
                "location": "https://zoom.us/j/updated-sync",
            }
        ]
    }

    execute_mock = calendar_service.events.return_value.list.return_value.execute
    execute_mock.return_value = first_events

    with patch("googleapiclient.discovery.build", return_value=calendar_service):
        first_response = await client.post("/api/calendar/sync", headers=AUTH_HEADER)

        assert first_response.status_code == 200
        assert first_response.json()["created"] == 1

        execute_mock.return_value = second_events
        second_response = await client.post("/api/calendar/sync", headers=AUTH_HEADER)

    assert second_response.status_code == 200
    assert second_response.json()["updated"] == 1

    interview_result = await db_session.execute(
        select(Interview).where(Interview.calendar_event_id == "calendar-event-1")
    )
    interviews = interview_result.scalars().all()
    assert len(interviews) == 1
    interview = interviews[0]
    assert interview.application_id == app.id
    assert interview.duration_minutes == 45
    assert interview.location_or_link == "https://zoom.us/j/updated-sync"
    assert interview.notes == "Auto-synced from Google Calendar: Technical Interview with MatchCo (Updated)"

    alert_result = await db_session.execute(select(Alert).where(Alert.user_id == TEST_USER_ID).order_by(Alert.created_at.asc()))
    alerts = alert_result.scalars().all()
    assert len(alerts) == 2
    assert alerts[0].action_url == f"/calendar?interview_id={interview.id}"
    assert alerts[1].action_url == f"/calendar?interview_id={interview.id}"
    assert alerts[0].alert_type == "interview_request"
    assert alerts[1].alert_type == "interview_request"


@pytest.mark.asyncio
async def test_calendar_sync_requires_connected_calendar(client):
    """POST /api/calendar/sync rejects users without Calendar access."""
    response = await client.post("/api/calendar/sync", headers=AUTH_HEADER)
    assert response.status_code == 400
    assert "Calendar not connected" in response.json()["detail"]
