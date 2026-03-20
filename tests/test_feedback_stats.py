"""Tests for GET /api/emails/feedback/stats endpoint."""

import pytest
from datetime import datetime, timezone
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_feedback_stats_empty(client):
    """Returns zeros when no feedback exists."""
    resp = await client.get("/api/emails/feedback/stats", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_feedback"] == 0
    assert data["not_job_related"] == 0
    assert data["job_related"] == 0
    assert data["top_blocked_domains"] == []
    assert data["original_classifications"] == {}
    assert data["daily_trend"] == []


@pytest.mark.asyncio
async def test_feedback_stats_with_data(client, db_session):
    """Returns aggregated stats from feedback on real emails."""
    from backend.models import EmailEvent

    # Create emails with different domains and classifications
    emails = []
    for i, (domain, cls) in enumerate([
        ("github.com", "job_update"),
        ("github.com", "conversation"),
        ("linkedin.com", "action_item"),
        ("newsletter.co", "job_update"),
    ]):
        ev = EmailEvent(
            gmail_message_id=f"fb-stats-{i}",
            sender=f"sender@{domain}",
            sender_email=f"sender@{domain}",
            subject=f"Test email {i}",
            received_at=datetime.now(timezone.utc),
            classification=cls,
            sender_domain=domain,
            pipeline=cls,
        )
        db_session.add(ev)
        emails.append(ev)
    await db_session.commit()
    for ev in emails:
        await db_session.refresh(ev)

    # Mark 3 as not job related, 1 as job related
    for ev in emails[:3]:
        resp = await client.post(
            "/api/emails/feedback",
            json={"email_id": str(ev.id), "is_job_related": False},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 201

    resp = await client.post(
        "/api/emails/feedback",
        json={"email_id": str(emails[3].id), "is_job_related": True},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201

    # Now check stats
    resp = await client.get("/api/emails/feedback/stats", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_feedback"] == 4
    assert data["not_job_related"] == 3
    assert data["job_related"] == 1

    # Top blocked domains — github.com should have 2, linkedin.com 1
    domains = {d["domain"]: d["count"] for d in data["top_blocked_domains"]}
    assert domains.get("github.com") == 2
    assert domains.get("linkedin.com") == 1

    # Original classifications — what classifier thought these were
    assert "original_classifications" in data
    assert isinstance(data["original_classifications"], dict)

    # Daily trend should have at least 1 entry
    assert len(data["daily_trend"]) >= 1
    assert data["daily_trend"][0]["count"] >= 1


@pytest.mark.asyncio
async def test_feedback_stats_requires_auth(client):
    """Endpoint requires authentication."""
    resp = await client.get("/api/emails/feedback/stats")
    assert resp.status_code in (401, 403, 422)
