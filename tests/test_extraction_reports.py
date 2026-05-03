"""Tests for extraction report endpoints."""

import pytest
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_create_extraction_report(client):
    """POST /api/extraction-reports creates a new report."""
    resp = await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "missing_data",
            "url": "https://example.com/jobs/123",
            "domain": "example.com",
            "platform_detected": "generic",
            "fields_flagged": ["salary", "description"],
            "notes": "Salary was in the description but not extracted.",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["report_type"] == "missing_data"
    assert data["url"] == "https://example.com/jobs/123"
    assert data["id"] is not None
    assert data["created_at"] is not None


@pytest.mark.asyncio
async def test_create_wrong_data_report_with_diff(client):
    """Reports include extracted vs corrected data for diffing."""
    resp = await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "wrong_data",
            "url": "https://draftkings.wd5.myworkdayjobs.com/en-US/DraftKings_Careers/job/Engineer",
            "domain": "myworkdayjobs.com",
            "platform_detected": "workday",
            "extraction_method": "platform",
            "extracted_data": {
                "company": "DK Crown Holdings Inc.",
                "title": "Software Engineer",
                "salary": None,
            },
            "corrected_data": {
                "company": "DraftKings",
                "title": "Software Engineer",
                "salary": "$170,600 - $213,250 USD",
            },
            "fields_flagged": ["company", "salary"],
            "extension_version": "1.0.0",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["report_type"] == "wrong_data"


@pytest.mark.asyncio
async def test_create_undetected_site_report(client):
    """Undetected site reports capture the URL for analysis."""
    resp = await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "undetected_site",
            "url": "https://newplatform.com/careers/swe-123",
            "domain": "newplatform.com",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["report_type"] == "undetected_site"


@pytest.mark.asyncio
async def test_create_false_positive_report(client):
    """False positive reports flag pages wrongly detected as jobs."""
    resp = await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "false_positive",
            "url": "https://company.com/blog/careers-at-company",
            "domain": "company.com",
            "platform_detected": "generic",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_invalid_report_type(client):
    """Invalid report_type returns 400."""
    resp = await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "invalid_type",
            "url": "https://example.com/jobs/123",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_extraction_reports(client):
    """GET /api/extraction-reports returns all reports."""
    # Create a couple of reports
    await client.post(
        "/api/extraction-reports",
        json={"report_type": "missing_data", "url": "https://a.com/jobs/1", "platform_detected": "workday"},
        headers=AUTH_HEADER,
    )
    await client.post(
        "/api/extraction-reports",
        json={"report_type": "false_positive", "url": "https://b.com/blog", "platform_detected": "generic"},
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/extraction-reports", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_list_with_type_filter(client):
    """Filtering by report_type works."""
    await client.post(
        "/api/extraction-reports",
        json={"report_type": "undetected_site", "url": "https://new.io/jobs/1"},
        headers=AUTH_HEADER,
    )
    await client.post(
        "/api/extraction-reports",
        json={"report_type": "missing_data", "url": "https://old.io/jobs/2"},
        headers=AUTH_HEADER,
    )

    resp = await client.get(
        "/api/extraction-reports?report_type=undetected_site",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["report_type"] == "undetected_site" for r in data)


@pytest.mark.asyncio
async def test_extraction_report_stats(client):
    """GET /api/extraction-reports/stats returns aggregate data."""
    await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "wrong_data",
            "url": "https://x.com/jobs/1",
            "platform_detected": "linkedin",
            "fields_flagged": ["salary", "company"],
        },
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/extraction-reports/stats", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "unresolved" in data
    assert "by_type" in data
    assert "by_platform" in data
    assert "by_field" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_resolve_extraction_report(client):
    """PATCH /api/extraction-reports/{id} marks resolved."""
    create_resp = await client.post(
        "/api/extraction-reports",
        json={"report_type": "missing_data", "url": "https://z.com/jobs/1"},
        headers=AUTH_HEADER,
    )
    report_id = create_resp.json()["id"]

    # Resolve
    resp = await client.patch(
        f"/api/extraction-reports/{report_id}",
        json={"resolved": True},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True

    # Verify in list
    list_resp = await client.get(
        "/api/extraction-reports?resolved=true",
        headers=AUTH_HEADER,
    )
    resolved_ids = [r["id"] for r in list_resp.json()]
    assert report_id in resolved_ids


@pytest.mark.asyncio
async def test_resolve_nonexistent_report(client):
    """PATCH on a nonexistent report returns 404."""
    resp = await client.patch(
        "/api/extraction-reports/00000000-0000-0000-0000-000000000000",
        json={"resolved": True},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 404
