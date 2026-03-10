import pytest
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_auth_required(client):
    resp = await client.get("/api/jobs")
    assert resp.status_code in (401, 422)


@pytest.mark.asyncio
async def test_create_application(client):
    payload = {
        "company": "TestCorp",
        "role_title": "Data Scientist",
        "job_url": "https://example.com/job/1",
        "source": "manual",
    }
    resp = await client.post("/api/jobs", json=payload, headers=AUTH_HEADER)
    assert resp.status_code == 201
    data = resp.json()
    assert data["company"] == "TestCorp"
    assert data["role_title"] == "Data Scientist"
    assert data["status"] == "saved"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_duplicate_returns_409(client):
    payload = {
        "company": "DupeCorp",
        "role_title": "Engineer",
        "job_url": "https://example.com/job/dup",
        "source": "manual",
    }
    resp1 = await client.post("/api/jobs", json=payload, headers=AUTH_HEADER)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/jobs", json=payload, headers=AUTH_HEADER)
    assert resp2.status_code == 409
    detail = resp2.json()["detail"]
    assert detail["message"] == "Already tracked"
    assert "existing" in detail


@pytest.mark.asyncio
async def test_list_applications(client):
    payload = {
        "company": "ListCorp",
        "role_title": "Analyst",
        "job_url": "https://example.com/job/list1",
        "source": "manual",
    }
    await client.post("/api/jobs", json=payload, headers=AUTH_HEADER)

    resp = await client.get("/api/jobs", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(a["company"] == "ListCorp" for a in data)


@pytest.mark.asyncio
async def test_archived_filtered(client, db_session):
    from datetime import datetime, timezone
    from backend.models import Application

    app_record = Application(
        company="ArchivedCorp",
        role_title="Old Role",
        job_url="https://example.com/job/archived",
        source="manual",
        archived_at=datetime.now(timezone.utc),
    )
    db_session.add(app_record)
    await db_session.commit()

    resp = await client.get("/api/jobs", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert not any(a["company"] == "ArchivedCorp" for a in data)

    # With archived=true, it should appear
    resp2 = await client.get("/api/jobs?archived=true", headers=AUTH_HEADER)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert any(a["company"] == "ArchivedCorp" for a in data2)


@pytest.mark.asyncio
async def test_greenhouse_parse(client):
    """Test parsing a real Greenhouse job URL via the API.
    First fetches a live job ID from Twitch's board, then parses it.
    """
    import httpx as _httpx

    # Find a live Greenhouse job ID
    async with _httpx.AsyncClient(timeout=10, follow_redirects=True) as hc:
        list_resp = await hc.get("https://boards-api.greenhouse.io/v1/boards/twitch/jobs")
        assert list_resp.status_code == 200
        jobs = list_resp.json().get("jobs", [])
        assert len(jobs) > 0, "No live Twitch Greenhouse jobs found"
        live_job_id = jobs[0]["id"]

    resp = await client.post(
        "/api/jobs/parse",
        json={"url": f"https://boards.greenhouse.io/twitch/jobs/{live_job_id}"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    result = data["data"]
    assert result.get("source") == "greenhouse"
    assert result.get("title") is not None
    assert result.get("company") == "twitch"
