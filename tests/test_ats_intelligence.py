"""Sprint 8: Tests for ATS behavioral intelligence."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_ats_intelligence_empty(client):
    """GET /api/intelligence/ats/{platform} returns empty profile for unknown platform."""
    resp = await client.get("/api/intelligence/ats/greenhouse.io", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "greenhouse.io"
    assert data["metrics"] == {}


@pytest.mark.asyncio
async def test_compute_ats_metrics(client, db_session):
    """POST /api/intelligence/ats/compute aggregates metrics from data."""
    from backend.models import Company, Application

    # Create company with ATS platform
    company = Company(
        domain="testcorp.com",
        name="TestCorp",
        ats_platform="greenhouse.io",
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    # Create applications linked to that company
    app1 = Application(
        company="TestCorp",
        role_title="SWE",
        status="rejected",
        company_id=company.id,
        applied_at=datetime.now(timezone.utc) - timedelta(days=30),
        last_email_at=datetime.now(timezone.utc) - timedelta(days=25),
    )
    app2 = Application(
        company="TestCorp",
        role_title="Designer",
        status="applied",
        company_id=company.id,
        applied_at=datetime.now(timezone.utc) - timedelta(days=20),
    )
    db_session.add_all([app1, app2])
    await db_session.commit()

    # Compute metrics
    resp = await client.post("/api/intelligence/ats/compute", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["metrics"]) > 0

    # Check platform profile
    profile_resp = await client.get("/api/intelligence/ats/greenhouse.io", headers=AUTH_HEADER)
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert "rejection_rate" in profile["metrics"]
    assert profile["metrics"]["rejection_rate"]["value"] == 50.0  # 1 of 2 rejected


@pytest.mark.asyncio
async def test_ats_ghosting_rate(client, db_session):
    """Ghosting rate computed for old applications with no email."""
    from backend.models import Company, Application

    company = Company(
        domain="ghostco.com",
        name="GhostCo",
        ats_platform="lever.co",
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    # Old app with no response
    old_app = Application(
        company="GhostCo",
        role_title="Phantom Role",
        status="applied",
        company_id=company.id,
        applied_at=datetime.now(timezone.utc) - timedelta(days=30),
        last_email_at=None,
    )
    db_session.add(old_app)
    await db_session.commit()

    resp = await client.post("/api/intelligence/ats/compute", headers=AUTH_HEADER)
    assert resp.status_code == 200

    profile_resp = await client.get("/api/intelligence/ats/lever.co", headers=AUTH_HEADER)
    profile = profile_resp.json()
    assert "ghosting_rate" in profile["metrics"]
    assert profile["metrics"]["ghosting_rate"]["value"] == 100.0


@pytest.mark.asyncio
async def test_ats_insights_generated(client, db_session):
    """Insights text generated from metrics."""
    from backend.models import Company, Application

    company = Company(
        domain="insightco.com",
        name="InsightCo",
        ats_platform="workday",
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app1 = Application(
        company="InsightCo",
        role_title="Analyst",
        status="rejected",
        company_id=company.id,
        applied_at=datetime.now(timezone.utc) - timedelta(days=10),
        last_email_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(app1)
    await db_session.commit()

    await client.post("/api/intelligence/ats/compute", headers=AUTH_HEADER)
    resp = await client.get("/api/intelligence/ats/workday", headers=AUTH_HEADER)
    data = resp.json()
    assert len(data["insights"]) > 0
    assert any("workday" in i.lower() for i in data["insights"])


# --- Unit tests for ATS intelligence service ---

from backend.services.ats_intelligence import get_platform_profile


@pytest.mark.asyncio
async def test_get_platform_profile_empty(db_session):
    """Empty platform profile returns empty metrics."""
    result = await get_platform_profile(db_session, "unknown_platform")
    assert result["platform"] == "unknown_platform"
    assert result["metrics"] == {}
    assert result["insights"] == []
