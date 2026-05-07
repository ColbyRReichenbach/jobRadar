import json
from pathlib import Path

from scripts.run_gmail_unlabeled_eda import compute_unlabeled_eda, write_artifacts


def _case(
    *,
    event_ref: str,
    sender_domain: str,
    route: str,
    subtype: str,
    subject: str,
    body: str,
    would_call_llm: bool = False,
    confidence_band: str = "high",
) -> dict[str, object]:
    return {
        "event_ref": event_ref,
        "sender_domain": sender_domain,
        "existing": {"route": "application_inbox", "classification": "interview_request"},
        "hybrid": {
            "route": route,
            "subtype": subtype,
            "classification": "not_relevant" if route == "filter" else "conversation",
            "confidence": 0.86,
            "confidence_band": confidence_band,
            "decision_path": "deterministic_high_confidence",
            "matched_features": ["text_has_job_signal", "job_update_phrase:apply"],
            "scores": {
                "route_margin": 0.5,
                "subtype_margin": 0.4,
            },
        },
        "preflight": {
            "would_call_llm": would_call_llm,
            "blocked": False,
            "leak_findings": [],
        },
        "redacted_email_preview": {
            "subject": subject,
            "body_preview": body,
        },
        "review_reasons": ["route_changed"] if route == "filter" else [],
    }


def _write_trace(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_compute_unlabeled_eda_summarizes_route_policy(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(
        trace_path,
        [
            _case(
                event_ref="email_one",
                sender_domain="notifications.joinhandshake.com",
                route="filter",
                subtype="job_alert",
                subject="Jobs for you",
                body="Apply to recommended analyst opportunities.",
            ),
            _case(
                event_ref="email_two",
                sender_domain="notifications.joinhandshake.com",
                route="filter",
                subtype="job_alert",
                subject="Recommended roles",
                body="Apply to recommended analyst jobs.",
            ),
            _case(
                event_ref="email_three",
                sender_domain="gmail.com",
                route="action_review",
                subtype="recruiter_outreach",
                subject="Quick question",
                body="A recruiter wants to connect about a data role.",
                would_call_llm=True,
                confidence_band="medium",
            ),
        ],
    )

    metrics = compute_unlabeled_eda(trace_path)

    assert metrics["summary"]["case_count"] == 3
    assert metrics["summary"]["filter_job_alert_or_promo_count"] == 2
    assert metrics["summary"]["would_call_llm_count"] == 1
    assert any(row["route"] == "filter" and row["count"] == 2 for row in metrics["route_counts"])
    assert any(row["group"] == "filter" for row in metrics["route_ngram_lift"])
    assert any(row["label_bucket"] == "filter_job_alert" for row in metrics["targeted_label_queue"])
    assert any(row["label_bucket"] == "action_review_or_llm" for row in metrics["targeted_label_queue"])


def test_write_artifacts_creates_unlabeled_workspace(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(
        trace_path,
        [
            _case(
                event_ref="email_one",
                sender_domain="notifications.joinhandshake.com",
                route="filter",
                subtype="job_alert",
                subject="Jobs for you",
                body="Apply to recommended analyst opportunities.",
            )
        ],
    )

    output_dir = write_artifacts(trace_path)

    assert (output_dir / "unlabeled_eda_report.md").exists()
    assert (output_dir / "unlabeled_eda_metrics.json").exists()
    assert (output_dir / "route_domain_summary.csv").exists()
    assert (output_dir / "review_candidates.csv").exists()
    assert (output_dir / "targeted_label_queue.csv").exists()
    assert (output_dir / "targeted_labeling_guidelines.md").exists()
    assert (output_dir / "redacted_examples_by_route.md").exists()
    assert (output_dir / "gmail_unlabeled_eda_workspace.ipynb").exists()
    assert (output_dir / "charts/route_distribution.svg").exists()
    notebook = json.loads((output_dir / "gmail_unlabeled_eda_workspace.ipynb").read_text(encoding="utf-8"))
    namespace: dict[str, object] = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            exec("".join(cell["source"]), namespace)
