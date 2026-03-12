import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_job_duplicate_check_by_url(client):
    create_resp = await client.post(
        "/api/jobs",
        json={
            "company": "Acme",
            "role_title": "Backend Engineer",
            "job_url": "https://jobs.example.com/acme/backend",
        },
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201

    resp = await client.post(
        "/api/jobs/duplicates/check",
        json={
            "company": "Acme",
            "role_title": "Backend Engineer",
            "job_url": "https://jobs.example.com/acme/backend",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate_type"] == "hard"
    assert len(data["matches"]) == 1


@pytest.mark.asyncio
async def test_job_duplicate_check_by_company_and_role(client):
    create_resp = await client.post(
        "/api/jobs",
        json={
            "company": "Acme",
            "role_title": "Backend Engineer",
            "location": "Remote",
        },
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201

    resp = await client.post(
        "/api/jobs/duplicates/check",
        json={
            "company": "Acme",
            "role_title": "Backend Engineer",
            "location": "Remote",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate_type"] == "soft"
    assert len(data["matches"]) == 1


@pytest.mark.asyncio
async def test_contact_duplicate_check_by_email(client):
    create_resp = await client.post(
        "/api/contacts",
        json={"name": "Taylor Smith", "email": "taylor@example.com"},
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201

    resp = await client.post(
        "/api/contacts/duplicates/check",
        json={"email": "taylor@example.com"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate_type"] == "hard"
    assert len(data["matches"]) == 1


@pytest.mark.asyncio
async def test_contact_duplicate_check_by_name(client):
    create_resp = await client.post(
        "/api/contacts",
        json={"name": "Audrey Lane", "email": "audrey.one@example.com"},
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201

    resp = await client.post(
        "/api/contacts/duplicates/check",
        json={"name": "Audrey Lane", "email": "audrey.two@example.com"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate_type"] == "soft"
    assert len(data["matches"]) == 1
