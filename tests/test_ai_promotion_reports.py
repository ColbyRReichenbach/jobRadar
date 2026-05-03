import uuid

import pytest

from backend.models import AiFeedbackRewardEvent, AiModelCall, User
from backend.services.experiments import create_or_update_experiment
from backend.services.promotion_reports import generate_promotion_report
from tests.conftest import AUTH_HEADER, TEST_USER_ID, make_auth_header


async def _seed_call(db_session, *, variant: str, cost: int, latency: int):
    call = AiModelCall(
        user_id=TEST_USER_ID,
        surface="copilot",
        task_name="copilot_answer",
        model="gpt-5.4",
        prompt_version="copilot_v1",
        variant=variant,
        status="success",
        cost_estimate_cents=cost,
        latency_ms=latency,
        request_metadata={"experiment_key": "copilot_promotion", "query_type": "pipeline_summary"},
    )
    db_session.add(call)
    await db_session.flush()
    return call


async def _seed_reward(db_session, *, variant: str, score: float):
    reward = AiFeedbackRewardEvent(
        feedback_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        user_id=TEST_USER_ID,
        experiment_key="copilot_promotion",
        variant=variant,
        rating="thumbs_up" if score > 0 else "thumbs_down",
        reward_score=score,
    )
    db_session.add(reward)
    await db_session.flush()
    return reward


@pytest.mark.asyncio
async def test_promotion_report_requires_admin_review_and_projects_scale(db_session):
    experiment = await create_or_update_experiment(
        db_session,
        experiment_key="copilot_promotion",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        candidate_variants=["candidate"],
    )
    for _ in range(2):
        await _seed_call(db_session, variant="control", cost=2, latency=200)
        await _seed_call(db_session, variant="candidate", cost=2, latency=180)
    await _seed_reward(db_session, variant="control", score=1)
    await _seed_reward(db_session, variant="control", score=-1)
    await _seed_reward(db_session, variant="candidate", score=1)
    await _seed_reward(db_session, variant="candidate", score=1)

    report = await generate_promotion_report(db_session, experiment=experiment, min_calls=2, min_feedback=2)

    assert report.status == "pending_review"
    assert report.recommendation == "promote:candidate"
    assert report.report_json["admin_decision_required"] is True
    assert report.report_json["variant_summaries"][1]["avg_reward"] == 1.0
    assert report.report_json["variant_summaries"][1]["guardrail_failure_rate"] == 0.0
    assert report.report_json["task_query_mix"]["candidate"]["pipeline_summary"] == 2
    assert "1000000" not in report.report_json
    assert report.report_json["scale_projections"]["candidate"][2]["users"] == 1_000_000


@pytest.mark.asyncio
async def test_admin_can_approve_promotion_report(client, db_session):
    experiment = await create_or_update_experiment(
        db_session,
        experiment_key="copilot_promotion_route",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        candidate_variants=["candidate"],
    )
    report = await generate_promotion_report(db_session, experiment=experiment, min_calls=0, min_feedback=0)
    report.recommendation = "promote:candidate"
    await db_session.commit()

    response = await client.post(f"/api/admin/ai/promotion-reports/{report.id}/approve", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    await db_session.refresh(experiment)
    assert experiment.control_variant == "candidate"
    assert experiment.status == "completed"


@pytest.mark.asyncio
async def test_non_admin_cannot_approve_promotion_report(client, db_session):
    user = User(
        id=uuid.uuid4(),
        google_id="non-admin-ai-promotion",
        email="non-admin-ai-promotion@apptrail.test",
        name="Normal User",
        is_admin=False,
    )
    db_session.add(user)
    experiment = await create_or_update_experiment(
        db_session,
        experiment_key="copilot_promotion_denied",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        candidate_variants=["candidate"],
    )
    report = await generate_promotion_report(db_session, experiment=experiment, min_calls=0, min_feedback=0)
    await db_session.commit()

    response = await client.post(
        f"/api/admin/ai/promotion-reports/{report.id}/approve",
        headers=make_auth_header(user.id, user.email, user.name),
    )

    assert response.status_code == 403
