import uuid

import pytest
from sqlalchemy import select

from backend.models import AiArtifact
from backend.services.ai_artifacts import record_ai_artifact
from backend.services.ai_usage import TokenUsage, record_model_call
from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_record_ai_artifact_links_generated_output_to_model_call(db_session):
    call = await record_model_call(
        db_session,
        user_id=TEST_USER_ID,
        surface="radar",
        task_name="research_report_writer",
        model="gpt-5.4",
        prompt_version="v1",
        status="success",
        token_usage=TokenUsage(prompt_tokens=2_000, output_tokens=1_000),
    )
    report_id = uuid.uuid4()

    artifact = await record_ai_artifact(
        db_session,
        user_id=TEST_USER_ID,
        model_call_id=call.id,
        artifact_type="research_report",
        artifact_ref_id=report_id,
        title="AI Hiring Report",
        path="docs/interview-artifacts/generated/2026-05-02/report.md",
        metadata={"refresh_token": "secret", "dataset_version": "radar-v1"},
    )
    await db_session.commit()

    saved = (await db_session.execute(select(AiArtifact).where(AiArtifact.id == artifact.id))).scalar_one()
    assert saved.user_id == TEST_USER_ID
    assert saved.model_call_id == call.id
    assert saved.artifact_type == "research_report"
    assert saved.artifact_ref_id == report_id
    assert saved.metadata_json["refresh_token"] == "[redacted]"
    assert saved.metadata_json["dataset_version"] == "radar-v1"
