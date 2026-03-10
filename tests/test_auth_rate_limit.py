import pytest


@pytest.mark.asyncio
async def test_auth_routes_are_rate_limited_per_ip(client):
    for _ in range(5):
        response = await client.post("/api/auth/refresh")
        assert response.status_code == 401

    limited_response = await client.post("/api/auth/refresh")

    assert limited_response.status_code == 429
    assert "Too many auth requests" in limited_response.json()["detail"]
