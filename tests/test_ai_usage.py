from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.models import AiModelCall
from backend.services.ai_pricing import ModelPricing, record_model_pricing
from backend.services.ai_usage import TokenUsage, record_model_call, trace_retention_days
from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_record_model_call_persists_usage_cost_and_redacted_metadata(db_session):
    await record_model_pricing(
        db_session,
        ModelPricing("openai", "gpt-4o-mini", input_token_cents_per_1m=10, output_token_cents_per_1m=20),
    )
    call = await record_model_call(
        db_session,
        user_id=TEST_USER_ID,
        surface="email_classifier",
        task_name="email_classifier",
        model="gpt-4o-mini",
        prompt_version="v3",
        status="success",
        latency_ms=123.9,
        retry_count=1,
        token_usage=TokenUsage(
            prompt_tokens=1_000_000,
            cached_input_tokens=100,
            output_tokens=500_000,
        ),
        request_metadata={
            "surface": "email_classifier",
            "api_key": "should-not-persist",
            "nested": {"refresh_token": "secret-refresh"},
        },
    )
    await db_session.commit()

    result = await db_session.execute(select(AiModelCall).where(AiModelCall.id == call.id))
    saved = result.scalar_one()

    assert saved.user_id == TEST_USER_ID
    assert saved.surface == "email_classifier"
    assert saved.status == "success"
    assert saved.latency_ms == 123
    assert saved.retry_count == 1
    assert saved.prompt_tokens == 1_000_000
    assert saved.cached_input_tokens == 100
    assert saved.output_tokens == 500_000
    assert saved.billable_input_tokens == 1_000_000
    assert saved.billable_output_tokens == 500_000
    assert saved.total_tokens == 1_500_000
    assert saved.cost_estimate_cents == 20
    assert saved.cost_breakdown["provider"] == "openai"
    assert saved.request_metadata["api_key"] == "[redacted]"
    assert saved.request_metadata["nested"]["refresh_token"] == "[redacted]"


@pytest.mark.asyncio
async def test_run_json_task_with_metadata_can_persist_success_row(monkeypatch, db_session):
    from backend.services import ai_orchestrator

    async def _fake_create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"classification":"job_update"}'))],
            usage=SimpleNamespace(prompt_tokens=321, completion_tokens=45),
        )

    monkeypatch.setattr(ai_orchestrator, "has_configured_api_key", lambda: True)
    monkeypatch.setattr(ai_orchestrator.client.chat.completions, "create", _fake_create)

    result = await ai_orchestrator.run_json_task_with_metadata(
        "email_classifier",
        "Classify this email.",
        metadata={"surface": "email_classifier", "authorization": "Bearer secret"},
        db_session=db_session,
        user_id=str(TEST_USER_ID),
    )
    await db_session.commit()

    assert result.payload == {"classification": "job_update"}
    saved = (await db_session.execute(select(AiModelCall))).scalar_one()
    assert saved.task_name == "email_classifier"
    assert saved.model == "gpt-4o-mini"
    assert saved.prompt_version == "v3"
    assert saved.status == "success"
    assert saved.prompt_tokens == 321
    assert saved.output_tokens == 45
    assert saved.request_metadata["authorization"] == "[redacted]"


@pytest.mark.asyncio
async def test_run_json_task_with_metadata_can_persist_failure_row(monkeypatch, db_session):
    from backend.services import ai_orchestrator

    async def _fake_create(**kwargs):
        raise ValueError("bad json")

    monkeypatch.setattr(ai_orchestrator, "has_configured_api_key", lambda: True)
    monkeypatch.setattr(ai_orchestrator.client.chat.completions, "create", _fake_create)

    with pytest.raises(RuntimeError):
        await ai_orchestrator.run_json_task_with_metadata(
            "email_classifier",
            "Classify this email.",
            metadata={"surface": "email_classifier"},
            db_session=db_session,
            user_id=str(TEST_USER_ID),
        )
    await db_session.commit()

    saved = (await db_session.execute(select(AiModelCall))).scalar_one()
    assert saved.status == "failure"
    assert saved.error_class == "ValueError"
    assert "bad json" in saved.error_message


def test_trace_retention_days_has_safe_default_and_minimum(monkeypatch):
    monkeypatch.delenv("AI_TRACE_RETENTION_DAYS", raising=False)
    assert trace_retention_days() == 30

    monkeypatch.setenv("AI_TRACE_RETENTION_DAYS", "0")
    assert trace_retention_days() == 1

    monkeypatch.setenv("AI_TRACE_RETENTION_DAYS", "14")
    assert trace_retention_days() == 14
