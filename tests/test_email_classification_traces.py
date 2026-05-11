import pytest
from sqlalchemy import select

from backend.models import EmailClassificationTrace, EmailEvent
from backend.services.email_classification_traces import create_email_classification_trace
from backend.services.email_classifier import classify_email
from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
async def test_email_classification_trace_persists_dry_run_metadata_without_raw_content(monkeypatch, db_session):
    monkeypatch.setenv("GMAIL_CLASSIFIER_MODE", "hybrid_dry_run")
    classification = await classify_email(
        subject="Schedule your interview",
        body="Please choose a time for your interview.",
        sender="Acme Recruiting",
        sender_email="recruiting@acme.example",
        ai_enabled=True,
        raw_candidate_urls=("https://calendly.com/acme/interview?token=secret",),
    )
    event = EmailEvent(
        user_id=TEST_USER_ID,
        gmail_message_id="trace-msg-1",
        sender="Acme Recruiting",
        sender_email="recruiting@acme.example",
        subject="Schedule your interview",
        body="Please choose a time for your interview.",
        classification=classification["classification"],
        email_type="decision",
        confidence=classification["confidence"],
    )
    db_session.add(event)
    await db_session.flush()

    trace = await create_email_classification_trace(
        db_session,
        user_id=TEST_USER_ID,
        classification=classification,
        email_event=event,
        candidate_source_url_count=classification["candidate_source_url_count"],
    )
    await db_session.commit()

    saved = (await db_session.execute(select(EmailClassificationTrace).where(EmailClassificationTrace.id == trace.id))).scalar_one()
    assert saved.email_event_id == event.id
    assert saved.classifier_mode == "hybrid_dry_run"
    assert saved.route == "application_inbox"
    assert saved.subtype == "interview_request"
    assert saved.route_confidence is not None
    assert saved.subtype_confidence is not None
    assert saved.threshold_version == "classifier-thresholds-v1"
    assert saved.model_used is False
    assert saved.candidate_source_url_count == 1
    assert saved.preflight_status == "dry_run_no_model"
    assert "Please choose a time" not in str(saved.feature_summary_json)
    assert "token=secret" not in str(saved.feature_summary_json)


@pytest.mark.asyncio
async def test_email_classification_trace_supports_filtered_without_email_event(db_session):
    trace = await create_email_classification_trace(
        db_session,
        user_id=TEST_USER_ID,
        gmail_message_id="filtered-msg-1",
        candidate_source_url_count=0,
        classification={
            "classifier_mode": "hybrid_dry_run",
            "classification": "not_relevant",
            "confidence": 0.91,
            "route": "filter",
            "subtype": "marketing_promo",
            "route_confidence": 0.92,
            "subtype_confidence": 0.88,
            "decision_path": "deterministic_noise_skip",
            "threshold_version": "classifier-thresholds-v1",
            "matched_features": ["marketing_language:newsletter"],
            "model_used": False,
        },
    )
    await db_session.commit()

    assert trace.email_event_id is None
    assert trace.gmail_message_id == "filtered-msg-1"
    assert trace.route == "filter"


@pytest.mark.asyncio
async def test_email_classification_trace_upserts_same_message_and_mode(db_session):
    first = await create_email_classification_trace(
        db_session,
        user_id=TEST_USER_ID,
        gmail_message_id="filtered-msg-upsert",
        candidate_source_url_count=0,
        classification={
            "classifier_mode": "hybrid_dry_run",
            "classification": "not_relevant",
            "confidence": 0.91,
            "route": "filter",
            "subtype": "marketing_promo",
            "route_confidence": 0.92,
            "subtype_confidence": 0.88,
            "decision_path": "deterministic_noise_skip",
            "threshold_version": "classifier-thresholds-v1",
            "matched_features": ["marketing_language:newsletter"],
            "model_used": False,
        },
    )
    second = await create_email_classification_trace(
        db_session,
        user_id=TEST_USER_ID,
        gmail_message_id="filtered-msg-upsert",
        candidate_source_url_count=2,
        classification={
            "classifier_mode": "hybrid_dry_run",
            "classification": "not_relevant",
            "confidence": 0.85,
            "route": "filter",
            "subtype": "job_board_promo",
            "route_confidence": 0.86,
            "subtype_confidence": 0.8,
            "decision_path": "deterministic_noise_skip",
            "threshold_version": "classifier-thresholds-v1",
            "matched_features": ["marketing_language:jobs"],
            "model_used": False,
        },
    )
    await db_session.commit()

    traces = list((await db_session.execute(select(EmailClassificationTrace))).scalars().all())
    assert second.id == first.id
    assert len(traces) == 1
    assert traces[0].subtype == "job_board_promo"
    assert traces[0].candidate_source_url_count == 2
