import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.models import (
    AiAdminAccessLog,
    AiArtifact,
    AiExperiment,
    AiExperimentAssignment,
    AiModelCall,
    AiModelCard,
    AiPromotionReport,
    AiShadowRun,
)
from backend.services.ai_retention import anonymize_user_ai_records, redact_expired_ai_trace_payloads
from tests.conftest import TEST_USER_ID


def _call(**overrides) -> AiModelCall:
    values = {
        "user_id": TEST_USER_ID,
        "surface": "copilot",
        "task_name": "copilot_answer",
        "model": "gpt-5.4",
        "prompt_version": "copilot_v1",
        "status": "success",
        "request_metadata": {"raw_prompt": "user private prompt"},
        "response_metadata": {"answer": "private response"},
    }
    values.update(overrides)
    return AiModelCall(**values)


@pytest.mark.asyncio
async def test_retention_redacts_old_trace_payloads_but_keeps_ledger_rows(db_session):
    now = datetime(2026, 5, 2, tzinfo=timezone.utc)
    old_call = _call(created_at=now - timedelta(days=45))
    recent_call = _call(created_at=now - timedelta(days=5), prompt_version="copilot_v2")
    db_session.add_all([old_call, recent_call])
    await db_session.commit()

    redacted_count = await redact_expired_ai_trace_payloads(db_session, now=now, retention_days=30)
    await db_session.commit()

    saved_old = await db_session.get(AiModelCall, old_call.id)
    saved_recent = await db_session.get(AiModelCall, recent_call.id)
    assert redacted_count == 1
    assert saved_old is not None
    assert saved_old.request_metadata["retention_redacted"] is True
    assert saved_old.response_metadata["retention_redacted"] is True
    assert saved_recent is not None
    assert saved_recent.request_metadata["raw_prompt"] == "user private prompt"


@pytest.mark.asyncio
async def test_user_deletion_policy_anonymizes_nullable_ai_records_and_deletes_sticky_assignment(db_session):
    experiment = AiExperiment(
        experiment_key="retention_policy",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        control_variant="control",
        candidate_variants=["candidate"],
    )
    db_session.add(experiment)
    await db_session.flush()
    call = _call()
    artifact = AiArtifact(
        user_id=TEST_USER_ID,
        model_call_id=call.id,
        artifact_type="copilot_message",
        artifact_ref_id=uuid.uuid4(),
    )
    shadow = AiShadowRun(
        experiment_id=experiment.id,
        user_id=TEST_USER_ID,
        production_model_call_id=call.id,
        candidate_variant="candidate",
        input_hash="a" * 64,
    )
    assignment = AiExperimentAssignment(
        experiment_id=experiment.id,
        user_id=TEST_USER_ID,
        variant="candidate",
    )
    promotion = AiPromotionReport(
        experiment_id=experiment.id,
        reviewed_by_user_id=TEST_USER_ID,
        status="approved",
        recommendation="promote:candidate",
        report_json={"admin_decision_required": True},
    )
    model_card = AiModelCard(
        task_name="copilot_answer",
        model="gpt-5.4",
        prompt_version="copilot_v1",
        intended_use="Answer user-scoped job pipeline questions.",
        approved_by_user_id=TEST_USER_ID,
    )
    access_log = AiAdminAccessLog(
        admin_user_id=TEST_USER_ID,
        action="view_full_ai_trace",
        target_type="ai_model_call",
        target_id=call.id,
        reason="policy test",
    )
    db_session.add_all([call, artifact, shadow, assignment, promotion, model_card, access_log])
    await db_session.commit()

    counts = await anonymize_user_ai_records(db_session, user_id=TEST_USER_ID)
    await db_session.commit()

    assert counts["ai_model_calls"] == 1
    assert counts["ai_artifacts"] == 1
    assert counts["ai_shadow_runs"] == 1
    assert counts["ai_experiment_assignments"] == 1
    assert (await db_session.get(AiModelCall, call.id)).user_id is None
    assert (await db_session.get(AiArtifact, artifact.id)).user_id is None
    assert (await db_session.get(AiShadowRun, shadow.id)).user_id is None
    assert (await db_session.get(AiPromotionReport, promotion.id)).reviewed_by_user_id is None
    assert (await db_session.get(AiModelCard, model_card.id)).approved_by_user_id is None
    assert (await db_session.get(AiAdminAccessLog, access_log.id)).admin_user_id is None
    remaining_assignments = (await db_session.execute(select(AiExperimentAssignment))).scalars().all()
    assert remaining_assignments == []
