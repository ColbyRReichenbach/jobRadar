import uuid

import pytest
from sqlalchemy import select

from backend.models import OpportunityScore, ResearchRun, ResearchSourceItem
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
    assert run_resp.status_code == 201
    run_payload = run_resp.json()
    assert run_payload['status'] == 'succeeded'
    assert run_payload['run_type'] == 'manual'
    assert run_payload['mode'] == 'internal'
    assert run_payload['trigger_reason'] == 'manual_run'
    assert run_payload['status_detail'] == {}
    assert run_payload['report_id'] is None

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
    assert first_run.status_code == 201
    second_run = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert second_run.status_code == 201

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

    monkeypatch.setattr("backend.main.collect_internal_sources", _boom)
    with pytest.raises(Exception):
        await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)

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
    assert run_resp.status_code == 201

    signals_resp = await client.get('/api/research/signals', headers=AUTH_HEADER)
    assert signals_resp.status_code == 200
    assert all(signal['event_type'] != 'new_role' for signal in signals_resp.json())
