import csv
import json
from pathlib import Path

from scripts.create_gmail_labeling_queue import (
    ERROR_BUCKETS,
    EXPECTED_ROUTES,
    EXPECTED_SUBTYPES,
    create_labeling_queues,
)


def _write_trace(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _case(
    *,
    event_ref: str,
    sender_domain: str,
    classification: str,
    confidence: float,
    matched_features: list[str],
    subject: str = "New role",
    body: str = "Apply early to stand out. Raleigh, NC (Onsite).",
):
    return {
        "event_ref": event_ref,
        "received_at": "2026-05-07T00:00:00+00:00",
        "sender_domain": sender_domain,
        "needs_manual_review": False,
        "review_reasons": [],
        "existing": {
            "route": "inbox" if classification != "conversation" else "conversation",
            "classification": classification,
            "confidence": confidence,
        },
        "hybrid": {
            "route": "inbox" if classification != "conversation" else "conversation",
            "classification": classification,
            "confidence": confidence,
            "confidence_band": "high" if confidence >= 0.7 else "medium",
            "decision_path": "deterministic_high_confidence",
            "matched_features": matched_features,
            "ambiguity_reasons": [],
            "scores": {
                "job_signal_score": confidence,
                "noise_score": 0,
                "top_category": classification,
                "top_score": confidence,
                "second_score": 0.25,
                "margin": confidence - 0.25,
            },
        },
        "preflight": {
            "would_call_llm": False,
            "leak_findings": [],
        },
        "redacted_email_preview": {
            "subject": subject,
            "body_preview": body,
        },
    }


def test_create_labeling_queues_outputs_taxonomy_and_priority_rows(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_trace(
        run_dir / "events_account_alumni" / "trace.jsonl",
        [
            _case(
                event_ref="email_1",
                sender_domain="notifications.joinhandshake.com",
                classification="interview_request",
                confidence=0.86,
                matched_features=["text_has_job_signal", "interview_request_phrase:onsite"],
            ),
            _case(
                event_ref="email_2",
                sender_domain="myworkday.com",
                classification="job_update",
                confidence=0.82,
                matched_features=["sender_domain_is_ats"],
            ),
        ],
    )

    output_dir = create_labeling_queues(run_dir)

    values = json.loads((output_dir / "label_values.json").read_text(encoding="utf-8"))
    assert values["expected_routes"] == EXPECTED_ROUTES
    assert values["expected_subtypes"] == EXPECTED_SUBTYPES
    assert values["error_buckets"] == ERROR_BUCKETS

    with (output_dir / "label_queue_priority.csv").open(newline="", encoding="utf-8") as handle:
        priority_rows = list(csv.DictReader(handle))
    assert len(priority_rows) == 1
    assert priority_rows[0]["case_id"] == "email_1"
    assert priority_rows[0]["expected_route"] == ""
    assert "opportunity_domain" in priority_rows[0]["priority_reason"]
    assert "interview_without_scheduler" in priority_rows[0]["priority_reason"]

    with (output_dir / "label_queue_all_stored.csv").open(newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))
    assert len(all_rows) == 2
    assert "redacted_body_preview" in all_rows[0]
