import uuid

import pytest

from backend.models import AiModelCall, CopilotConversation, CopilotFeedback, CopilotMessage
from backend.services.experiments import (
    assign_variant,
    auto_pause_if_guardrail_breached,
    create_or_update_experiment,
    queue_shadow_run,
    record_feedback_reward_event,
)
from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_sticky_assignment_respects_experiment_flag(db_session, monkeypatch):
    disabled = await create_or_update_experiment(
        db_session,
        experiment_key="copilot_disabled_assignment",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        candidate_variants=["candidate"],
        traffic_allocation={"candidate": 1.0},
    )
    monkeypatch.setenv("COPILOT_EXPERIMENTS_ENABLED", "false")
    disabled_assignment = await assign_variant(db_session, experiment=disabled, user_id=TEST_USER_ID)
    assert disabled_assignment.variant == "control"

    enabled = await create_or_update_experiment(
        db_session,
        experiment_key="copilot_enabled_assignment",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        candidate_variants=["candidate"],
        traffic_allocation={"candidate": 1.0},
    )
    monkeypatch.setenv("COPILOT_EXPERIMENTS_ENABLED", "true")
    first = await assign_variant(db_session, experiment=enabled, user_id=TEST_USER_ID)
    second = await assign_variant(db_session, experiment=enabled, user_id=TEST_USER_ID)
    assert first.id == second.id
    assert first.variant == "candidate"


@pytest.mark.asyncio
async def test_shadow_run_is_never_visible_to_user(db_session):
    experiment = await create_or_update_experiment(
        db_session,
        experiment_key="copilot_shadow",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        candidate_variants=["candidate"],
    )
    shadow = await queue_shadow_run(
        db_session,
        experiment=experiment,
        user_id=TEST_USER_ID,
        production_model_call_id=None,
        candidate_variant="candidate",
        input_payload="What roles need follow-up?",
    )
    assert shadow.visible_to_user is False
    assert shadow.status == "queued"
    assert len(shadow.input_hash) == 64


@pytest.mark.asyncio
async def test_feedback_creates_reward_event_linked_to_variant(db_session):
    model_call = AiModelCall(
        user_id=TEST_USER_ID,
        surface="copilot",
        task_name="copilot_answer",
        model="gpt-5.4",
        prompt_version="copilot_v1",
        variant="candidate",
        status="success",
        request_metadata={"experiment_key": "copilot_model_cost_v1"},
    )
    conversation = CopilotConversation(user_id=TEST_USER_ID, title="Feedback")
    db_session.add_all([model_call, conversation])
    await db_session.flush()
    message = CopilotMessage(
        conversation_id=conversation.id,
        user_id=TEST_USER_ID,
        role="assistant",
        content="Grounded answer",
        model_call_id=model_call.id,
    )
    db_session.add(message)
    await db_session.flush()
    feedback = CopilotFeedback(user_id=TEST_USER_ID, message_id=message.id, rating="thumbs_down")
    db_session.add(feedback)
    await db_session.flush()

    reward = await record_feedback_reward_event(db_session, feedback=feedback)

    assert reward.reward_score == -1.0
    assert reward.variant == "candidate"
    assert reward.experiment_key == "copilot_model_cost_v1"
    assert reward.model_call_id == model_call.id


@pytest.mark.asyncio
async def test_guardrail_breach_auto_pauses_experiment(db_session):
    experiment = await create_or_update_experiment(
        db_session,
        experiment_key="copilot_guardrail",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        guardrail_thresholds={"max_critical_failure_rate": 0.0},
    )

    paused = await auto_pause_if_guardrail_breached(
        db_session,
        experiment=experiment,
        guardrail_metrics={"critical_failure_rate": 0.01},
    )

    assert paused is True
    assert experiment.status == "paused"
    assert experiment.metadata_json["auto_pause_reason"] == "critical_guardrail_breach"
