"""Sprint 11: Tests for alerts and response time intelligence."""

import pytest
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_alerts_empty(client):
    """GET /api/alerts returns empty when no alerts."""
    resp = await client.get("/api/alerts", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_list_alerts(client, db_session):
    """Alerts can be created and listed."""
    from backend.models import Alert

    alert = Alert(
        alert_type="follow_up",
        title="Follow up with Acme Corp",
        body="Your application to Acme Corp is 7 days old with no response.",
    )
    db_session.add(alert)
    await db_session.commit()

    resp = await client.get("/api/alerts", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Follow up with Acme Corp"
    assert data[0]["read"] is False


@pytest.mark.asyncio
async def test_mark_alert_read(client, db_session):
    """PATCH /api/alerts/{id} marks alert as read."""
    from backend.models import Alert

    alert = Alert(alert_type="dead_listing", title="Job closed at TestCo")
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)

    resp = await client.patch(f"/api/alerts/{str(alert.id)}", headers=AUTH_HEADER)
    assert resp.status_code == 200

    # Verify
    list_resp = await client.get("/api/alerts?unread=true", headers=AUTH_HEADER)
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_unread_count(client, db_session):
    """GET /api/alerts/count returns correct unread count."""
    from backend.models import Alert

    db_session.add(Alert(alert_type="test", title="Alert 1"))
    db_session.add(Alert(alert_type="test", title="Alert 2"))
    db_session.add(Alert(alert_type="test", title="Alert 3", read=True))
    await db_session.commit()

    resp = await client.get("/api/alerts/count", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["unread"] == 2


@pytest.mark.asyncio
async def test_first_response_days_field(client):
    """Application serializes first_response_days."""
    resp = await client.post(
        "/api/jobs",
        json={"company": "ResponseCo", "role_title": "Analyst"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["first_response_days"] is None


@pytest.mark.asyncio
async def test_alert_not_found(client):
    """PATCH /api/alerts/{invalid} returns 404."""
    import uuid
    resp = await client.patch(f"/api/alerts/{uuid.uuid4()}", headers=AUTH_HEADER)
    assert resp.status_code == 404
