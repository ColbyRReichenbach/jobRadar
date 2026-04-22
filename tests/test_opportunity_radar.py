import uuid

import pytest
from sqlalchemy import select

from backend.models import (
    OpportunityScore,
    ResearchEvidenceItem,
    ResearchReport,
    ResearchReportSection,
    ResearchRun,
    ResearchRunStep,
    ResearchSourceItem,
)
from backend.services.opportunity_radar.signal_scorer import score_signal
from tests.conftest import AUTH_HEADER, make_auth_header


@pytest.mark.asyncio
async def test_research_profile_crud_user_isolation(client, db_session):
    resp = await client.post('/api/research/profiles', json={"name": "Healthcare Radar"}, headers=AUTH_HEADER)
    assert resp.status_code == 201
    profile = resp.json()

    list_resp = await client.get('/api/research/profiles', headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    assert any(p['id'] == profile['id'] for p in list_resp.json())

    other_header = make_auth_header(uuid.UUID('00000000-0000-0000-0000-000000000002'), email='other@apptrail.test')
    other_list = await client.get('/api/research/profiles', headers=other_header)
    assert other_list.status_code == 200
    assert other_list.json() == []


@pytest.mark.asyncio
async def test_research_profile_extended_fields_round_trip(client):
    create_resp = await client.post(
        '/api/research/profiles',
        json={
            "name": "Research Mode Tracker",
            "objective": "Track product data roles in AI tooling companies.",
            "selected_domains": ["ai_infrastructure"],
            "selected_roles": ["Product Data Scientist"],
            "selected_companies": ["OpenAI"],
            "source_types": ["company_visit"],
            "mode": "hybrid",
            "frequency": "biweekly",
            "depth": "deep",
            "notification_mode": "email_digest",
            "minimum_score": 82,
            "target_locations": ["New York", "Remote"],
            "remote_types": ["remote", "hybrid"],
            "seniority_levels": ["senior", "staff"],
            "research_source_scopes": ["company_news", "job_boards"],
            "use_profile_context": True,
            "include_public_web_research": True,
            "report_prompt_notes": "Bias toward platform teams and strong experimentation culture.",
            "max_search_queries": 12,
            "max_sources_per_run": 24,
        },
        headers=AUTH_HEADER,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["mode"] == "hybrid"
    assert created["frequency"] == "biweekly"
    assert created["depth"] == "deep"
    assert created["target_locations"] == ["New York", "Remote"]
    assert created["remote_types"] == ["remote", "hybrid"]
    assert created["seniority_levels"] == ["senior", "staff"]
    assert created["research_source_scopes"] == ["company_news", "job_boards"]
    assert created["include_public_web_research"] is True
    assert created["max_search_queries"] == 12
    assert created["max_sources_per_run"] == 24
    assert created["next_run_at"] is None
    assert created["last_successful_run_at"] is None
    assert created["updated_at"] is not None

    patch_resp = await client.patch(
        f"/api/research/profiles/{created['id']}",
        json={
            "mode": "research",
            "depth": "standard",
            "use_profile_context": False,
            "include_public_web_research": False,
            "report_prompt_notes": "Tighten around companies with recent hiring signals.",
            "max_search_queries": 6,
        },
        headers=AUTH_HEADER,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["mode"] == "research"
    assert updated["depth"] == "standard"
    assert updated["use_profile_context"] is False
    assert updated["include_public_web_research"] is False
    assert updated["report_prompt_notes"] == "Tighten around companies with recent hiring signals."
    assert updated["max_search_queries"] == 6
    assert updated["max_sources_per_run"] == 24


@pytest.mark.asyncio
async def test_manual_run_creates_run_and_sources_and_scores(client, db_session):
    await client.post('/api/company-visits', json={"domain": "example.com", "url": "https://example.com/careers"}, headers=AUTH_HEADER)
    await client.post('/api/jobs', json={"company": "Example", "role_title": "Data Engineer", "job_url": "https://example.com/jobs/1"}, headers=AUTH_HEADER)

    profile_resp = await client.post('/api/research/profiles', json={"name": "Run Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']

    run_resp = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert run_resp.status_code == 202
    run_payload = run_resp.json()
    assert run_payload['status'] == 'queued'
    assert run_payload['run_type'] == 'manual'
    assert run_payload['mode'] == 'internal'
    assert run_payload['trigger_reason'] == 'manual_run'
    assert run_payload['status_detail'] == {}
    assert run_payload['report_id'] is None

    run_detail = await client.get(f"/api/research/runs/{run_payload['id']}", headers=AUTH_HEADER)
    assert run_detail.status_code == 200
    assert run_detail.json()['status'] == 'succeeded'

    runs = (await db_session.execute(select(ResearchRun))).scalars().all()
    assert len(runs) >= 1
    sources = (await db_session.execute(select(ResearchSourceItem))).scalars().all()
    assert len(sources) >= 1
    scores = (await db_session.execute(select(OpportunityScore))).scalars().all()
    assert len(scores) >= 1


@pytest.mark.asyncio
async def test_rule_extractor_and_signal_listing(client, db_session):
    from backend.models import CompanyVisit
    from tests.conftest import TEST_USER_ID

    db_session.add(CompanyVisit(user_id=TEST_USER_ID, domain='repeat.com', url='https://repeat.com/careers', visit_count=3))
    await db_session.commit()

    profile_resp = await client.post('/api/research/profiles', json={"name": "Extractor Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']
    await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)

    signals_resp = await client.get('/api/research/signals', headers=AUTH_HEADER)
    assert signals_resp.status_code == 200
    event_types = {s['event_type'] for s in signals_resp.json()}
    assert 'company_visit_interest' in event_types


@pytest.mark.asyncio
async def test_scoring_stable_components():
    class Sig:
        event_type = 'new_role'
        roles = ['Data Engineer']
        domains = ['healthcare_ai']
        company_id = None
        occurred_at = None
        confidence = 0.8

    class Profile:
        selected_roles = ['Data Engineer']
        selected_domains = ['healthcare_ai']

    score = score_signal(Sig(), profile=Profile())
    assert set(score.keys()) == {
        'total_score', 'role_fit', 'domain_fit', 'company_interest', 'recency',
        'public_data_buildability', 'outreach_path_strength', 'portfolio_gap_relevance',
        'source_confidence', 'explanation'
    }
    assert 0 <= score['total_score'] <= 100


@pytest.mark.asyncio
async def test_actions_accept_and_dismiss(client):
    await client.post('/api/jobs', json={"company": "ActionCo", "role_title": "MLE", "job_url": "https://actionco.com/jobs/1"}, headers=AUTH_HEADER)
    profile_resp = await client.post('/api/research/profiles', json={"name": "Action Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']
    await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)

    actions_resp = await client.get('/api/research/actions', headers=AUTH_HEADER)
    assert actions_resp.status_code == 200
    action = actions_resp.json()[0]

    accepted = await client.post(f"/api/research/actions/{action['id']}/accept", headers=AUTH_HEADER)
    assert accepted.status_code == 200
    assert accepted.json()['status'] == 'accepted'

    invalid = await client.patch(f"/api/research/actions/{action['id']}", json={'status': 'invalid_status'}, headers=AUTH_HEADER)
    assert invalid.status_code == 422

    completed = await client.patch(f"/api/research/actions/{action['id']}", json={'status': 'completed'}, headers=AUTH_HEADER)
    assert completed.status_code == 200
    invalid_transition = await client.patch(f"/api/research/actions/{action['id']}", json={'status': 'dismissed'}, headers=AUTH_HEADER)
    assert invalid_transition.status_code == 400


@pytest.mark.asyncio
async def test_briefs_and_actions_include_signal_linkage(client):
    await client.post('/api/jobs', json={"company": "LinkageCo", "role_title": "Platform Engineer", "job_url": "https://linkageco.com/jobs/1"}, headers=AUTH_HEADER)
    profile_resp = await client.post('/api/research/profiles', json={"name": "Linkage Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']
    await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)

    signals_resp = await client.get('/api/research/signals', headers=AUTH_HEADER)
    briefs_resp = await client.get('/api/research/briefs', headers=AUTH_HEADER)
    actions_resp = await client.get('/api/research/actions', headers=AUTH_HEADER)

    assert signals_resp.status_code == 200
    assert briefs_resp.status_code == 200
    assert actions_resp.status_code == 200

    signal_ids = {signal['id'] for signal in signals_resp.json()}
    assert briefs_resp.json()
    assert actions_resp.json()
    assert briefs_resp.json()[0]['signal_id'] in signal_ids
    assert actions_resp.json()[0]['signal_id'] in signal_ids
    assert actions_resp.json()[0]['profile_id'] == profile_id


@pytest.mark.asyncio
async def test_signal_evidence_includes_source_context(client):
    await client.post(
        '/api/jobs',
        json={"company": "EvidenceCo", "role_title": "Backend Engineer", "job_url": "https://evidenceco.com/jobs/1"},
        headers=AUTH_HEADER,
    )
    profile_resp = await client.post('/api/research/profiles', json={"name": "Evidence Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']
    await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)

    signals_resp = await client.get('/api/research/signals', headers=AUTH_HEADER)
    assert signals_resp.status_code == 200
    signal = next(signal for signal in signals_resp.json() if signal['event_type'] == 'new_role')

    assert signal['evidence']
    evidence = signal['evidence'][0]
    assert evidence['source_type'] == 'application'
    assert evidence['source_name'] == 'internal_application'
    assert 'EvidenceCo' in (evidence['title'] or '')
    assert evidence['excerpt']


@pytest.mark.asyncio
async def test_feedback_stats_endpoint_aggregates_recent_feedback(client):
    await client.post(
        '/api/jobs',
        json={"company": "FeedbackCo", "role_title": "ML Engineer", "job_url": "https://feedbackco.com/jobs/1"},
        headers=AUTH_HEADER,
    )
    profile_resp = await client.post('/api/research/profiles', json={"name": "Feedback Stats", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']
    await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)

    signals_resp = await client.get('/api/research/signals', headers=AUTH_HEADER)
    briefs_resp = await client.get('/api/research/briefs', headers=AUTH_HEADER)
    actions_resp = await client.get('/api/research/actions', headers=AUTH_HEADER)
    signal = signals_resp.json()[0]
    brief = briefs_resp.json()[0]
    action = actions_resp.json()[0]

    useful_resp = await client.post(
        '/api/research/feedback',
        json={
            'signal_id': signal['id'],
            'brief_id': brief['id'],
            'action_id': action['id'],
            'rating': 'useful',
            'notes': 'Brief lined up with the signal and next step.',
        },
        headers=AUTH_HEADER,
    )
    assert useful_resp.status_code == 201

    not_useful_resp = await client.post(
        '/api/research/feedback',
        json={
            'signal_id': signal['id'],
            'rating': 'not_useful',
        },
        headers=AUTH_HEADER,
    )
    assert not_useful_resp.status_code == 201
    useful_payload = useful_resp.json()
    assert useful_payload['feedback_scope'] == 'signal'
    assert useful_payload['signal_id'] == signal['id']
    assert useful_payload['brief_id'] == brief['id']
    assert useful_payload['action_id'] == action['id']

    stats_resp = await client.get('/api/research/feedback/stats', headers=AUTH_HEADER)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats['total_feedback'] == 2
    assert stats['useful'] == 1
    assert stats['not_useful'] == 1
    assert stats['usefulness_rate'] == 50.0
    assert stats['notes_count'] == 1
    assert len(stats['recent_feedback']) == 2
    assert stats['recent_feedback'][0]['rating'] == 'not_useful'
    assert stats['recent_feedback'][1]['brief_id'] == brief['id']
    assert stats['recent_feedback'][1]['action_id'] == action['id']
    assert stats['recent_feedback'][1]['signal_id'] == signal['id']


@pytest.mark.asyncio
async def test_run_does_not_duplicate_same_signal_for_same_source(client):
    await client.post('/api/jobs', json={"company": "NoDup", "role_title": "Data Engineer", "job_url": "https://nodup.com/jobs/1"}, headers=AUTH_HEADER)
    profile_resp = await client.post('/api/research/profiles', json={"name": "Dedup Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']

    first_run = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert first_run.status_code == 202
    second_run = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert second_run.status_code == 202

    signals_resp = await client.get('/api/research/signals', headers=AUTH_HEADER)
    assert signals_resp.status_code == 200
    new_role_signals = [s for s in signals_resp.json() if s['event_type'] == 'new_role' and 'NoDup' in s['title']]
    assert len(new_role_signals) == 1


@pytest.mark.asyncio
async def test_run_marks_failed_when_source_collection_raises(client, monkeypatch):
    profile_resp = await client.post('/api/research/profiles', json={"name": "Failure Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']

    async def _boom(*args, **kwargs):
        raise RuntimeError("collection failed")

    monkeypatch.setattr("backend.tasks.run_research_radar.collect_internal_sources", _boom)
    run_resp = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert run_resp.status_code == 202

    runs_resp = await client.get('/api/research/runs', headers=AUTH_HEADER)
    assert runs_resp.status_code == 200
    failed_runs = [r for r in runs_resp.json() if r['profile_id'] == profile_id and r['status'] == 'failed']
    assert failed_runs


@pytest.mark.asyncio
async def test_profile_source_types_limit_collection(client):
    await client.post('/api/jobs', json={"company": "SourceFilter", "role_title": "Data Engineer", "job_url": "https://sourcefilter.com/jobs/1"}, headers=AUTH_HEADER)
    await client.post('/api/company-visits', json={"domain": "sourcefilter.com", "url": "https://sourcefilter.com/careers"}, headers=AUTH_HEADER)

    profile_resp = await client.post(
        '/api/research/profiles',
        json={"name": "SourceType Test", "source_types": ["company_visit"], "minimum_score": 10},
        headers=AUTH_HEADER,
    )
    profile_id = profile_resp.json()['id']
    run_resp = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert run_resp.status_code == 202

    signals_resp = await client.get('/api/research/signals', headers=AUTH_HEADER)
    assert signals_resp.status_code == 200
    assert all(signal['event_type'] != 'new_role' for signal in signals_resp.json())


@pytest.mark.asyncio
async def test_run_trace_endpoints_return_steps(client):
    await client.post(
        '/api/jobs',
        json={"company": "TraceCo", "role_title": "Platform Engineer", "job_url": "https://traceco.com/jobs/1"},
        headers=AUTH_HEADER,
    )
    profile_resp = await client.post('/api/research/profiles', json={"name": "Trace Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']

    run_resp = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert run_resp.status_code == 202
    run_id = run_resp.json()['id']

    steps_resp = await client.get(f'/api/research/runs/{run_id}/steps', headers=AUTH_HEADER)
    assert steps_resp.status_code == 200
    steps = steps_resp.json()
    assert len(steps) >= 2
    assert steps[0]['step_name'] == 'collect_internal_sources'
    assert steps[0]['status'] == 'succeeded'
    assert steps[1]['step_name'] == 'process_internal_signals'
    assert steps[1]['status'] == 'succeeded'

    trace_resp = await client.get(f'/api/research/runs/{run_id}/trace', headers=AUTH_HEADER)
    assert trace_resp.status_code == 200
    trace = trace_resp.json()
    assert trace['run']['id'] == run_id
    assert trace['run']['status'] == 'succeeded'
    assert trace['step_count'] == len(steps)
    assert trace['steps'][0]['step_name'] == 'collect_internal_sources'


@pytest.mark.asyncio
async def test_report_endpoints_return_saved_report_and_accept_feedback(client, db_session):
    profile_resp = await client.post('/api/research/profiles', json={"name": "Report Surface"}, headers=AUTH_HEADER)
    assert profile_resp.status_code == 201
    profile_id = profile_resp.json()['id']

    run = ResearchRun(user_id=uuid.UUID('00000000-0000-0000-0000-000000000001'), profile_id=uuid.UUID(profile_id), status="succeeded")
    db_session.add(run)
    await db_session.flush()

    report = ResearchReport(
        user_id=uuid.UUID('00000000-0000-0000-0000-000000000001'),
        profile_id=uuid.UUID(profile_id),
        run_id=run.id,
        title="Weekly AI Infra Scan",
        summary_markdown="Three strong companies showed new platform-data hiring signals.",
        diff_summary="Two companies are new since the previous run.",
        status="published",
        finding_count=3,
        source_count=6,
        new_findings_count=2,
        changed_findings_count=1,
    )
    db_session.add(report)
    await db_session.flush()

    db_session.add(
        ResearchReportSection(
            report_id=report.id,
            section_key="executive_summary",
            title="Executive Summary",
            display_order=1,
            markdown="Hiring activity accelerated across the shortlist.",
        )
    )
    db_session.add(
        ResearchEvidenceItem(
            user_id=uuid.UUID('00000000-0000-0000-0000-000000000001'),
            profile_id=uuid.UUID(profile_id),
            run_id=run.id,
            report_id=report.id,
            evidence_type="company_update",
            title="TraceCo launched a new data platform opening",
            claim="TraceCo is expanding its platform-data team.",
            snippet="New staff platform engineer role posted this week.",
            url="https://traceco.com/jobs/1",
            domain="traceco.com",
            company_name="TraceCo",
            role_title="Platform Engineer",
        )
    )
    await db_session.commit()

    list_resp = await client.get('/api/research/reports', headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    reports = list_resp.json()
    assert any(item['id'] == str(report.id) for item in reports)

    detail_resp = await client.get(f'/api/research/reports/{report.id}', headers=AUTH_HEADER)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail['title'] == "Weekly AI Infra Scan"
    assert detail['sections'][0]['section_key'] == 'executive_summary'
    assert detail['evidence'][0]['company_name'] == 'TraceCo'

    diff_resp = await client.get(f'/api/research/reports/{report.id}/diff', headers=AUTH_HEADER)
    assert diff_resp.status_code == 200
    assert diff_resp.json()['diff_summary'] == "Two companies are new since the previous run."

    feedback_resp = await client.post(
        f'/api/research/reports/{report.id}/feedback',
        json={'rating': 'useful', 'notes': 'This is the right level of detail.'},
        headers=AUTH_HEADER,
    )
    assert feedback_resp.status_code == 201
    feedback = feedback_resp.json()
    assert feedback['report_id'] == str(report.id)
    assert feedback['feedback_scope'] == 'report'
