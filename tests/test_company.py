"""Tests for Sprint 2: Company Entity."""
import pytest
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_create_job_auto_creates_company(client):
    """Creating a job with a URL should auto-create a company record."""
    res = await client.post("/api/jobs", json={
        "company": "Stripe",
        "role_title": "Software Engineer",
        "job_url": "https://stripe.com/jobs/1234",
    }, headers=AUTH_HEADER)
    assert res.status_code == 201
    data = res.json()
    assert data["company_id"] is not None

    # Company should be listed
    companies_res = await client.get("/api/companies", headers=AUTH_HEADER)
    assert companies_res.status_code == 200
    companies = companies_res.json()
    assert len(companies) >= 1
    assert any(c["domain"] == "stripe.com" for c in companies)


@pytest.mark.asyncio
async def test_company_detail_endpoint(client):
    """GET /api/companies/{domain} returns company profile."""
    # Create a job to create the company
    await client.post("/api/jobs", json={
        "company": "Google",
        "role_title": "SRE",
        "job_url": "https://google.com/jobs/sre",
    }, headers=AUTH_HEADER)

    res = await client.get("/api/companies/google.com", headers=AUTH_HEADER)
    assert res.status_code == 200
    data = res.json()
    assert data["domain"] == "google.com"
    assert data["name"] == "Google"
    assert "jobs" in data
    assert len(data["jobs"]) >= 1


@pytest.mark.asyncio
async def test_company_not_found(client):
    """GET /api/companies/{domain} returns 404 for unknown domain."""
    res = await client.get("/api/companies/nonexistent.example.com", headers=AUTH_HEADER)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_platform_domain_no_company(client):
    """Platform domains (gmail.com, etc.) should not create companies."""
    res = await client.post("/api/jobs", json={
        "company": "SomeCompany",
        "role_title": "Dev",
        "job_url": "https://gmail.com/something",
    }, headers=AUTH_HEADER)
    assert res.status_code == 201
    data = res.json()
    assert data["company_id"] is None


@pytest.mark.asyncio
async def test_company_upsert_idempotent(client):
    """Creating two jobs with same domain should link to same company."""
    res1 = await client.post("/api/jobs", json={
        "company": "Meta",
        "role_title": "Engineer",
        "job_url": "https://meta.com/jobs/1",
    }, headers=AUTH_HEADER)
    res2 = await client.post("/api/jobs", json={
        "company": "Meta",
        "role_title": "PM",
        "job_url": "https://meta.com/jobs/2",
    }, headers=AUTH_HEADER)
    assert res1.json()["company_id"] == res2.json()["company_id"]

    # Companies list should have exactly one meta.com
    companies_res = await client.get("/api/companies", headers=AUTH_HEADER)
    meta_companies = [c for c in companies_res.json() if c["domain"] == "meta.com"]
    assert len(meta_companies) == 1
    assert meta_companies[0]["job_count"] == 2
