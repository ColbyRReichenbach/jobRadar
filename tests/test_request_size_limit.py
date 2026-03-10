import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_request_body_limit_rejects_payloads_over_1mb(client):
    response = await client.post(
        "/api/company-visits/submission",
        json={
            "platform": "greenhouse",
            "url": "https://example.com/apply",
            "domain": "example.com",
            "enrichment": {
                "blob": "x" * (1024 * 1024),
            },
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 413
    assert "1MB" in response.json()["detail"]
