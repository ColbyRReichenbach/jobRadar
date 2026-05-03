"""Sprint 8: Tests for ATS behavioral intelligence."""

import pytest
import uuid
from datetime import datetime, timezone, timedelta

from tests.conftest import AUTH_HEADER, TEST_USER_ID


async def _add_users(db_session, count: int) -> list[uuid.UUID]:
    from backend.models import User

    user_ids = [TEST_USER_ID]
    for idx in range(count - 1):
        user_id = uuid.uuid4()
        user_ids.append(user_id)
        db_session.add(
            User(
                id=user_id,
                google_id=f"ats-user-{user_id}",
                email=f"ats-{idx}@apptrail.test",
                name=f"ATS User {idx}",
            )
        )
    await db_session.commit()
    return user_ids


@pytest.mark.asyncio
async def test_ats_intelligence_empty(client):
    """GET /api/intelligence/ats/{platform} returns empty profile for unknown platform."""
    resp = await client.get("/api/intelligence/ats/greenhouse.io", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "greenhouse.io"
    assert data["metrics"] == {}
    assert data["aggregate_status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_ats_profile_hides_metrics_until_minimum_distinct_users(client, db_session):
    from backend.models import Company, Application

    company = Company(domain="smallco.com", name="SmallCo", ats_platform="greenhouse.io")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    db_session.add(
        Application(
            company="SmallCo",
            role_title="Engineer",
            status="rejected",
            company_id=company.id,
            applied_at=datetime.now(timezone.utc) - timedelta(days=30),
            last_email_at=datetime.now(timezone.utc) - timedelta(days=25),
        )
    )
    await db_session.commit()

    compute_resp = await client.post("/api/intelligence/ats/compute", headers=AUTH_HEADER)
    assert compute_resp.status_code == 200
    assert compute_resp.json()["metrics"] == []

    profile_resp = await client.get("/api/intelligence/ats/greenhouse.io", headers=AUTH_HEADER)
    profile = profile_resp.json()
    assert profile["metrics"] == {}
    assert profile["aggregate_status"] == "insufficient_data"


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

    user_ids = await _add_users(db_session, 4)
    apps = [
        Application(
            user_id=user_ids[0],
            company="TestCorp",
            role_title="SWE",
            status="rejected",
            company_id=company.id,
            applied_at=datetime.now(timezone.utc) - timedelta(days=30),
            last_email_at=datetime.now(timezone.utc) - timedelta(days=25),
        ),
        Application(
            user_id=user_ids[1],
            company="TestCorp",
            role_title="Backend Engineer",
            status="rejected",
            company_id=company.id,
            applied_at=datetime.now(timezone.utc) - timedelta(days=28),
        ),
        Application(
            user_id=user_ids[2],
            company="TestCorp",
            role_title="Designer",
            status="applied",
            company_id=company.id,
            applied_at=datetime.now(timezone.utc) - timedelta(days=20),
        ),
        Application(
            user_id=user_ids[3],
            company="TestCorp",
            role_title="Data Engineer",
            status="applied",
            company_id=company.id,
            applied_at=datetime.now(timezone.utc) - timedelta(days=18),
        ),
    ]
    db_session.add_all(apps)
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
    assert profile["metrics"]["rejection_rate"]["value"] == 50.0
    assert profile["metrics"]["rejection_rate"]["sample_size_bucket"] == "3-4"
    assert "sample_size" not in profile["metrics"]["rejection_rate"]


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

    user_ids = await _add_users(db_session, 3)
    db_session.add_all([
        Application(
            user_id=user_id,
            company="GhostCo",
            role_title=f"Phantom Role {idx}",
            status="applied",
            company_id=company.id,
            applied_at=datetime.now(timezone.utc) - timedelta(days=30 + idx),
            last_email_at=None,
        )
        for idx, user_id in enumerate(user_ids)
    ])
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

    user_ids = await _add_users(db_session, 3)
    db_session.add_all([
        Application(
            user_id=user_id,
            company="InsightCo",
            role_title=f"Analyst {idx}",
            status="rejected",
            company_id=company.id,
            applied_at=datetime.now(timezone.utc) - timedelta(days=10 + idx),
            last_email_at=datetime.now(timezone.utc) - timedelta(days=5 + idx),
        )
        for idx, user_id in enumerate(user_ids)
    ])
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
