import pytest

from backend.services.research_radar.schemas import SearchCandidate
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


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_research_radar_metrics(client, monkeypatch):
    async def _fake_search(query: str, max_results: int):
        return [
            SearchCandidate(
                url="https://example.com/careers/platform-engineer",
                title="Platform Engineer at Example",
                snippet="Example is hiring a platform engineer for its data platform team.",
                source_type="company_careers",
                domain="example.com",
                published_at="2026-04-22T12:00:00+00:00",
                why_selected=query,
            )
        ]

    async def _fake_fetch(url: str):
        return (
            "<html><body><h1>Platform Engineer</h1><p>Example is growing its data platform team.</p></body></html>",
            "Platform Engineer Example is growing its data platform team.",
        )

    monkeypatch.setattr("backend.services.research_radar.nodes.search.search_public_web", _fake_search)
    monkeypatch.setattr("backend.services.research_radar.nodes.fetch.fetch_document", _fake_fetch)

    consent_resp = await client.put(
        "/api/consent",
        json={
            "core": True,
            "ai_processing": True,
            "third_party_enrichment": False,
            "web_research": True,
        },
        headers=AUTH_HEADER,
    )
    assert consent_resp.status_code == 200

    profile_resp = await client.post(
        "/api/research/profiles",
        json={
            "name": "Metrics Tracker",
            "mode": "research",
            "depth": "quick",
            "selected_roles": ["Platform Engineer"],
            "selected_companies": ["Example"],
            "include_public_web_research": True,
            "max_search_queries": 1,
            "max_sources_per_run": 2,
        },
        headers=AUTH_HEADER,
    )
    assert profile_resp.status_code == 201

    run_resp = await client.post(f"/api/research/profiles/{profile_resp.json()['id']}/run", headers=AUTH_HEADER)
    assert run_resp.status_code == 202

    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "apptrail_research_runs_total" in body
    assert "apptrail_research_run_duration_seconds" in body
    assert "apptrail_research_run_step_duration_seconds" in body
    assert "apptrail_research_reports_generated_total" in body
    assert "apptrail_research_sources_fetched_total" in body
    assert "apptrail_research_evidence_items_total" in body
    assert 'mode="research"' in body
