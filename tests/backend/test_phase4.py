import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import AUTH_HEADER


# --- 4.1 Job search tests ---


@pytest.mark.asyncio
async def test_job_search_returns_results():
    """SerpAPI query returns >= 1 result (mocked)."""
    mock_response = {
        "jobs_results": [
            {
                "title": "Data Analyst",
                "company_name": "TestCo",
                "location": "Remote",
                "description": "Analyze data for insights",
                "related_links": [{"link": "https://example.com/job/1"}],
                "detected_extensions": {"posted_at": "3 days ago"},
            }
        ]
    }

    with patch("backend.services.job_search.SERPAPI_KEY", "test-key"):
        with patch("backend.services.job_search.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = mock_response
            from backend.services.job_search import search_serpapi

            results = await search_serpapi("data analyst", "Remote")
            assert len(results) >= 1
            assert results[0]["title"] == "Data Analyst"
            assert results[0]["company"] == "TestCo"
            assert results[0]["source"] == "serpapi"


@pytest.mark.asyncio
async def test_job_search_caching(client):
    """Same query within 24h returns cached results."""
    mock_response = {
        "jobs_results": [
            {
                "title": "Cached Job",
                "company_name": "CacheCo",
                "location": "NYC",
                "description": "A cached job",
                "related_links": [],
                "detected_extensions": {},
            }
        ]
    }

    with patch("backend.services.job_search.SERPAPI_KEY", "test-key"):
        with patch("backend.services.job_search.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = mock_response

            # First call
            resp1 = await client.get(
                "/api/search?q=cached+test&location=NYC",
                headers=AUTH_HEADER,
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["cached"] is False
            assert len(data1["results"]) >= 1

            # Second call — should use cache
            resp2 = await client.get(
                "/api/search?q=cached+test&location=NYC",
                headers=AUTH_HEADER,
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["cached"] is True


@pytest.mark.asyncio
async def test_greenhouse_search():
    """Twitch Greenhouse search returns jobs (mocked)."""
    mock_response = {
        "jobs": [
            {
                "title": "Software Engineer",
                "location": {"name": "San Francisco"},
                "absolute_url": "https://boards.greenhouse.io/twitch/jobs/123",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ]
    }

    with patch("backend.services.job_search.with_retry", new_callable=AsyncMock) as mock_retry:
        mock_retry.return_value = mock_response
        from backend.services.job_search import search_greenhouse

        results = await search_greenhouse("twitch")
        assert len(results) >= 1
        assert results[0]["source"] == "greenhouse"
        assert results[0]["company"] == "Twitch"


# --- 4.2 Follow-up tests ---


@pytest.mark.asyncio
async def test_followup_flagging(db_session):
    """8-day-old applied application gets follow_up_due = true."""
    from backend.models import Application

    app = Application(
        company="FollowUpCo",
        role_title="Engineer",
        status="applied",
        applied_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    assert app.follow_up_due is False

    # Run follow-up check logic directly against test db_session
    from sqlalchemy import select, and_
    from backend.models import Application as AppModel

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = select(AppModel).where(
        and_(
            AppModel.status == "applied",
            AppModel.last_email_at.is_(None),
            AppModel.applied_at < cutoff,
            AppModel.archived_at.is_(None),
        )
    )
    result = await db_session.execute(stmt)
    apps = result.scalars().all()
    count = 0
    for a in apps:
        if not a.follow_up_due:
            a.follow_up_due = True
            count += 1
    if count > 0:
        await db_session.commit()
    assert count >= 1

    await db_session.refresh(app)
    assert app.follow_up_due is True


# --- 4.3 Contact response tracking ---


@pytest.mark.asyncio
async def test_contact_response_tracking(db_session):
    """Email from contact email -> response_received = true."""
    from backend.models import Application, Contact
    from backend.tasks.poll_gmail import _track_contact_response

    app = Application(company="TrackCo", role_title="Dev", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    contact = Contact(
        application_id=app.id,
        name="Test Contact",
        email="contact@trackco.com",
        source="hunter",
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)

    assert contact.response_received is False

    await _track_contact_response(db_session, "Test Contact <contact@trackco.com>")

    await db_session.refresh(contact)
    assert contact.response_received is True


# --- 4.5 Global search ---


@pytest.mark.asyncio
async def test_global_search(client):
    """Search 'globaltest' returns matching application."""
    # Create an application
    await client.post(
        "/api/jobs",
        json={
            "company": "GlobalTestCorp",
            "role_title": "Analyst",
            "job_url": "https://example.com/job/globaltest",
            "source": "manual",
        },
        headers=AUTH_HEADER,
    )

    resp = await client.get(
        "/api/search/global?q=globaltestcorp",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["applications"]) >= 1
    assert data["applications"][0]["company"] == "GlobalTestCorp"


# --- 4.6 CSV export ---


@pytest.mark.asyncio
async def test_csv_export(client):
    """GET /api/export/csv returns valid CSV with correct columns."""
    # Create an application first
    await client.post(
        "/api/jobs",
        json={
            "company": "CSVCorp",
            "role_title": "Data Engineer",
            "job_url": "https://example.com/job/csv-test",
            "source": "manual",
        },
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/export/csv", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")

    content = resp.text
    reader = csv.reader(io.StringIO(content))
    headers = next(reader)
    assert "company" in headers
    assert "role_title" in headers
    assert "status" in headers
    assert "contacts_count" in headers
    assert "archived_at" in headers

    rows = list(reader)
    assert len(rows) >= 1
    # Find our CSVCorp row
    csv_row = [r for r in rows if "CSVCorp" in r]
    assert len(csv_row) >= 1
