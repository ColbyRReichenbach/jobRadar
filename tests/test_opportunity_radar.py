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
async def test_manual_run_creates_run_and_sources_and_scores(client, db_session):
    await client.post('/api/company-visits', json={"domain": "example.com", "url": "https://example.com/careers"}, headers=AUTH_HEADER)
    await client.post('/api/jobs', json={"company": "Example", "role_title": "Data Engineer", "job_url": "https://example.com/jobs/1"}, headers=AUTH_HEADER)

    profile_resp = await client.post('/api/research/profiles', json={"name": "Run Test", "minimum_score": 10}, headers=AUTH_HEADER)
    profile_id = profile_resp.json()['id']

    run_resp = await client.post(f'/api/research/profiles/{profile_id}/run', headers=AUTH_HEADER)
    assert run_resp.status_code == 201
    assert run_resp.json()['status'] == 'succeeded'

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
