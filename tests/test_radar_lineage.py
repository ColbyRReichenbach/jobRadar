import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.models import ResearchEvidenceItem, ResearchProfile, ResearchReport, ResearchRun, ResearchRunStep, ResearchSourceItem, User
from backend.services.ai_usage import TokenUsage, record_model_call
from backend.services.research_radar.lineage import (
    RadarLineageNotFoundError,
    collect_radar_lineage,
    record_radar_report_artifact,
    write_radar_lineage_report_bundle,
)
from tests.conftest import TEST_USER_ID


async def _seed_radar_report(db_session):
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    profile = ResearchProfile(
        user_id=TEST_USER_ID,
        name="AI Banking Roles",
        mode="research",
        frequency="weekly",
        selected_domains=["banking", "AI assistants"],
        selected_roles=["Data Scientist", "ML Engineer"],
        selected_companies=["Bank of America"],
        keywords=["Erica", "NLP"],
    )
    db_session.add(profile)
    await db_session.flush()

    run = ResearchRun(
        user_id=TEST_USER_ID,
        profile_id=profile.id,
        status="succeeded",
        mode="research",
        run_type="manual",
        started_at=now - timedelta(minutes=5),
        completed_at=now - timedelta(minutes=1),
        tokens_in=2_000,
        tokens_out=800,
        llm_call_count=1,
        cost_estimate_cents=18,
    )
    db_session.add(run)
    await db_session.flush()

    report = ResearchReport(
        user_id=TEST_USER_ID,
        profile_id=profile.id,
        run_id=run.id,
        report_date=now,
        title="Banking AI Assistant Hiring Radar",
        summary_markdown="Banking teams are investing in assistant search and NLP.",
        structured_json={"verification": {"unsupported_claim_count": 0, "claim_count": 2}},
        status="published",
        finding_count=2,
        source_count=2,
        overall_confidence=0.86,
    )
    db_session.add(report)
    await db_session.flush()
    run.report_id = report.id

    source = ResearchSourceItem(
        user_id=TEST_USER_ID,
        profile_id=profile.id,
        run_id=run.id,
        source_type="web",
        source_name="careers",
        source_url="https://careers.example.com/jobs/data-scientist",
        title="Data Scientist, AI Assistant Search",
        raw_text="Raw source text should not be copied into lineage payloads.",
        raw_json={"secret": "raw-json-should-not-be-copied"},
        published_at=now - timedelta(days=1),
        fetched_at=now,
        content_hash="d" * 64,
    )
    db_session.add(source)
    await db_session.flush()

    db_session.add(
        ResearchEvidenceItem(
            user_id=TEST_USER_ID,
            profile_id=profile.id,
            run_id=run.id,
            report_id=report.id,
            source_item_id=source.id,
            evidence_type="job_posting",
            title="Assistant search role opened",
            claim="Banking AI teams are hiring for assistant search and NLP work.",
            url=source.source_url,
            domain="careers.example.com",
            company_name="Bank of America",
            role_title="Data Scientist",
            confidence=0.91,
            relevance_score=0.88,
        )
    )
    db_session.add(
        ResearchRunStep(
            user_id=TEST_USER_ID,
            profile_id=profile.id,
            run_id=run.id,
            step_name="writer",
            step_order=1,
            status="succeeded",
            model_name="gpt-5.4",
            prompt_version="radar-writer-v1",
            tokens_in=2_000,
            tokens_out=800,
            cost_estimate_cents=18,
            started_at=now - timedelta(seconds=25),
            completed_at=now,
        )
    )
    call = await record_model_call(
        db_session,
        user_id=TEST_USER_ID,
        surface="radar",
        task_name="research_report_writer",
        model="gpt-5.4",
        prompt_version="radar-writer-v1",
        status="success",
        token_usage=TokenUsage(prompt_tokens=2_000, output_tokens=800),
        cost_estimate_cents=18,
    )
    artifact = await record_radar_report_artifact(
        db_session,
        report=report,
        run=run,
        model_call_id=call.id,
        path="app://radar/reports/banking-ai",
        metadata={"api_key": "should-redact"},
    )
    await db_session.commit()
    return now, report, artifact, call


@pytest.mark.asyncio
async def test_collect_radar_lineage_is_user_scoped_and_sanitized(db_session):
    now, report, artifact, call = await _seed_radar_report(db_session)

    lineage = await collect_radar_lineage(
        db_session,
        user_id=TEST_USER_ID,
        report_id=report.id,
        as_of=now,
    )

    assert lineage["report"]["id"] == str(report.id)
    assert lineage["profile"]["selected_roles"] == ["Data Scientist", "ML Engineer"]
    assert lineage["quality_metrics"]["source_count"] == 1
    assert lineage["quality_metrics"]["source_coverage_rate"] == 1.0
    assert lineage["quality_metrics"]["linked_model_call_count"] == 1
    assert lineage["model_calls"][0]["id"] == str(call.id)
    assert lineage["artifacts"][0]["id"] == str(artifact.id)
    assert lineage["artifacts"][0]["metadata"]["api_key"] == "[redacted]"
    assert lineage["artifacts"][0]["metadata"]["company_names"] == ["Bank of America"]
    assert "raw_text" not in json.dumps(lineage)
    assert "raw-json-should-not-be-copied" not in json.dumps(lineage)

    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="other", email="other@apptrail.test", name="Other User"))
    await db_session.commit()

    with pytest.raises(RadarLineageNotFoundError):
        await collect_radar_lineage(db_session, user_id=other_user_id, report_id=report.id, as_of=now)


@pytest.mark.asyncio
async def test_radar_lineage_report_bundle_is_reproducible(db_session, tmp_path: Path):
    now, report, _, _ = await _seed_radar_report(db_session)
    lineage = await collect_radar_lineage(db_session, user_id=TEST_USER_ID, report_id=report.id, as_of=now)

    output = Path(
        write_radar_lineage_report_bundle(
            lineage,
            str(tmp_path),
            generated_at=now,
            git_sha="abc123",
            release_version="test-release",
        )
    )

    assert (output / "report.md").exists()
    assert (output / "lineage_payload.json").exists()
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    source_input = json.loads((output / "source_input.json").read_text(encoding="utf-8"))
    assert metadata["report_type"] == "radar_lineage"
    assert metadata["git_sha"] == "abc123"
    assert metrics["source_coverage_rate"] == 1.0
    assert source_input["supporting_artifacts"][0]["path"] == "lineage_payload.json"
