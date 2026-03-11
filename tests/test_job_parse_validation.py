from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_parse_job_rejects_http_urls(client):
    with patch("backend.main.extract_job", new_callable=AsyncMock) as mock_extract:
        response = await client.post(
            "/api/jobs/parse",
            json={"url": "http://boards.greenhouse.io/twitch/jobs/123"},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only HTTPS job URLs are allowed"
    mock_extract.assert_not_called()


@pytest.mark.asyncio
async def test_parse_job_rejects_private_ip_urls(client):
    with patch("backend.main.extract_job", new_callable=AsyncMock) as mock_extract:
        response = await client.post(
            "/api/jobs/parse",
            json={"url": "https://127.0.0.1/job/123"},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Local or private network addresses are not allowed"
    mock_extract.assert_not_called()


@pytest.mark.asyncio
async def test_parse_job_rejects_unsupported_hosts(client):
    with patch("backend.main.extract_job", new_callable=AsyncMock) as mock_extract:
        response = await client.post(
            "/api/jobs/parse",
            json={"url": "https://example.com/careers/123"},
            headers=AUTH_HEADER,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Job URL host is not supported"
    mock_extract.assert_not_called()


@pytest.mark.asyncio
async def test_validate_job_url_rejects_private_dns_resolution(monkeypatch):
    from backend.services import scraper

    class FakeLoop:
        async def getaddrinfo(self, *args, **kwargs):
            return [
                (None, None, None, None, ("10.0.0.12", 0)),
            ]

    monkeypatch.setattr(scraper.asyncio, "get_running_loop", lambda: FakeLoop())

    with pytest.raises(ValueError, match="Local or private network addresses are not allowed"):
        await scraper.validate_job_parse_url("https://boards.greenhouse.io/test/jobs/123")
