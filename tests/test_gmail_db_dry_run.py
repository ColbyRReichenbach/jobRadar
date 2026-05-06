import json
import uuid

import pytest

from backend.models import EmailEvent
from backend.services.evals.gmail_db_dry_run import (
    GmailDbDryRunOptions,
    analyze_email_event_for_dry_run,
    render_db_dry_run_review,
    run_db_gmail_dry_run,
    write_db_dry_run_artifacts,
)


@pytest.mark.asyncio
async def test_analyze_email_event_for_dry_run_redacts_private_values():
    event = EmailEvent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        gmail_message_id="gmail-raw-id",
        thread_id="thread-raw-id",
        sender="Alex Rivera",
        sender_email="alex.rivera@northstar.example",
        sender_domain="northstar.example",
        subject="Quick follow up",
        body=(
            "Are you still interested in the role? Email john.personal@example.com or call 555-111-2222. "
            "Use https://careers.example.com/status?candidateId=abc123&token=secret to review details."
        ),
        classification="conversation",
        email_type="conversation",
    )

    result = await analyze_email_event_for_dry_run(event)
    serialized = json.dumps(result)

    assert result["preflight"]["would_call_llm"] is True
    assert result["hybrid"]["model_used"] is False
    assert "john.personal@example.com" not in serialized
    assert "555-111-2222" not in serialized
    assert "candidateId=abc123" not in serialized
    assert "token=secret" not in serialized
    assert "Alex Rivera" not in serialized
    assert "[PRIVATE_APPLICATION_URL]" in serialized
    assert result["preflight"]["leak_findings"] == []


@pytest.mark.asyncio
async def test_run_db_gmail_dry_run_summarizes_local_events(db_session):
    event = EmailEvent(
        user_id=uuid.uuid4(),
        gmail_message_id="dry-run-msg-1",
        sender="GitHub",
        sender_email="noreply@github.com",
        sender_domain="github.com",
        subject="Security alert",
        body="A dependency alert was detected.",
        classification="job_update",
        email_type="decision",
    )
    db_session.add(event)
    await db_session.commit()

    result = await run_db_gmail_dry_run(db_session, GmailDbDryRunOptions(limit=50))

    assert result["summary"]["event_count"] == 1
    assert result["summary"]["model_call_count"] == 0
    assert result["summary"]["hybrid_classification_counts"]["not_relevant"] == 1
    assert result["summary"]["route_change_count"] == 1
    assert result["manual_label_queue"]


def test_write_db_dry_run_artifacts(tmp_path):
    result = {
        "summary": {
            "event_count": 1,
            "model_call_count": 0,
            "prompt_leak_rate": 0,
        },
        "options": {"limit": 1},
        "case_results": [
            {
                "event_ref": "email_123",
                "sender_domain": "example.com",
                "existing": {"classification": "conversation", "route": "conversation"},
                "hybrid": {
                    "classification": "conversation",
                    "route": "conversation",
                    "confidence": 0.5,
                    "confidence_band": "medium",
                    "decision_path": "ambiguous_no_model_fallback",
                },
                "preflight": {
                    "would_call_llm": True,
                    "blocked": False,
                    "block_reason": None,
                    "redaction_counts": {"email": 1},
                    "leak_findings": [],
                    "prompt_preview": "From: [SENDER] <[EMAIL]>",
                },
                "redacted_email_preview": {
                    "sender": "[SENDER]",
                    "sender_email": "[EMAIL]",
                    "subject": "Role question",
                    "body_preview": "Are you interested?",
                },
                "needs_manual_review": True,
                "review_reasons": ["would_call_llm"],
            }
        ],
        "manual_label_queue": [],
    }
    result["manual_label_queue"] = result["case_results"]

    output = write_db_dry_run_artifacts(result, tmp_path / "run")
    review = render_db_dry_run_review(result)

    assert (output / "summary.json").exists()
    assert (output / "trace.jsonl").exists()
    assert (output / "manual_label_queue.jsonl").exists()
    assert (output / "review.md").exists()
    assert "Would-be LLM prompt preview" in review
