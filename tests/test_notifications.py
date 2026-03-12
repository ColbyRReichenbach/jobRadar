"""Sprint 19: Tests for notification preferences, alert creation with SMS, and digest."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_get_preferences_default(client):
    """GET /api/notifications/preferences returns defaults when none set."""
    resp = await client.get("/api/notifications/preferences", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["sms_enabled"] is False
    assert data["sms_phone"] is None
    assert data["weekly_digest_enabled"] is False
    assert data["browser_notifications_enabled"] is False
    assert data["inbox_updates_enabled"] is True
    assert data["conversations_enabled"] is True
    assert data["quiet_hours_enabled"] is False
    assert data["quiet_hours_start"] is None
    assert data["quiet_hours_end"] is None


@pytest.mark.asyncio
async def test_create_and_update_preferences(client):
    """PUT /api/notifications/preferences creates then updates."""
    # Create
    resp = await client.put(
        "/api/notifications/preferences",
        json={"sms_enabled": True, "sms_phone": "+15551234567"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sms_enabled"] is True
    assert data["sms_phone"] == "+15551234567"
    assert data["weekly_digest_enabled"] is False
    assert data["inbox_updates_enabled"] is True

    # Update
    resp2 = await client.put(
        "/api/notifications/preferences",
        json={
            "weekly_digest_enabled": True,
            "browser_notifications_enabled": True,
            "followups_enabled": False,
            "quiet_hours_enabled": True,
            "quiet_hours_start": 22,
            "quiet_hours_end": 7,
        },
        headers=AUTH_HEADER,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["sms_enabled"] is True  # unchanged
    assert data2["weekly_digest_enabled"] is True
    assert data2["browser_notifications_enabled"] is True
    assert data2["followups_enabled"] is False
    assert data2["quiet_hours_enabled"] is True
    assert data2["quiet_hours_start"] == 22
    assert data2["quiet_hours_end"] == 7


@pytest.mark.asyncio
async def test_get_preferences_after_set(client):
    """GET returns previously set preferences."""
    await client.put(
        "/api/notifications/preferences",
        json={"sms_enabled": True, "sms_phone": "+15559876543", "weekly_digest_enabled": True},
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/notifications/preferences", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["sms_enabled"] is True
    assert data["sms_phone"] == "+15559876543"
    assert data["weekly_digest_enabled"] is True


@pytest.mark.asyncio
async def test_notification_preferences_allow_clearing_quiet_hours(client):
    resp = await client.put(
        "/api/notifications/preferences",
        json={
            "quiet_hours_enabled": True,
            "quiet_hours_start": 21,
            "quiet_hours_end": 6,
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    clear_resp = await client.put(
        "/api/notifications/preferences",
        json={
            "quiet_hours_enabled": False,
            "quiet_hours_start": None,
            "quiet_hours_end": None,
        },
        headers=AUTH_HEADER,
    )
    assert clear_resp.status_code == 200
    data = clear_resp.json()
    assert data["quiet_hours_enabled"] is False
    assert data["quiet_hours_start"] is None
    assert data["quiet_hours_end"] is None


@pytest.mark.asyncio
async def test_create_alert(client):
    """POST /api/alerts creates an alert."""
    resp = await client.post(
        "/api/alerts",
        json={
            "alert_type": "dead_listing",
            "title": "Job at TestCo may be closed",
            "body": "The listing returned a 404.",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["alert_type"] == "dead_listing"
    assert data["title"] == "Job at TestCo may be closed"
    assert data["sms_sent"] is False  # not an urgent type


@pytest.mark.asyncio
async def test_create_alert_urgent_with_sms_prefs(client, db_session):
    """POST /api/alerts with urgent type checks SMS preferences."""
    from backend.models import NotificationPreference

    # Set up SMS preferences
    pref = NotificationPreference(
        sms_enabled=True,
        sms_phone="+15551112222",
    )
    db_session.add(pref)
    await db_session.commit()

    with patch("backend.services.sms_sender.send_sms", new_callable=AsyncMock) as mock_sms:
        mock_sms.return_value = {"status": "sent", "sid": "SM123"}

        resp = await client.post(
            "/api/alerts",
            json={
                "alert_type": "offer",
                "title": "Offer from BigCo!",
                "body": "You received an offer.",
            },
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["alert_type"] == "offer"
        assert data["sms_sent"] is True

        mock_sms.assert_called_once()
        call_args = mock_sms.call_args
        assert call_args[0][0] == "+15551112222"
        assert "OFFER" in call_args[0][1]


@pytest.mark.asyncio
async def test_create_alert_no_sms_when_disabled(client, db_session):
    """Urgent alert doesn't send SMS when SMS is disabled."""
    from backend.models import NotificationPreference

    pref = NotificationPreference(sms_enabled=False, sms_phone="+15551112222")
    db_session.add(pref)
    await db_session.commit()

    resp = await client.post(
        "/api/alerts",
        json={"alert_type": "offer", "title": "Offer!"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    assert resp.json()["sms_sent"] is False


@pytest.mark.asyncio
async def test_digest_preview_empty(client):
    """GET /api/digest/preview returns stats with no data."""
    resp = await client.get("/api/digest/preview", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["applications_submitted"] == 0
    assert data["stats"]["interviews_scheduled"] == 0
    assert data["stats"]["responses_received"] == 0
    assert "preview" in data


@pytest.mark.asyncio
async def test_digest_preview_with_data(client, db_session):
    """GET /api/digest/preview reflects recent activity."""
    from backend.models import Application

    app = Application(
        company="DigestCo",
        role_title="Engineer",
        status="applied",
        applied_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(app)
    await db_session.commit()

    resp = await client.get("/api/digest/preview", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["applications_submitted"] >= 1


@pytest.mark.asyncio
async def test_format_alert_sms():
    """Test SMS message formatting."""
    from backend.services.sms_sender import format_alert_sms

    msg = format_alert_sms("offer", "Offer from BigCo!", "Congratulations!")
    assert msg.startswith("[AppTrail OFFER]")
    assert "BigCo" in msg
    assert len(msg) <= 160

    msg2 = format_alert_sms("interview_request", "Interview at SmallCo")
    assert "[AppTrail INTERVIEW]" in msg2

    msg3 = format_alert_sms("unknown_type", "Something happened")
    assert "[AppTrail ALERT]" in msg3


@pytest.mark.asyncio
async def test_sms_skipped_without_credentials():
    """SMS is skipped gracefully when Twilio not configured."""
    from backend.services.sms_sender import send_sms

    result = await send_sms("+15551234567", "Test message")
    assert result["status"] == "skipped"
    assert result["reason"] == "twilio_not_configured"


@pytest.mark.asyncio
async def test_digest_build(db_session):
    """Test build_digest returns correct stats."""
    from backend.tasks.send_weekly_digest import build_digest
    from backend.models import Application, Interview

    # Add some data
    app = Application(
        company="BuildCo",
        role_title="Dev",
        status="applied",
        applied_at=datetime.now(timezone.utc) - timedelta(hours=12),
        follow_up_due=True,
    )
    db_session.add(app)

    interview = Interview(
        application_id=None,
        interview_type="phone",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
        outcome="pending",
    )
    db_session.add(interview)
    await db_session.commit()

    stats = await build_digest(db_session)
    assert stats["applications_submitted"] >= 1
    assert stats["upcoming_interviews"] >= 1
    assert stats["followups_due"] >= 1
    assert "period_start" in stats
    assert "period_end" in stats


@pytest.mark.asyncio
async def test_digest_render():
    """Test digest text rendering."""
    from backend.tasks.send_weekly_digest import render_digest_text

    stats = {
        "period_start": "2026-03-03T00:00:00+00:00",
        "period_end": "2026-03-10T00:00:00+00:00",
        "applications_submitted": 5,
        "interviews_scheduled": 2,
        "responses_received": 3,
        "followups_due": 1,
        "active_applications": 8,
        "upcoming_interviews": 1,
    }
    text = render_digest_text(stats)
    assert "Applications submitted: 5" in text
    assert "Interviews scheduled:   2" in text
    assert "Follow-ups due:         1" in text
    assert "AppTrail" in text
