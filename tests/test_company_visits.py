"""Sprint 17: Tests for company visits and extension intelligence."""

import pytest
from tests.conftest import AUTH_HEADER, TEST_USER_ID


@pytest.mark.asyncio
async def test_record_company_visit(client):
    """POST /api/company-visits creates a new visit record."""
    resp = await client.post(
        "/api/company-visits",
        json={"domain": "stripe.com", "url": "https://stripe.com/jobs/listing/engineer", "visit_count": 1},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain"] == "stripe.com"
    assert data["visit_count"] == 1
    assert data["first_visited_at"] is not None


@pytest.mark.asyncio
async def test_record_company_visit_drops_private_url(client):
    resp = await client.post(
        "/api/company-visits",
        json={
            "domain": "stripe.com",
            "url": "https://stripe.com/jobs/listing/engineer?candidateId=abc&token=secret",
            "visit_count": 1,
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201

    list_resp = await client.get("/api/company-visits", headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    visit = next(item for item in list_resp.json() if item["domain"] == "stripe.com")
    assert visit["url"] is None


@pytest.mark.asyncio
async def test_update_company_visit(client):
    """POST same domain updates existing visit record."""
    await client.post(
        "/api/company-visits",
        json={"domain": "google.com", "url": "https://careers.google.com/jobs", "visit_count": 1},
        headers=AUTH_HEADER,
    )
    resp = await client.post(
        "/api/company-visits",
        json={"domain": "google.com", "visit_count": 5},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain"] == "google.com"
    assert data["visit_count"] == 5


@pytest.mark.asyncio
async def test_list_company_visits(client):
    """GET /api/company-visits returns visits ordered by last_visited_at."""
    await client.post(
        "/api/company-visits",
        json={"domain": "meta.com", "visit_count": 3},
        headers=AUTH_HEADER,
    )
    await client.post(
        "/api/company-visits",
        json={"domain": "apple.com", "visit_count": 7},
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/company-visits", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    # Most recent should be first
    domains = [v["domain"] for v in data]
    assert "meta.com" in domains
    assert "apple.com" in domains


@pytest.mark.asyncio
async def test_list_company_visits_min_filter(client):
    """GET /api/company-visits?min_visits=5 filters by minimum count."""
    await client.post(
        "/api/company-visits",
        json={"domain": "lowvisit.com", "visit_count": 2},
        headers=AUTH_HEADER,
    )
    await client.post(
        "/api/company-visits",
        json={"domain": "highvisit.com", "visit_count": 10},
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/company-visits?min_visits=5", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    domains = [v["domain"] for v in data]
    assert "highvisit.com" in domains
    assert "lowvisit.com" not in domains


@pytest.mark.asyncio
async def test_submission_detection_no_match(client):
    """POST /api/company-visits/submission with no matching app returns matched=false."""
    resp = await client.post(
        "/api/company-visits/submission",
        json={
            "platform": "greenhouse",
            "url": "https://boards.greenhouse.io/unknown/jobs/123",
            "domain": "unknowncorp.com",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] is False
    assert data["platform"] == "greenhouse"
    assert data["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_submission_detection_with_enrichment(client, db_session):
    """POST /api/company-visits/submission enriches matching application with salary."""
    from backend.models import Application, Company

    company = Company(domain="enrichco.com", name="EnrichCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app = Application(
        user_id=TEST_USER_ID,
        company="EnrichCo",
        role_title="Engineer",
        status="saved",
        company_id=company.id,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.post(
        "/api/company-visits/submission",
        json={
            "platform": "greenhouse",
            "url": "https://boards.greenhouse.io/enrichco/jobs/456",
            "domain": "enrichco.com",
            "application_id": str(app.id),
            "enrichment": {
                "salary": "$120,000 - $160,000",
                "department": "Engineering",
            },
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] is True
    assert data["updated"] is True
    assert data["requires_confirmation"] is False

    # Verify the application was updated
    await db_session.refresh(app)
    assert app.status == "applied"
    assert app.salary_min == 120000
    assert app.salary_max == 160000
    assert app.department == "Engineering"


@pytest.mark.asyncio
async def test_submission_detection_no_overwrite(client, db_session):
    """Submission detection does not overwrite existing department or salary."""
    from backend.models import Application, Company

    company = Company(domain="existco.com", name="ExistCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app = Application(
        user_id=TEST_USER_ID,
        company="ExistCo",
        role_title="Dev",
        status="applied",
        company_id=company.id,
        department="Data",
        salary_min=100000,
        salary_max=140000,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.post(
        "/api/company-visits/submission",
        json={
            "platform": "lever",
            "url": "https://jobs.lever.co/existco/789",
            "domain": "existco.com",
            "application_id": str(app.id),
            "enrichment": {
                "salary": "$80,000 - $100,000",
                "department": "Marketing",
            },
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200

    await db_session.refresh(app)
    # Should NOT overwrite existing values
    assert app.department == "Data"
    assert app.salary_min == 100000
    assert app.salary_max == 140000


@pytest.mark.asyncio
async def test_submission_detection_without_application_id_does_not_mutate(client, db_session):
    """Loose domain-only confirmation signals are review-only."""
    from backend.models import Application, Company

    company = Company(domain="looseco.com", name="LooseCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    app = Application(
        user_id=TEST_USER_ID,
        company="LooseCo",
        role_title="Engineer",
        status="saved",
        company_id=company.id,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.post(
        "/api/company-visits/submission",
        json={
            "platform": "greenhouse",
            "url": "https://boards.greenhouse.io/looseco/jobs/456",
            "domain": "looseco.com",
            "enrichment": {"department": "Engineering"},
        },
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["matched"] is False
    assert data["updated"] is False
    assert data["requires_confirmation"] is True
    await db_session.refresh(app)
    assert app.status == "saved"
    assert app.department is None
