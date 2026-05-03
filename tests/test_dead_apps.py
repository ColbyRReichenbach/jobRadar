"""Sprint 7: Tests for dead application detection."""

from datetime import datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy import select
from unittest.mock import AsyncMock, patch, MagicMock

from tests.conftest import AUTH_HEADER, TEST_USER_ID


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


@pytest.mark.asyncio
async def test_dead_app_task_creates_pipeline_alert(db_session):
    from backend.models import Alert, Application, User
    from backend.tasks.check_dead_apps import _run_check

    class _SessionCtx:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    app = Application(
        user_id=TEST_USER_ID,
        company="DeadCo",
        role_title="Ghost Engineer",
        status="applied",
        job_url="https://example.com/dead",
        listing_alive=True,
        listing_last_checked=None,
        listing_died_at=None,
        applied_at=datetime.now(timezone.utc),
    )
    db_session.add(app)
    user_result = await db_session.execute(select(User).where(User.id == TEST_USER_ID))
    user = user_result.scalar_one()
    user.notifications_started_at = datetime.now(timezone.utc)
    await db_session.commit()

    with patch("backend.database.async_session_factory", return_value=_SessionCtx(db_session)):
        with patch("backend.tasks.check_dead_apps._check_url", new=AsyncMock(return_value={"alive": False, "reason": "404"})):
            result = await _run_check()

    assert result["dead"] == 1

    await db_session.refresh(app)
    assert app.listing_alive is False
    assert app.listing_died_at is not None

    alert_result = await db_session.execute(select(Alert).where(Alert.user_id == TEST_USER_ID))
    alert = alert_result.scalar_one()
    assert alert.alert_type == "dead_listing"
    assert alert.action_url == f"/dashboard?job_id={app.id}"
    assert "Posting may be closed at DeadCo" in alert.title
