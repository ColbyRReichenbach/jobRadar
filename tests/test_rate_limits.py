from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.models import GmailToken
from tests.conftest import AUTH_HEADER, TEST_USER_ID


@pytest.mark.asyncio
async def test_job_parse_endpoint_is_rate_limited(monkeypatch, client):
    monkeypatch.setenv("APPTRAIL_JOB_PARSE_RATE_LIMIT", "2/minute")

    with patch("backend.main.validate_job_parse_url", new=AsyncMock(side_effect=lambda url: url)):
        with patch("backend.main.extract_job", new=AsyncMock(return_value={"company": "Rate Limited Co"})):
            for _ in range(2):
                response = await client.post(
                    "/api/jobs/parse",
                    headers=AUTH_HEADER,
                    json={"url": "https://www.linkedin.com/jobs/view/123"},
                )
                assert response.status_code == 200

            limited_response = await client.post(
                "/api/jobs/parse",
                headers=AUTH_HEADER,
                json={"url": "https://www.linkedin.com/jobs/view/123"},
            )

    assert limited_response.status_code == 429
    assert "Too many job parse requests" in limited_response.json()["detail"]


@pytest.mark.asyncio
async def test_search_endpoint_is_rate_limited(monkeypatch, client):
    monkeypatch.setenv("APPTRAIL_SEARCH_RATE_LIMIT", "2/minute")

    with patch("backend.services.job_search.search_jobs", new=AsyncMock(return_value=[])):
        for _ in range(2):
            response = await client.get(
                "/api/search",
                params={"q": "engineer"},
                headers=AUTH_HEADER,
            )
            assert response.status_code == 200

        limited_response = await client.get(
            "/api/search",
            params={"q": "engineer"},
            headers=AUTH_HEADER,
        )

    assert limited_response.status_code == 429
    assert "Too many search requests" in limited_response.json()["detail"]


@pytest.mark.asyncio
async def test_send_email_endpoint_is_rate_limited(monkeypatch, client, db_session):
    monkeypatch.setenv("APPTRAIL_SEND_EMAIL_RATE_LIMIT", "2/minute")

    db_session.add(
        GmailToken(
            user_id=TEST_USER_ID,
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    await db_session.commit()

    with patch("googleapiclient.discovery.build", return_value=Mock()):
        with patch("backend.services.email_sender.send_email", new=AsyncMock(return_value={"status": "ok"})):
            payload = {
                "to": "recruiter@example.com",
                "subject": "Checking in",
                "body": "Just following up on my application.",
            }
            for _ in range(2):
                response = await client.post(
                    "/api/emails/send",
                    headers=AUTH_HEADER,
                    json=payload,
                )
                assert response.status_code == 201

            limited_response = await client.post(
                "/api/emails/send",
                headers=AUTH_HEADER,
                json=payload,
            )

    assert limited_response.status_code == 429
    assert "Too many send email requests" in limited_response.json()["detail"]
