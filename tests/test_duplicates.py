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
async def test_job_duplicate_check_normalizes_tracking_params(client):
    create_resp = await client.post(
        "/api/jobs",
        json={
            "company": "Acme",
            "role_title": "Backend Engineer",
            "job_url": "https://jobs.example.com/acme/backend/?utm_source=linkedin&gh_jid=123",
        },
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["job_url"] == "https://jobs.example.com/acme/backend"

    resp = await client.post(
        "/api/jobs/duplicates/check",
        json={
            "company": "Acme",
            "role_title": "Backend Engineer",
            "job_url": "https://jobs.example.com/acme/backend?utm_medium=email",
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


@pytest.mark.asyncio
async def test_contact_keep_separate_suppresses_future_soft_warning(client):
    create_resp = await client.post(
        "/api/contacts",
        json={"name": "Audrey Lane", "email": "audrey.one@example.com"},
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201

    keep_resp = await client.post(
        "/api/contacts/duplicates/keep-separate",
        json={
            "name": "Audrey Lane",
            "email": "audrey.two@example.com",
            "match_email": "audrey.one@example.com",
        },
        headers=AUTH_HEADER,
    )
    assert keep_resp.status_code == 201

    resp = await client.post(
        "/api/contacts/duplicates/check",
        json={"name": "Audrey Lane", "email": "audrey.two@example.com"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate_type"] == "none"


@pytest.mark.asyncio
async def test_contact_merge_updates_target_and_removes_source(client):
    target_resp = await client.post(
        "/api/contacts",
        json={
            "name": "Audrey Lane",
            "email": "audrey.one@example.com",
            "title": "Recruiter",
        },
        headers=AUTH_HEADER,
    )
    assert target_resp.status_code == 201
    target = target_resp.json()

    source_resp = await client.post(
        "/api/contacts",
        json={
            "name": "Audrey Lane",
            "email": "audrey.two@example.com",
            "company_name": "Acme",
            "phone_number": "+15555550123",
        },
        headers=AUTH_HEADER,
    )
    assert source_resp.status_code == 201
    source = source_resp.json()

    merge_resp = await client.post(
        "/api/contacts/merge",
        json={
            "target_contact_id": target["id"],
            "source_contact_id": source["id"],
            "name": "Audrey Lane",
            "email": "audrey.one@example.com",
            "title": "Senior Recruiter",
            "company_name": "Acme",
            "phone_number": "+15555550123",
        },
        headers=AUTH_HEADER,
    )
    assert merge_resp.status_code == 200
    merged = merge_resp.json()
    assert merged["title"] == "Senior Recruiter"
    assert merged["company"] == "Acme"
    assert merged["phone_number"] == "+15555550123"

    dup_resp = await client.post(
        "/api/contacts/duplicates/check",
        json={"email": "audrey.two@example.com"},
        headers=AUTH_HEADER,
    )
    assert dup_resp.status_code == 200
    assert dup_resp.json()["duplicate_type"] == "none"
