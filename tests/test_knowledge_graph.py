"""Sprint 15: Tests for knowledge graph retrieval layer."""

import uuid

import pytest

from tests.conftest import AUTH_HEADER, make_auth_header


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


@pytest.mark.asyncio
async def test_company_context_is_user_scoped(client, db_session):
    from backend.models import Application, Company, Contact, EmailEvent, User, WarmConnection

    other_user_id = uuid.UUID("00000000-0000-0000-0000-00000000000f")
    db_session.add(
        User(
            id=other_user_id,
            google_id="other-google-id",
            email="other-user@apptrail.test",
            name="Other User",
        )
    )

    company = Company(domain="privateco.com", name="PrivateCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    own_app = Application(
        company="PrivateCo",
        role_title="Own Role",
        company_id=company.id,
    )
    other_app = Application(
        user_id=other_user_id,
        company="PrivateCo",
        role_title="Other Role",
        company_id=company.id,
    )
    db_session.add_all([own_app, other_app])
    await db_session.commit()
    await db_session.refresh(own_app)
    await db_session.refresh(other_app)

    db_session.add_all([
        Contact(
            application_id=own_app.id,
            company_id=company.id,
            name="Own Contact",
            email="own@privateco.com",
            source="hunter",
        ),
        Contact(
            user_id=other_user_id,
            application_id=other_app.id,
            company_id=company.id,
            name="Other Contact",
            email="other@privateco.com",
            source="hunter",
        ),
        EmailEvent(
            company_id=company.id,
            application_id=own_app.id,
            gmail_message_id="own-msg",
            sender="Own Sender",
            classification="update",
            color_code="blue",
            urgency="low",
        ),
        EmailEvent(
            user_id=other_user_id,
            company_id=company.id,
            application_id=other_app.id,
            gmail_message_id="other-msg",
            sender="Other Sender",
            classification="update",
            color_code="blue",
            urgency="low",
        ),
        WarmConnection(
            company_domain="privateco.com",
            contact_email="own@privateco.com",
            contact_name="Own Warm Path",
            email_count=2,
        ),
        WarmConnection(
            user_id=other_user_id,
            company_domain="privateco.com",
            contact_email="other@privateco.com",
            contact_name="Other Warm Path",
            email_count=5,
        ),
    ])
    await db_session.commit()

    response = await client.get(
        "/api/companies/privateco.com/context",
        headers=AUTH_HEADER,
    )
    assert response.status_code == 200
    data = response.json()

    assert [app["role_title"] for app in data["applications"]] == ["Own Role"]
    assert [contact["email"] for contact in data["contacts"]] == ["own@privateco.com"]
    assert len(data["emails"]) == 1
    assert data["emails"][0]["sender"] == "Own Sender"
    assert [warm["contact_email"] for warm in data["warm_connections"]] == ["own@privateco.com"]

    other_response = await client.get(
        "/api/companies/privateco.com/context",
        headers=make_auth_header(other_user_id, "other-user@apptrail.test", "Other User"),
    )
    assert other_response.status_code == 200
    other_data = other_response.json()
    assert [app["role_title"] for app in other_data["applications"]] == ["Other Role"]
    assert [contact["email"] for contact in other_data["contacts"]] == ["other@privateco.com"]
    assert len(other_data["emails"]) == 1
    assert other_data["emails"][0]["sender"] == "Other Sender"
    assert [warm["contact_email"] for warm in other_data["warm_connections"]] == ["other@privateco.com"]
