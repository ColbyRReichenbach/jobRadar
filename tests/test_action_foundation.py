import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models import ActionCandidate, Application, Contact, Interview, RecommendedAction, ResearchProfile, ResearchRun
from backend.services.action_candidates import ActionCandidateSpec, create_or_update_action_candidate
from backend.services.dedupe_gate import evaluate_action_dedupe
from backend.services.research_radar.nodes.persist import persist_report_node
from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_action_candidate_creation_is_deterministic_for_same_source_action_entity(db_session):
    decision = await evaluate_action_dedupe(
        db_session,
        user_id=TEST_USER_ID,
        action_type="add_job_to_pipeline",
        payload={"company": "Acme", "role_title": "Backend Engineer", "job_url": "https://jobs.example.com/acme/1"},
    )

    spec = ActionCandidateSpec(
        user_id=TEST_USER_ID,
        source_type="email_event",
        source_id="email-1",
        action_type="add_job_to_pipeline",
        target_entity_type=decision.target_entity_type,
        target_fingerprint=decision.target_fingerprint,
        dedupe_key=decision.dedupe_key,
        duplicate_type=decision.duplicate_type,
        duplicate_matches_json=decision.matches,
        policy_decision=decision.policy_decision,
        confidence=0.82,
        evidence_json={"source": "unit_test"},
    )
    first = await create_or_update_action_candidate(db_session, spec)
    second = await create_or_update_action_candidate(db_session, spec)

    assert second.id == first.id
    assert first.dedupe_key == decision.dedupe_key
    assert first.status == "proposed"


@pytest.mark.asyncio
async def test_action_candidate_upsert_preserves_terminal_status(db_session):
    decision = await evaluate_action_dedupe(
        db_session,
        user_id=TEST_USER_ID,
        action_type="add_job_to_pipeline",
        payload={"company": "Acme", "role_title": "Backend Engineer"},
    )
    spec = ActionCandidateSpec(
        user_id=TEST_USER_ID,
        source_type="email_event",
        source_id="email-terminal",
        action_type="add_job_to_pipeline",
        target_entity_type=decision.target_entity_type,
        target_fingerprint=decision.target_fingerprint,
        dedupe_key=decision.dedupe_key,
        duplicate_type="none",
        confidence=0.8,
        evidence_json={"version": 1},
    )
    candidate = await create_or_update_action_candidate(db_session, spec)
    candidate.status = "accepted"
    candidate.policy_decision = "link_existing"
    candidate.requires_confirmation = False
    candidate.evidence_json = {"accepted": True}
    await db_session.flush()

    reprocessed = await create_or_update_action_candidate(
        db_session,
        ActionCandidateSpec(
            user_id=TEST_USER_ID,
            source_type="email_event",
            source_id="email-terminal",
            action_type="add_job_to_pipeline",
            target_entity_type=decision.target_entity_type,
            target_fingerprint=decision.target_fingerprint,
            dedupe_key=decision.dedupe_key,
            duplicate_type="hard",
            policy_decision="suppress_duplicate",
            confidence=0.2,
            requires_confirmation=True,
            evidence_json={"version": 2},
        ),
    )

    assert reprocessed.id == candidate.id
    assert reprocessed.status == "accepted"
    assert reprocessed.policy_decision == "link_existing"
    assert reprocessed.requires_confirmation is False
    assert reprocessed.evidence_json == {"accepted": True}
    assert reprocessed.duplicate_type == "hard"
    assert reprocessed.confidence == 0.2


@pytest.mark.asyncio
async def test_dedupe_gate_detects_hard_soft_and_none_cases(db_session):
    app = Application(
        user_id=TEST_USER_ID,
        company="Acme",
        role_title="Backend Engineer",
        location="Remote",
        job_url="https://jobs.example.com/acme/backend",
    )
    contact = Contact(user_id=TEST_USER_ID, name="Taylor Smith", email="taylor@example.com")
    interview = Interview(
        user_id=TEST_USER_ID,
        interview_type="phone",
        scheduled_at=datetime(2026, 5, 12, 14, 0, tzinfo=timezone.utc),
        interviewer_email="recruiter@example.com",
    )
    db_session.add_all([app, contact, interview])
    await db_session.commit()

    hard_job = await evaluate_action_dedupe(
        db_session,
        user_id=TEST_USER_ID,
        action_type="add_job_to_pipeline",
        payload={
            "company": "Acme",
            "role_title": "Backend Engineer",
            "job_url": "https://jobs.example.com/acme/backend?utm_source=email",
        },
    )
    soft_contact = await evaluate_action_dedupe(
        db_session,
        user_id=TEST_USER_ID,
        action_type="add_network_contact",
        payload={"name": "Taylor Smith", "email": "taylor.other@example.com"},
    )
    hard_interview = await evaluate_action_dedupe(
        db_session,
        user_id=TEST_USER_ID,
        action_type="schedule_interview",
        payload={
            "scheduled_at": "2026-05-12T14:00:00+00:00",
            "interviewer_email": "recruiter@example.com",
        },
    )
    no_radar = await evaluate_action_dedupe(
        db_session,
        user_id=TEST_USER_ID,
        action_type="review_radar_opportunity",
        payload={"profile_id": uuid.uuid4(), "title": "Review Acme opening", "source_url": "https://example.com/jobs/1"},
    )

    assert hard_job.duplicate_type == "hard"
    assert hard_job.reason == "job_url_already_tracked"
    assert hard_job.matches[0]["entity_type"] == "application"
    assert soft_contact.duplicate_type == "soft"
    assert soft_contact.reason == "same_contact_name"
    assert hard_interview.duplicate_type == "hard"
    assert hard_interview.reason == "same_time_and_interviewer"
    assert no_radar.duplicate_type == "none"


@pytest.mark.asyncio
async def test_radar_recommended_actions_get_candidate_and_suppress_exact_duplicate(monkeypatch, db_session):
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("backend.services.research_radar.nodes.persist.index_record", _noop)
    monkeypatch.setattr("backend.services.research_radar.nodes.persist.record_radar_report_artifact", _noop)

    profile = ResearchProfile(user_id=TEST_USER_ID, name="Radar Foundation")
    db_session.add(profile)
    await db_session.flush()

    async def _persist_with_new_run():
        run = ResearchRun(user_id=TEST_USER_ID, profile_id=profile.id, status="running")
        db_session.add(run)
        await db_session.flush()
        return await persist_report_node(
            {
                "db": db_session,
                "user_id": TEST_USER_ID,
                "profile_id": profile.id,
                "run_id": run.id,
                "tracker": {"name": profile.name},
                "final_report": {
                    "title": "Radar report",
                    "summary_markdown": "Summary",
                    "structured_json": {},
                    "status": "published",
                    "overall_confidence": 0.71,
                    "finding_count": 1,
                    "source_count": 1,
                },
                "diff_summary": {},
                "report_sections": [],
                "evidence_items": [],
                "report_actions": [
                    {
                        "action_type": "review_opportunity",
                        "title": "Review Acme opening",
                        "body": "Review the role.",
                        "payload": {"source_url": "https://example.com/jobs/1"},
                        "priority": 40,
                    }
                ],
            }
        )

    await _persist_with_new_run()
    await _persist_with_new_run()
    await db_session.commit()

    actions = list((await db_session.execute(select(RecommendedAction))).scalars().all())
    candidates = list((await db_session.execute(select(ActionCandidate).order_by(ActionCandidate.created_at))).scalars().all())

    assert len(actions) == 1
    assert actions[0].dedupe_key
    assert actions[0].action_candidate_id == candidates[0].id
    assert candidates[0].status == "proposed"
    assert candidates[1].status == "suppressed_duplicate"
    assert candidates[1].duplicate_matches_json[0]["id"] == str(actions[0].id)
