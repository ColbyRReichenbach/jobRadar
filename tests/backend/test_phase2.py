import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import AUTH_HEADER, TEST_USER_ID


async def _grant_enrichment_consent(db_session):
    from backend.models import DataConsent, User

    now = datetime.now(timezone.utc)
    user = await db_session.get(User, TEST_USER_ID)
    user.data_consent_accepted_at = now
    db_session.add(
        DataConsent(
            user_id=TEST_USER_ID,
            consent_type="third_party_enrichment",
            granted=True,
            granted_at=now,
            updated_at=now,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_hunter_find_contacts():
    """Returns contacts for known domain (mocked)."""
    mock_response = {
        "data": {
            "emails": [
                {
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "value": "jane@stripe.com",
                    "position": "Senior Data Engineer",
                    "department": "engineering",
                    "seniority": "senior",
                    "confidence": 95,
                },
                {
                    "first_name": "John",
                    "last_name": "Smith",
                    "value": "john@stripe.com",
                    "position": "Marketing Coordinator",
                    "department": "marketing",
                    "seniority": "junior",
                    "confidence": 80,
                },
            ]
        }
    }

    with patch("backend.services.hunter.HUNTER_API_KEY", "test-key"):
        with patch("backend.services.hunter.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = mock_response
            from backend.services.hunter import find_contacts

            contacts = await find_contacts("stripe.com", "Stripe")
            assert len(contacts) == 1  # Only engineering/data/analytics pass filter
            assert contacts[0]["name"] == "Jane Doe"
            assert contacts[0]["email"] == "jane@stripe.com"
            assert contacts[0]["confidence_score"] == 0.95


@pytest.mark.asyncio
async def test_hunter_caching(client, db_session):
    """Second call for same domain hits cache, not Hunter API."""
    await _grant_enrichment_consent(db_session)

    # Create an application first
    app_resp = await client.post(
        "/api/jobs",
        json={
            "company": "CacheCorp",
            "role_title": "Engineer",
            "job_url": "https://example.com/job/cache-test",
            "source": "manual",
        },
        headers=AUTH_HEADER,
    )
    assert app_resp.status_code == 201
    app_id = app_resp.json()["id"]

    mock_response = {
        "data": {
            "emails": [
                {
                    "first_name": "Cache",
                    "last_name": "Test",
                    "value": "cache@test.com",
                    "position": "Data Scientist",
                    "department": "data",
                    "seniority": "senior",
                    "confidence": 90,
                }
            ]
        }
    }

    with patch("backend.services.hunter.HUNTER_API_KEY", "test-key"):
        with patch("backend.services.hunter.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = mock_response

            # First call
            resp1 = await client.post(
                "/api/contacts/find",
                json={"application_id": app_id, "company": "CacheCorp", "domain": "test.com"},
                headers=AUTH_HEADER,
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["cached"] is False
            assert len(data1["contacts"]) == 1

            # Second call — should use cache
            resp2 = await client.post(
                "/api/contacts/find",
                json={"application_id": app_id, "company": "CacheCorp", "domain": "test.com"},
                headers=AUTH_HEADER,
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["cached"] is True
            assert len(data2["contacts"]) == 1

            # with_retry should only be called once (first call)
            assert mock_retry.call_count == 1


@pytest.mark.asyncio
async def test_hunter_limit_degrades():
    """Mock 429 from Hunter returns [] not exception."""
    import httpx

    with patch("backend.services.hunter.HUNTER_API_KEY", "test-key"):
        with patch("backend.services.hunter.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_response = httpx.Response(429, request=httpx.Request("GET", "https://api.hunter.io"))
            mock_retry.side_effect = httpx.HTTPStatusError(
                "rate limited", request=mock_response.request, response=mock_response
            )
            from backend.services.hunter import find_contacts

            result = await find_contacts("example.com", "Example")
            assert result == []


@pytest.mark.asyncio
async def test_contacts_find_endpoint(client, db_session):
    """POST /api/contacts/find returns list + linkedin URL."""
    await _grant_enrichment_consent(db_session)

    # Create application
    app_resp = await client.post(
        "/api/jobs",
        json={
            "company": "FindCorp",
            "role_title": "Analyst",
            "job_url": "https://example.com/job/find-test",
            "source": "manual",
        },
        headers=AUTH_HEADER,
    )
    app_id = app_resp.json()["id"]

    mock_response = {
        "data": {
            "emails": [
                {
                    "first_name": "Alice",
                    "last_name": "Johnson",
                    "value": "alice@findcorp.com",
                    "position": "Analytics Manager",
                    "department": "analytics",
                    "seniority": "manager",
                    "confidence": 88,
                }
            ]
        }
    }

    with patch("backend.services.hunter.HUNTER_API_KEY", "test-key"):
        with patch("backend.services.hunter.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = mock_response

            resp = await client.post(
                "/api/contacts/find",
                json={"application_id": app_id, "company": "FindCorp", "domain": "findcorp.com"},
                headers=AUTH_HEADER,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "contacts" in data
            assert "linkedin_search_url" in data
            assert len(data["contacts"]) == 1
            assert data["contacts"][0]["name"] == "Alice Johnson"
            assert data["contacts"][0]["email"] == "alice@findcorp.com"


@pytest.mark.asyncio
async def test_contact_update(client, db_session):
    """PATCH /api/contacts/{id} updates reached_out fields."""
    await _grant_enrichment_consent(db_session)

    # Create application + contact
    app_resp = await client.post(
        "/api/jobs",
        json={
            "company": "PatchCorp",
            "role_title": "Dev",
            "job_url": "https://example.com/job/patch-test",
            "source": "manual",
        },
        headers=AUTH_HEADER,
    )
    app_id = app_resp.json()["id"]

    mock_response = {
        "data": {
            "emails": [
                {
                    "first_name": "Bob",
                    "last_name": "Update",
                    "value": "bob@patch.com",
                    "position": "Data Director",
                    "department": "data",
                    "seniority": "director",
                    "confidence": 75,
                }
            ]
        }
    }

    with patch("backend.services.hunter.HUNTER_API_KEY", "test-key"):
        with patch("backend.services.hunter.with_retry", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = mock_response

            find_resp = await client.post(
                "/api/contacts/find",
                json={"application_id": app_id, "company": "PatchCorp", "domain": "patch.com"},
                headers=AUTH_HEADER,
            )
            contact_id = find_resp.json()["contacts"][0]["id"]

    # PATCH to mark reached_out
    patch_resp = await client.patch(
        f"/api/contacts/{contact_id}",
        json={"reached_out": True},
        headers=AUTH_HEADER,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["reached_out"] is True
    assert updated["reached_out_at"] is not None


@pytest.mark.asyncio
async def test_contacts_find_without_enrichment_consent_returns_no_contacts(client):
    app_resp = await client.post(
        "/api/jobs",
        json={
            "company": "NoConsentCo",
            "role_title": "Analyst",
            "job_url": "https://example.com/job/no-consent-test",
            "source": "manual",
        },
        headers=AUTH_HEADER,
    )
    app_id = app_resp.json()["id"]

    resp = await client.post(
        "/api/contacts/find",
        json={"application_id": app_id, "company": "NoConsentCo", "domain": "noconsent.co"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["contacts"] == []
    assert data["cached"] is False
    assert data["enrichment_enabled"] is False
    assert "linkedin_search_url" in data


@pytest.mark.asyncio
async def test_linkedin_search_url_format():
    """URL contains company name, and school if provided."""
    from backend.services.hunter import generate_linkedin_search_url

    # Without school — just company
    url = generate_linkedin_search_url("Stripe")
    assert "Stripe" in url
    assert "linkedin.com/search/results/people" in url

    # With school — includes both
    url_with_school = generate_linkedin_search_url("Stripe", school="UNC Chapel Hill")
    assert "UNC+Chapel+Hill" in url_with_school or "UNC Chapel Hill" in url_with_school
    assert "Stripe" in url_with_school
    assert "linkedin.com/search/results/people" in url_with_school
