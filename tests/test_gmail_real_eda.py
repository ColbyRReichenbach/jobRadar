import csv
import json
from pathlib import Path

from scripts.run_gmail_real_eda import compute_metrics, write_artifacts


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "gmail_combined_real_baseline_3acct_test"
    _write_csv(
        run_dir / "sync_account_summary.csv",
        [
            {
                "account_label": "account_alumni",
                "audit_rows": 10,
                "stored_rows": 6,
                "filtered_rows": 2,
                "skipped_rows": 2,
                "stored_rate_pct": 60.0,
                "first_audit_at": "2026-05-07T00:00:00Z",
                "last_audit_at": "2026-05-07T00:01:00Z",
            },
            {
                "account_label": "account_noise",
                "audit_rows": 5,
                "stored_rows": 1,
                "filtered_rows": 1,
                "skipped_rows": 3,
                "stored_rate_pct": 20.0,
                "first_audit_at": "2026-05-07T00:00:00Z",
                "last_audit_at": "2026-05-07T00:01:00Z",
            },
        ],
    )
    _write_csv(
        run_dir / "sync_decision_summary.csv",
        [
            {
                "account_label": "account_alumni",
                "decision": "stored",
                "reason": "job_related",
                "classification": "interview_request",
                "message_count": 4,
            },
            {
                "account_label": "account_alumni",
                "decision": "stored",
                "reason": "job_related",
                "classification": "conversation",
                "message_count": 2,
            },
            {
                "account_label": "account_alumni",
                "decision": "filtered",
                "reason": "classifier_not_relevant",
                "classification": "not_relevant",
                "message_count": 2,
            },
            {
                "account_label": "account_noise",
                "decision": "skipped",
                "reason": "obvious_noise",
                "classification": "",
                "message_count": 3,
            },
        ],
    )
    _write_csv(
        run_dir / "sync_domain_summary_top300.csv",
        [
            {
                "account_label": "account_alumni",
                "sender_domain": "notifications.joinhandshake.com",
                "decision": "stored",
                "reason": "job_related",
                "classification": "interview_request",
                "message_count": 4,
            }
        ],
    )
    _write_csv(
        run_dir / "stored_event_summary.csv",
        [
            {
                "account_label": "account_alumni",
                "classification": "interview_request",
                "email_type": "decision",
                "event_count": 4,
                "avg_confidence": 0.86,
            },
            {
                "account_label": "account_alumni",
                "classification": "conversation",
                "email_type": "conversation",
                "event_count": 2,
                "avg_confidence": 0.53,
            },
        ],
    )
    _write_csv(
        run_dir / "stored_event_domain_summary_top300.csv",
        [
            {
                "account_label": "account_alumni",
                "sender_domain": "notifications.joinhandshake.com",
                "classification": "interview_request",
                "email_type": "decision",
                "event_count": 4,
                "avg_confidence": 0.86,
            },
            {
                "account_label": "account_alumni",
                "sender_domain": "notifications.joinhandshake.com",
                "classification": "conversation",
                "email_type": "conversation",
                "event_count": 2,
                "avg_confidence": 0.53,
            },
            {
                "account_label": "account_noise",
                "sender_domain": "twitch.tv",
                "classification": "conversation",
                "email_type": "conversation",
                "event_count": 1,
                "avg_confidence": 0.5,
            },
        ],
    )
    _write_csv(
        run_dir / "sync_run_latency_summary.csv",
        [
            {
                "account_label": "account_alumni",
                "sync_run_id": "run-1",
                "message_count": 10,
                "first_audit_at": "2026-05-07T00:00:00Z",
                "last_audit_at": "2026-05-07T00:01:00Z",
                "audit_window_seconds": 60,
            }
        ],
    )
    _write_csv(
        run_dir / "gmail_classifier_model_call_summary.csv",
        [
            {
                "account_label": "account_alumni",
                "gmail_classifier_model_call_count": 0,
                "total_tokens": 0,
                "cost_estimate_cents": 0,
            }
        ],
    )
    summary_dir = run_dir / "events_account_alumni"
    summary_dir.mkdir(parents=True)
    (summary_dir / "summary.json").write_text(
        json.dumps(
            {
                "event_count": 6,
                "manual_review_count": 4,
                "would_call_llm_count": 4,
                "prompt_leak_count": 0,
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_compute_metrics_surfaces_opportunity_discovery_gap(tmp_path: Path):
    run_dir = _make_run_dir(tmp_path)

    metrics = compute_metrics(run_dir)

    assert metrics["totals"]["sync_audit_decisions"] == 15
    assert metrics["totals"]["stored_product_emails"] == 7
    assert metrics["opportunity_discovery_gap"]["stored_event_count"] == 6
    assert metrics["opportunity_discovery_gap"]["by_domain"] == {"notifications.joinhandshake.com": 6}
    assert metrics["opportunity_discovery_gap"]["by_current_classification"] == {
        "interview_request": 4,
        "conversation": 2,
    }
    assert "confidence_audit" in metrics
    assert metrics["confidence_audit"]["confidence_exact_by_classification"] == []


def test_write_artifacts_creates_summary_metrics_and_notebook(tmp_path: Path):
    run_dir = _make_run_dir(tmp_path)

    output_dir = write_artifacts(run_dir)

    assert (output_dir / "eda_metrics.json").exists()
    assert (output_dir / "eda_summary.md").exists()
    assert (output_dir / "charts.md").exists()
    assert (output_dir / "charts/current_routing_bins.svg").exists()
    assert (output_dir / "charts/confidence_score_clusters.svg").exists()
    assert (output_dir / "redacted_examples.md").exists()
    notebook = json.loads((output_dir / "gmail_classifier_real_eda.ipynb").read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    summary = (output_dir / "eda_summary.md").read_text(encoding="utf-8")
    assert "Opportunity-Discovery Gap" in summary
    assert "Confidence Audit" in summary
