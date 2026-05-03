import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models import (
    AiAdminAccessLog,
    AiArtifact,
    AiExperiment,
    AiModelCall,
    AiModelCard,
    AiPromotionReport,
    AiSafetyDecision,
    AiShadowRun,
    SearchDocument,
    User,
)
from tests.conftest import AUTH_HEADER, TEST_USER_ID, make_auth_header


async def _seed_ai_ops_data(db_session):
    call = AiModelCall(
        user_id=TEST_USER_ID,
        surface="copilot",
        task_name="copilot_answer",
        model="gpt-5.4",
        prompt_version="copilot_v1",
        variant="control",
        status="success",
        validation_result="valid",
        fallback_used=False,
        latency_ms=250,
        prompt_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cost_estimate_cents=3,
        request_metadata={"experiment_key": "copilot_ops", "raw_prompt": "secret prompt"},
        response_metadata={"answer_quality": "grounded", "email_body": "private body"},
    )
    experiment = AiExperiment(
        experiment_key="copilot_ops",
        surface="copilot",
        task_name="copilot_answer",
        status="running",
        control_variant="control",
        candidate_variants=["candidate"],
    )
    model_card = AiModelCard(
        task_name="copilot_answer",
        model="gpt-5.4",
        prompt_version="copilot_v1",
        intended_use="Answer user-scoped pipeline questions.",
        approval_status="draft",
    )
    search_doc = SearchDocument(
        user_id=TEST_USER_ID,
        source_type="application",
        source_id=uuid.uuid4(),
        title="TraceBank Data Scientist",
        search_text="TraceBank Data Scientist",
        content_hash="hash",
        source_updated_at=datetime(2026, 5, 2, 14, 0, tzinfo=timezone.utc),
        indexed_at=datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([call, experiment, model_card, search_doc])
    await db_session.flush()
    artifact = AiArtifact(
        user_id=TEST_USER_ID,
        model_call_id=call.id,
        artifact_type="copilot_message",
        artifact_ref_id=uuid.uuid4(),
        title="Copilot answer",
        path="app://copilot/message",
        metadata_json={"raw_prompt": "secret prompt", "summary": "grounded"},
    )
    shadow = AiShadowRun(
        experiment_id=experiment.id,
        user_id=TEST_USER_ID,
        production_model_call_id=call.id,
        candidate_variant="candidate",
        input_hash="a" * 64,
        status="queued",
        visible_to_user=False,
    )
    promotion = AiPromotionReport(
        experiment_id=experiment.id,
        status="pending_review",
        recommendation="keep_control_collect_more_data",
        report_json={"warnings": ["underpowered"]},
        generated_after_calls=1,
        generated_after_feedback=0,
    )
    db_session.add_all([artifact, shadow, promotion])
    db_session.add(
        AiSafetyDecision(
            user_id=TEST_USER_ID,
            model_call_id=call.id,
            surface="copilot",
            task_name="copilot_answer",
            stage="preflight",
            policy_decision="allow_redacted",
            risk_score=0.72,
            prompt_injection_score=0.36,
            input_data_classes=["career_private", "untrusted_inbound"],
            redaction_counts={"email": 1},
            reasons=["redacted_email"],
            token_estimate=250,
            metadata_json={"raw_prompt": "secret prompt"},
        )
    )
    await db_session.commit()
    return call


@pytest.mark.asyncio
async def test_admin_ai_ops_telemetry_and_lineage_endpoints(client, db_session):
    call = await _seed_ai_ops_data(db_session)

    telemetry = await client.get("/api/admin/ai/telemetry", headers=AUTH_HEADER)
    runs = await client.get("/api/admin/ai/runs", headers=AUTH_HEADER)
    detail = await client.get(f"/api/admin/ai/runs/{call.id}", headers=AUTH_HEADER)
    artifacts = await client.get("/api/admin/ai/artifacts", headers=AUTH_HEADER)
    experiments = await client.get("/api/admin/ai/experiments", headers=AUTH_HEADER)
    model_cards = await client.get("/api/admin/ai/model-cards", headers=AUTH_HEADER)
    promotions = await client.get("/api/admin/ai/promotion-reports", headers=AUTH_HEADER)
    safety = await client.get("/api/admin/ai/safety-decisions", headers=AUTH_HEADER)

    assert telemetry.status_code == 200
    assert telemetry.json()["overview"]["total_calls"] == 1
    assert telemetry.json()["search_freshness"]["stale_document_count"] == 1
    assert telemetry.json()["queue_health"]["queued_shadow_runs"] == 1
    assert telemetry.json()["experiment_guardrails"]["pending_promotion_reports"] == 1
    assert telemetry.json()["safety_guardrails"]["redacted_decisions"] == 1
    assert runs.json()["runs"][0]["id"] == str(call.id)
    assert detail.json()["request_metadata"]["raw_prompt"] == "[redacted]"
    assert detail.json()["response_metadata"]["email_body"] == "[redacted]"
    assert detail.json()["full_trace_requires_reason"] is True
    assert artifacts.json()["artifacts"][0]["metadata"]["raw_prompt"] == "[redacted]"
    assert experiments.json()["experiments"][0]["experiment_key"] == "copilot_ops"
    assert model_cards.json()["model_cards"][0]["task_name"] == "copilot_answer"
    assert promotions.json()["promotion_reports"][0]["status"] == "pending_review"
    assert safety.json()["safety_decisions"][0]["policy_decision"] == "allow_redacted"
    assert safety.json()["safety_decisions"][0]["metadata"]["raw_prompt"] == "[redacted]"


@pytest.mark.asyncio
async def test_admin_ai_safety_decisions_support_operational_filters(client, db_session):
    await _seed_ai_ops_data(db_session)
    db_session.add(
        AiSafetyDecision(
            user_id=TEST_USER_ID,
            surface="research_radar",
            task_name="research_evidence_extractor",
            stage="preflight",
            policy_decision="quarantine",
            risk_score=0.91,
            prompt_injection_score=0.91,
            input_data_classes=["public_research"],
            redaction_counts={"prompt_injection_line": 1},
            reasons=["semantic_prompt_guard"],
            token_estimate=300,
        )
    )
    await db_session.commit()

    response = await client.get(
        "/api/admin/ai/safety-decisions?policy_decision=quarantine&stage=preflight&min_risk=0.8",
        headers=AUTH_HEADER,
    )

    assert response.status_code == 200
    decisions = response.json()["safety_decisions"]
    assert len(decisions) == 1
    assert decisions[0]["surface"] == "research_radar"
    assert decisions[0]["policy_decision"] == "quarantine"


@pytest.mark.asyncio
async def test_admin_can_review_safety_decision(client, db_session):
    await _seed_ai_ops_data(db_session)
    decision = (
        await db_session.execute(
            select(AiSafetyDecision).where(AiSafetyDecision.policy_decision == "allow_redacted")
        )
    ).scalar_one()

    response = await client.patch(
        f"/api/admin/ai/safety-decisions/{decision.id}/review",
        json={
            "review_status": "false_positive",
            "review_notes": "Safe after manual review.",
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["review_status"] == "false_positive"
    assert data["review_notes"] == "Safe after manual review."
    assert data["reviewed_by_user_id"] == str(TEST_USER_ID)


@pytest.mark.asyncio
async def test_full_trace_access_requires_reason_and_writes_log(client, db_session):
    call = await _seed_ai_ops_data(db_session)

    denied = await client.post(
        f"/api/admin/ai/runs/{call.id}/trace-access",
        json={"reason": "short"},
        headers=AUTH_HEADER,
    )
    granted = await client.post(
        f"/api/admin/ai/runs/{call.id}/trace-access",
        json={"reason": "debugging groundedness issue"},
        headers=AUTH_HEADER,
    )

    assert denied.status_code == 422
    assert granted.status_code == 200
    assert granted.json()["request_metadata"]["raw_prompt"] == "secret prompt"
    logs_response = await client.get("/api/admin/ai/trace-access-logs", headers=AUTH_HEADER)
    assert logs_response.status_code == 200
    assert logs_response.json()["access_logs"][0]["action"] == "view_full_ai_trace"
    assert logs_response.json()["access_logs"][0]["reason"] == "debugging groundedness issue"
    log = (await db_session.execute(select(AiAdminAccessLog))).scalar_one()
    assert log.action == "view_full_ai_trace"
    assert log.reason == "debugging groundedness issue"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_ai_ops(client, db_session):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        google_id="ai-ops-normal-user",
        email="ai-ops-normal@apptrail.test",
        name="Normal",
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.get(
        "/api/admin/ai/telemetry",
        headers=make_auth_header(user.id, user.email, user.name),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ai_ops_routes_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("ADMIN_AI_OPS_ENABLED", "false")

    response = await client.get("/api/admin/ai/telemetry", headers=AUTH_HEADER)

    assert response.status_code == 404
