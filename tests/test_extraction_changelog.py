"""Tests for extraction changelog + version-stats endpoints."""

import pytest
from tests.conftest import AUTH_HEADER


# ── Changelog CRUD ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_changelog_entry(client):
    """POST /api/extraction-changelog creates a new entry."""
    resp = await client.post(
        "/api/extraction-changelog",
        json={
            "version": "ext-2026.03.18a",
            "description": "Added Workday split-pane extraction + salary regex for USD format",
            "change_type": "extraction",
            "platforms_affected": ["workday"],
            "fields_affected": ["salary", "description"],
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "ext-2026.03.18a"
    assert data["description"].startswith("Added Workday")
    assert data["change_type"] == "extraction"
    assert data["platforms_affected"] == ["workday"]
    assert data["fields_affected"] == ["salary", "description"]
    assert data["id"] is not None
    assert data["created_at"] is not None


@pytest.mark.asyncio
async def test_create_changelog_duplicate_version(client):
    """Duplicate version returns 409."""
    payload = {
        "version": "ext-dup-test",
        "description": "First entry",
        "change_type": "extraction",
    }
    resp1 = await client.post("/api/extraction-changelog", json=payload, headers=AUTH_HEADER)
    assert resp1.status_code == 200

    resp2 = await client.post("/api/extraction-changelog", json=payload, headers=AUTH_HEADER)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_changelog_missing_fields(client):
    """Missing version or description returns 400."""
    resp = await client.post(
        "/api/extraction-changelog",
        json={"version": "ext-bad"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_changelog_invalid_change_type(client):
    """Invalid change_type returns 400."""
    resp = await client.post(
        "/api/extraction-changelog",
        json={
            "version": "ext-bad-type",
            "description": "test",
            "change_type": "invalid",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_changelog_entries(client):
    """GET /api/extraction-changelog returns entries ordered desc."""
    await client.post(
        "/api/extraction-changelog",
        json={"version": "ext-list-a", "description": "First", "change_type": "extraction"},
        headers=AUTH_HEADER,
    )
    await client.post(
        "/api/extraction-changelog",
        json={"version": "ext-list-b", "description": "Second", "change_type": "classifier"},
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/extraction-changelog", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    # Most recent first
    versions = [e["version"] for e in data]
    assert "ext-list-b" in versions
    assert "ext-list-a" in versions


@pytest.mark.asyncio
async def test_update_changelog_entry(client):
    """PATCH /api/extraction-changelog/{id} updates fields."""
    create = await client.post(
        "/api/extraction-changelog",
        json={"version": "ext-patch", "description": "Original", "change_type": "extraction"},
        headers=AUTH_HEADER,
    )
    entry_id = create.json()["id"]

    resp = await client.patch(
        f"/api/extraction-changelog/{entry_id}",
        json={"description": "Updated description", "change_type": "both"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Updated description"
    assert data["change_type"] == "both"
    assert data["version"] == "ext-patch"  # version unchanged


@pytest.mark.asyncio
async def test_update_nonexistent_changelog(client):
    """PATCH on nonexistent entry returns 404."""
    resp = await client.patch(
        "/api/extraction-changelog/00000000-0000-0000-0000-000000000000",
        json={"description": "nope"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 404


# ── Version Stats ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_version_stats_empty(client):
    """Version stats returns empty when no versioned reports exist."""
    resp = await client.get("/api/extraction-reports/version-stats", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert "versions" in data
    assert "changelog" in data
    assert isinstance(data["versions"], list)
    assert isinstance(data["changelog"], list)


@pytest.mark.asyncio
async def test_version_stats_with_reports(client):
    """Version stats computes per-version accuracy from reports."""
    # Create reports with extractor_version
    await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "wrong_data",
            "url": "https://a.com/jobs/1",
            "platform_detected": "workday",
            "fields_flagged": ["salary", "company"],
            "extractor_version": "ext-v1",
        },
        headers=AUTH_HEADER,
    )
    await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "false_positive",
            "url": "https://b.com/blog",
            "extractor_version": "ext-v1",
        },
        headers=AUTH_HEADER,
    )
    await client.post(
        "/api/extraction-reports",
        json={
            "report_type": "wrong_data",
            "url": "https://c.com/jobs/2",
            "fields_flagged": ["salary"],
            "extractor_version": "ext-v2",
        },
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/extraction-reports/version-stats", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()

    versions_by_name = {v["version"]: v for v in data["versions"]}
    assert "ext-v1" in versions_by_name
    assert "ext-v2" in versions_by_name

    v1 = versions_by_name["ext-v1"]
    assert v1["total_reports"] == 2
    assert v1["wrong_data_reports"] == 1
    assert v1["false_positive_reports"] == 1
    # Accuracy = 1 - (1 wrong / 2 total) = 0.5
    assert v1["accuracy_rate"] == 0.5
    # Field accuracy: salary flagged 1 out of 2 → 0.5, company 1 out of 2 → 0.5
    assert v1["field_accuracy"]["salary"] == 0.5
    assert v1["field_accuracy"]["company"] == 0.5

    v2 = versions_by_name["ext-v2"]
    assert v2["total_reports"] == 1
    assert v2["wrong_data_reports"] == 1
    # Accuracy = 1 - (1/1) = 0.0
    assert v2["accuracy_rate"] == 0.0


@pytest.mark.asyncio
async def test_version_stats_includes_changelog(client):
    """Version stats response includes changelog entries."""
    await client.post(
        "/api/extraction-changelog",
        json={"version": "ext-changelog-link", "description": "Test correlation", "change_type": "extraction"},
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/extraction-reports/version-stats", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    cl_versions = [c["version"] for c in data["changelog"]]
    assert "ext-changelog-link" in cl_versions
