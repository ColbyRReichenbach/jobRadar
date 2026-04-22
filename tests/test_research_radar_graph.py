import uuid

import pytest
from sqlalchemy import select

from backend.models import ResearchReport, ResearchRun, ResearchRunStep
from backend.services.research_radar.llm import deterministic_normalized_brief, deterministic_research_plan
from backend.services.research_radar.nodes.dedupe import dedupe_and_rank_evidence
from backend.services.research_radar.schemas import SearchCandidate
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_deterministic_normalized_brief_fills_from_context():
    tracker = {
        "objective": "Find strong data-platform roles.",
        "selected_roles": [],
        "selected_domains": ["developer_tools"],
        "selected_companies": ["TraceCo"],
        "target_locations": [],
        "remote_types": [],
        "seniority_levels": ["staff"],
        "keywords": ["platform", "data"],
        "excluded_keywords": ["intern"],
        "report_prompt_notes": "Bias toward platform ownership.",
    }
    user_context = {
        "role_interest_labels": ["Data Platform Engineer"],
        "preferred_locations": ["New York"],
        "preferred_remote_type": "hybrid",
        "skills": ["Python", "SQL"],
        "tools": ["Airflow", "dbt"],
        "experience_years": 6,
    }

    brief = deterministic_normalized_brief(tracker, user_context)
    assert brief.ideal_role_titles == ["Data Platform Engineer"]
    assert brief.target_locations == ["New York"]
    assert brief.remote_preferences == ["hybrid"]
    assert "Bias toward platform ownership." in brief.search_constraints


@pytest.mark.asyncio
async def test_deterministic_research_plan_respects_depth_limits():
    normalized_brief = {
        "search_objective": "Find public hiring signals for platform engineering roles.",
        "ideal_role_titles": ["Platform Engineer", "Data Engineer"],
        "target_domains": ["developer_tools", "data_infra"],
        "target_companies": ["TraceCo", "Signal Labs", "Northwind"],
    }

    quick_plan = deterministic_research_plan(normalized_brief, "quick", 10)
    deep_plan = deterministic_research_plan(normalized_brief, "deep", 10)

    assert len(quick_plan) <= 4
    assert len(deep_plan) <= 10
    assert quick_plan[0].task_type == "role_openings"


@pytest.mark.asyncio
async def test_dedupe_and_rank_evidence_prefers_stronger_source():
    state = {
        "evidence_items": [
            {
                "evidence_type": "role_opening",
                "company_name": "TraceCo",
                "role_title": "Platform Engineer",
                "url": "https://traceco.com/jobs/1",
                "domain": "traceco.com",
                "confidence": 0.7,
                "relevance_score": 0.5,
                "novelty_score": 0.5,
            },
            {
                "evidence_type": "role_opening",
                "company_name": "TraceCo",
                "role_title": "Platform Engineer",
                "url": "https://traceco.com/jobs/1?ref=feed",
                "domain": "traceco.com",
                "confidence": 0.9,
                "relevance_score": 0.6,
                "novelty_score": 0.6,
            },
        ]
    }
    result = await dedupe_and_rank_evidence(state)
    assert len(result["evidence_items"]) == 1
    assert result["evidence_items"][0]["confidence"] == 0.9


@pytest.mark.asyncio
async def test_research_mode_run_persists_report_and_steps(client, monkeypatch, db_session):
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

    profile_resp = await client.post(
        "/api/research/profiles",
        json={
            "name": "Research Tracker",
            "mode": "research",
            "depth": "quick",
            "selected_roles": ["Platform Engineer"],
            "selected_companies": ["Example"],
            "include_public_web_research": True,
            "max_search_queries": 2,
            "max_sources_per_run": 3,
        },
        headers=AUTH_HEADER,
    )
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()["id"]

    run_resp = await client.post(f"/api/research/profiles/{profile_id}/run", headers=AUTH_HEADER)
    assert run_resp.status_code == 202
    run_id = run_resp.json()["id"]

    run_detail = await client.get(f"/api/research/runs/{run_id}", headers=AUTH_HEADER)
    assert run_detail.status_code == 200
    run_payload = run_detail.json()
    assert run_payload["status"] == "published"
    assert run_payload["report_id"] is not None
    assert run_payload["orchestrator_version"] == "research_graph_v1"
    assert run_payload["graph_thread_id"] is not None

    report_resp = await client.get(f"/api/research/reports/{run_payload['report_id']}", headers=AUTH_HEADER)
    assert report_resp.status_code == 200
    report_payload = report_resp.json()
    assert report_payload["status"] == "published"
    assert report_payload["sections"]
    assert report_payload["evidence"]
    assert report_payload["actions"]

    accept_resp = await client.post(
        f"/api/research/reports/{run_payload['report_id']}/actions/{report_payload['actions'][0]['id']}/accept",
        headers=AUTH_HEADER,
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["status"] == "accepted"

    step_rows = (
        await db_session.execute(
            select(ResearchRunStep).where(ResearchRunStep.run_id == uuid.UUID(run_id)).order_by(ResearchRunStep.step_order.asc())
        )
    ).scalars().all()
    assert len(step_rows) == 15
    assert step_rows[0].step_name == "load_tracker_context"
    assert step_rows[-1].step_name == "schedule_next_run"
    assert all(step.status == "succeeded" for step in step_rows)

    report_rows = (await db_session.execute(select(ResearchReport))).scalars().all()
    assert len(report_rows) == 1


@pytest.mark.asyncio
async def test_research_mode_failed_step_is_persisted(client, monkeypatch, db_session):
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

    async def _boom(url: str):
        raise RuntimeError("fetch exploded")

    monkeypatch.setattr("backend.services.research_radar.nodes.search.search_public_web", _fake_search)
    monkeypatch.setattr("backend.services.research_radar.nodes.fetch.fetch_document", _boom)

    profile_resp = await client.post(
        "/api/research/profiles",
        json={
            "name": "Broken Research Tracker",
            "mode": "research",
            "depth": "quick",
            "selected_roles": ["Platform Engineer"],
            "selected_companies": ["Example"],
            "include_public_web_research": True,
        },
        headers=AUTH_HEADER,
    )
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()["id"]

    run_resp = await client.post(f"/api/research/profiles/{profile_id}/run", headers=AUTH_HEADER)
    assert run_resp.status_code == 202
    run_id = uuid.UUID(run_resp.json()["id"])

    run = (
        await db_session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalars().first()
    assert run is not None
    assert run.status == "failed"
    assert "fetch exploded" in (run.error_message or "")
    assert run.status_detail["failed_step"] == "fetch_documents"

    failed_step = (
        await db_session.execute(
            select(ResearchRunStep)
            .where(ResearchRunStep.run_id == run_id, ResearchRunStep.step_name == "fetch_documents")
        )
    ).scalars().first()
    assert failed_step is not None
    assert failed_step.status == "failed"
    assert "fetch exploded" in (failed_step.error_message or "")


@pytest.mark.asyncio
async def test_second_research_report_persists_diff_payload(client, monkeypatch):
    call_count = {"count": 0}

    async def _fake_search(query: str, max_results: int):
        call_count["count"] += 1
        candidates = [
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
        if call_count["count"] >= 2:
            candidates.append(
                SearchCandidate(
                    url="https://acme.com/careers/ml-platform",
                    title="ML Platform Engineer at Acme",
                    snippet="Acme is building a new machine learning platform team.",
                    source_type="company_careers",
                    domain="acme.com",
                    published_at="2026-04-23T12:00:00+00:00",
                    why_selected=query,
                )
            )
        return candidates

    async def _fake_fetch(url: str):
        if "acme.com" in url:
            return (
                "<html><body><h1>ML Platform Engineer</h1><p>Acme is building a new machine learning platform team.</p></body></html>",
                "ML Platform Engineer Acme is building a new machine learning platform team.",
            )
        return (
            "<html><body><h1>Platform Engineer</h1><p>Example is growing its data platform team.</p></body></html>",
            "Platform Engineer Example is growing its data platform team.",
        )

    monkeypatch.setattr("backend.services.research_radar.nodes.search.search_public_web", _fake_search)
    monkeypatch.setattr("backend.services.research_radar.nodes.fetch.fetch_document", _fake_fetch)

    profile_resp = await client.post(
        "/api/research/profiles",
        json={
            "name": "Diff Tracker",
            "mode": "research",
            "depth": "quick",
            "selected_roles": ["Platform Engineer"],
            "selected_companies": ["Example"],
            "include_public_web_research": True,
            "max_search_queries": 1,
        },
        headers=AUTH_HEADER,
    )
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()["id"]

    first_run = await client.post(f"/api/research/profiles/{profile_id}/run", headers=AUTH_HEADER)
    assert first_run.status_code == 202
    second_run = await client.post(f"/api/research/profiles/{profile_id}/run", headers=AUTH_HEADER)
    assert second_run.status_code == 202

    reports_resp = await client.get(f"/api/research/reports?profile_id={profile_id}", headers=AUTH_HEADER)
    assert reports_resp.status_code == 200
    reports = reports_resp.json()
    assert len(reports) == 2

    latest_report_id = reports[0]["id"]
    diff_resp = await client.get(f"/api/research/reports/{latest_report_id}/diff", headers=AUTH_HEADER)
    assert diff_resp.status_code == 200
    diff = diff_resp.json()
    assert diff["new_findings"]
    assert "new findings" in diff["diff_summary"]
