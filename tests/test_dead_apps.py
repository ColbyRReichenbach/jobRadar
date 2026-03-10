"""Sprint 7: Tests for dead application detection."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_listing_alive_default(client):
    """New applications default to listing_alive=True."""
    resp = await client.post(
        "/api/jobs",
        json={
            "company": "TestCo",
            "role_title": "SWE",
            "job_url": "https://example.com/job/123",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["listing_alive"] is True
    assert data["listing_died_at"] is None


@pytest.mark.asyncio
async def test_dead_listing_serialized(client, db_session):
    """Dead listing fields are serialized in job response."""
    from backend.models import Application
    from datetime import datetime, timezone

    app = Application(
        company="DeadCo",
        role_title="Ghost Engineer",
        job_url="https://example.com/dead",
        listing_alive=False,
        listing_died_at=datetime.now(timezone.utc),
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.get("/api/jobs", headers=AUTH_HEADER)
    assert resp.status_code == 200
    jobs = resp.json()
    dead_job = next((j for j in jobs if j["company"] == "DeadCo"), None)
    assert dead_job is not None
    assert dead_job["listing_alive"] is False
    assert dead_job["listing_died_at"] is not None


# --- Unit tests for URL checking ---

from backend.tasks.check_dead_apps import _check_url, DEAD_SIGNALS


@pytest.mark.asyncio
async def test_check_url_404():
    """404 response marks job as dead."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.url = "https://example.com/job/404"

    with patch("backend.tasks.check_dead_apps.asyncio.sleep", new_callable=AsyncMock):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _check_url("https://example.com/job/404")
            assert result["alive"] is False
            assert "404" in result["reason"]


@pytest.mark.asyncio
async def test_check_url_alive():
    """200 response with no dead signals marks job as alive."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>Great job opportunity! Apply now.</body></html>"
    mock_response.url = "https://example.com/job/123"

    with patch("backend.tasks.check_dead_apps.asyncio.sleep", new_callable=AsyncMock):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _check_url("https://example.com/job/123")
            assert result["alive"] is True


@pytest.mark.asyncio
async def test_check_url_dead_signal():
    """Response containing dead signal text marks job as dead."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>Sorry, this position has been filled.</body></html>"
    mock_response.url = "https://example.com/job/filled"

    with patch("backend.tasks.check_dead_apps.asyncio.sleep", new_callable=AsyncMock):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await _check_url("https://example.com/job/filled")
            assert result["alive"] is False


@pytest.mark.asyncio
async def test_check_url_network_error():
    """Network errors don't mark job as dead (graceful degradation)."""
    with patch("backend.tasks.check_dead_apps.asyncio.sleep", new_callable=AsyncMock):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("Connection timeout"))
            mock_client_cls.return_value = mock_client

            result = await _check_url("https://example.com/job/timeout")
            assert result["alive"] is True  # Don't mark dead on network issues
