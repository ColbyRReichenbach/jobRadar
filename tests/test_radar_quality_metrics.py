import uuid
from datetime import datetime, timedelta, timezone

from backend.models import AiModelCall, ResearchEvidenceItem, ResearchReport, ResearchRun, ResearchRunStep, ResearchSourceItem
from backend.services.research_radar.lineage import compute_radar_quality_metrics
from tests.conftest import TEST_USER_ID


def test_compute_radar_quality_metrics_tracks_sources_evidence_and_costs():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    profile_id = uuid.uuid4()
    run_id = uuid.uuid4()
    report_id = uuid.uuid4()
    source_a = uuid.uuid4()
    source_b = uuid.uuid4()
    source_c = uuid.uuid4()

    run = ResearchRun(
        id=run_id,
        user_id=TEST_USER_ID,
        profile_id=profile_id,
        status="succeeded",
        started_at=now - timedelta(minutes=4),
        completed_at=now - timedelta(minutes=1),
        tokens_in=1_000,
        tokens_out=500,
        llm_call_count=2,
        cost_estimate_cents=12,
    )
    report = ResearchReport(
        id=report_id,
        user_id=TEST_USER_ID,
        profile_id=profile_id,
        run_id=run_id,
        title="Weekly AI Hiring Radar",
        structured_json={"verification": {"unsupported_claim_count": 1, "claim_count": 5}},
    )
    sources = [
        ResearchSourceItem(
            id=source_a,
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            source_type="web",
            source_url="https://example.com/jobs/1",
            title="Fresh job",
            published_at=now - timedelta(days=2),
            fetched_at=now,
            content_hash="a" * 64,
        ),
        ResearchSourceItem(
            id=source_b,
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            source_type="web",
            source_url="https://example.com/jobs/1/",
            title="Fresh duplicate URL",
            published_at=now - timedelta(days=4),
            fetched_at=now,
            content_hash="b" * 64,
        ),
        ResearchSourceItem(
            id=source_c,
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            source_type="web",
            source_url="https://stale.example.com/news",
            title="Stale news",
            published_at=now - timedelta(days=90),
            fetched_at=now - timedelta(days=90),
            content_hash="c" * 64,
        ),
    ]
    evidence = [
        ResearchEvidenceItem(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            report_id=report_id,
            source_item_id=source_a,
            evidence_type="job_posting",
            claim="ExampleCo opened a new ML role.",
        ),
        ResearchEvidenceItem(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            report_id=report_id,
            evidence_type="company_update",
            claim="ExampleCo shipped a new assistant feature.",
            url="https://example.com/blog/assistant",
        ),
        ResearchEvidenceItem(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            report_id=report_id,
            evidence_type="company_update",
            claim="Unsupported claim with no source.",
        ),
    ]
    steps = [
        ResearchRunStep(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            step_name="planner",
            step_order=1,
            status="succeeded",
            started_at=now,
            completed_at=now + timedelta(seconds=10),
        ),
        ResearchRunStep(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            profile_id=profile_id,
            run_id=run_id,
            step_name="writer",
            step_order=2,
            status="failed",
            started_at=now,
            completed_at=now + timedelta(seconds=20),
        ),
    ]
    model_calls = [
        AiModelCall(
            id=uuid.uuid4(),
            user_id=TEST_USER_ID,
            surface="radar",
            task_name="research_report_writer",
            provider="openai",
            model="gpt-5.4",
            prompt_version="radar-writer-v1",
            status="success",
            prompt_tokens=700,
            output_tokens=200,
            total_tokens=900,
            cost_estimate_cents=6,
        )
    ]

    metrics = compute_radar_quality_metrics(
        report=report,
        run=run,
        evidence_items=evidence,
        source_items=sources,
        steps=steps,
        model_calls=model_calls,
        as_of=now,
    )

    assert metrics["source_count"] == 3
    assert metrics["duplicate_source_url_count"] == 1
    assert metrics["duplicate_source_url_rate"] == 0.3333
    assert metrics["fresh_source_count"] == 2
    assert metrics["source_freshness_rate"] == 0.6667
    assert metrics["covered_evidence_count"] == 2
    assert metrics["source_coverage_rate"] == 0.6667
    assert metrics["unsupported_claim_rate"] == 0.2
    assert metrics["linked_model_call_cost_cents"] == 6
    assert metrics["effective_cost_per_report_cents"] == 6
    assert metrics["projected_cost_per_1000_reports_cents"] == 6_000
    assert metrics["successful_run_step_count"] == 1
    assert metrics["failed_run_step_count"] == 1
    assert metrics["p95_step_duration_seconds"] == 20.0
