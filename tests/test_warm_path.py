"""Sprint 9: Tests for warm path detection."""

import pytest
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_warm_paths_no_domain(client):
    """GET /api/jobs/{id}/warm-paths returns empty when no domain."""
    resp = await client.post(
        "/api/jobs",
        json={"company": "NoDomainCo", "role_title": "SWE"},
        headers=AUTH_HEADER,
    )
    job_id = resp.json()["id"]
    resp = await client.get(f"/api/jobs/{job_id}/warm-paths", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["warm_connections"] == []


@pytest.mark.asyncio
async def test_warm_paths_with_domain(client, db_session):
    """GET /api/jobs/{id}/warm-paths returns connections for company domain."""
    from backend.models import Company, Application, WarmConnection
    from datetime import datetime, timezone

    company = Company(domain="warmco.com", name="WarmCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app = Application(
        company="WarmCo",
        role_title="Engineer",
        company_id=company.id,
        job_url="https://warmco.com/careers/123",
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    # Seed a warm connection
    conn = WarmConnection(
        company_domain="warmco.com",
        contact_email="alice@warmco.com",
        contact_name="Alice Smith",
        email_count=5,
        last_interaction_at=datetime.now(timezone.utc),
    )
    db_session.add(conn)
    await db_session.commit()

    resp = await client.get(f"/api/jobs/{str(app.id)}/warm-paths", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["warm_connections"]) == 1
    assert data["warm_connections"][0]["contact_name"] == "Alice Smith"
    assert data["warm_connections"][0]["email_count"] == 5


@pytest.mark.asyncio
async def test_warm_connection_model(db_session):
    """WarmConnection model stores correctly."""
    from backend.models import WarmConnection
    from datetime import datetime, timezone

    conn = WarmConnection(
        company_domain="test.com",
        contact_email="bob@test.com",
        contact_name="Bob",
        email_count=3,
    )
    db_session.add(conn)
    await db_session.commit()
    await db_session.refresh(conn)

    assert conn.company_domain == "test.com"
    assert conn.email_count == 3


@pytest.mark.asyncio
async def test_warm_path_service_no_gmail(db_session):
    """discover_warm_paths returns empty without Gmail service."""
    from backend.services.warm_path import discover_warm_paths

    result = await discover_warm_paths(db_session, "unknown.com")
    assert result == []
