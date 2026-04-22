import pytest

from tests.conftest import AUTH_HEADER


@pytest.fixture(autouse=True)
def reset_ai_metrics_state():
    from backend.services.ai_orchestrator import reset_metrics_for_tests

    reset_metrics_for_tests()
    yield
    reset_metrics_for_tests()


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_payload(client):
    from backend.services.ai_orchestrator import record_fallback

    await client.get("/api/health")
    record_fallback("email_classifier", "task_failure")
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "apptrail_http_requests_total" in body
    assert 'path="/api/health"' in body
    assert "apptrail_http_request_duration_seconds" in body
    assert "apptrail_http_requests_in_progress" in body
    assert "apptrail_ai_task_fallbacks_total" in body
    assert 'task="email_classifier"' in body


@pytest.mark.asyncio
async def test_ai_metrics_endpoint_returns_task_snapshot(client):
    from backend.services.ai_orchestrator import record_fallback

    record_fallback("resume_parser", "disabled_or_unconfigured", {"surface": "resume_parser"})

    response = await client.get("/api/ai/metrics", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    resume_parser = next(task for task in data["tasks"] if task["task"] == "resume_parser")
    assert resume_parser["model"] == "gpt-4o-mini"
    assert resume_parser["fallbacks"] == 1
    assert resume_parser["last_fallback_reason"] == "disabled_or_unconfigured"
