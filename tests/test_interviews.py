"""Sprint 13: Tests for interview calendar."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from tests.conftest import AUTH_HEADER


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
