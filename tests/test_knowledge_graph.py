"""Sprint 15: Tests for knowledge graph retrieval layer."""

import pytest
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_company_context_not_found(client):
    """GET /api/companies/{domain}/context returns empty for unknown domain."""
    resp = await client.get("/api/companies/unknown-domain.com/context", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is False
    assert data["domain"] == "unknown-domain.com"


@pytest.mark.asyncio
async def test_company_context_with_data(client, db_session):
    """GET /api/companies/{domain}/context returns full assembled context."""
    from backend.models import Company, Application, Contact

    company = Company(
        domain="graphco.com",
        name="GraphCo",
        logo_url="https://logo.clearbit.com/graphco.com",
        ats_platform="greenhouse.io",
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app = Application(
        company="GraphCo",
        role_title="Graph Engineer",
        status="applied",
        company_id=company.id,
        match_score=85,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    contact = Contact(
        application_id=app.id,
        company_id=company.id,
        name="Graph User",
        email="user@graphco.com",
        source="hunter",
    )
    db_session.add(contact)
    await db_session.commit()

    resp = await client.get("/api/companies/graphco.com/context", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert data["identity"]["name"] == "GraphCo"
    assert len(data["applications"]) == 1
    assert data["applications"][0]["match_score"] == 85
    assert len(data["contacts"]) == 1
    assert data["summary"]["total_applications"] == 1
    assert data["summary"]["total_contacts"] == 1


@pytest.mark.asyncio
async def test_knowledge_graph_service(db_session):
    """get_company_context assembles all data correctly."""
    from backend.models import Company
    from backend.services.knowledge_graph import get_company_context

    company = Company(domain="svctest.com", name="SvcTest")
    db_session.add(company)
    await db_session.commit()

    result = await get_company_context(db_session, "svctest.com")
    assert result["found"] is True
    assert result["identity"]["name"] == "SvcTest"
    assert result["applications"] == []
    assert result["tech_stack"] == []


@pytest.mark.asyncio
async def test_knowledge_graph_unknown_domain(db_session):
    """get_company_context returns not found for unknown domain."""
    from backend.services.knowledge_graph import get_company_context

    result = await get_company_context(db_session, "nope.com")
    assert result["found"] is False


@pytest.mark.asyncio
async def test_company_context_response_stats(client, db_session):
    """Response stats computed from application first_response_days."""
    from backend.models import Company, Application

    company = Company(domain="respco.com", name="RespCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    for days in [3, 5, 7]:
        app = Application(
            company="RespCo",
            role_title="Dev",
            company_id=company.id,
            first_response_days=days,
        )
        db_session.add(app)
    await db_session.commit()

    resp = await client.get("/api/companies/respco.com/context", headers=AUTH_HEADER)
    data = resp.json()
    assert data["response_stats"]["avg_response_days"] == 5.0
    assert data["response_stats"]["min_response_days"] == 3
    assert data["response_stats"]["max_response_days"] == 7
