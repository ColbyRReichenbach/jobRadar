import pytest


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_payload(client):
    await client.get("/api/health")
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "apptrail_http_requests_total" in body
    assert 'path="/api/health"' in body
    assert "apptrail_http_request_duration_seconds" in body
    assert "apptrail_http_requests_in_progress" in body
