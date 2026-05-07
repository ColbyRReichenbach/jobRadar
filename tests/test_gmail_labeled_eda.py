import csv
import json
from pathlib import Path

from scripts.run_gmail_labeled_eda import compute_labeled_eda, write_artifacts


def _write_labels(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _row(
    *,
    case_id: str,
    sender_domain: str,
    predicted_route: str,
    predicted_classification: str,
    confidence: float,
    subject: str,
    body: str,
    expected_route: str,
    expected_subtype: str,
    is_correct: str,
    error_bucket: str,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "account_label": "account_test",
        "received_at": "2026-05-07T00:00:00Z",
        "sender_domain": sender_domain,
        "predicted_route": predicted_route,
        "predicted_classification": predicted_classification,
        "predicted_confidence": confidence,
        "confidence_band": "high" if confidence >= 0.7 else "medium",
        "decision_path": "deterministic_high_confidence",
        "job_signal_score": confidence,
        "noise_score": 0,
        "top_category": predicted_classification,
        "top_score": confidence,
        "second_score": 0.2,
        "margin": confidence - 0.2,
        "matched_features": "interview_request_phrase:onsite;text_has_job_signal",
        "ambiguity_reasons": "",
        "review_reasons": "",
        "needs_manual_review": "false",
        "would_call_llm": "false",
        "prompt_leak_count": 0,
        "redacted_subject": subject,
        "redacted_body_preview": body,
        "expected_route": expected_route,
        "expected_subtype": expected_subtype,
        "is_correct": is_correct,
        "error_bucket": error_bucket,
        "review_notes": "",
        "priority_reason": "opportunity_domain",
    }


def test_compute_labeled_eda_finds_theme_patterns_and_lift(tmp_path: Path):
    label_path = tmp_path / "labels.csv"
    rows = [
        _row(
            case_id="one",
            sender_domain="notifications.joinhandshake.com",
            predicted_route="inbox",
            predicted_classification="interview_request",
            confidence=0.86,
            subject="Jobs for you",
            body="Apply to onsite analyst jobs and opportunities today.",
            expected_route="filter",
            expected_subtype="job_alert",
            is_correct="no",
            error_bucket="false_positive_opportunity_as_lifecycle",
        ),
        _row(
            case_id="two",
            sender_domain="notifications.joinhandshake.com",
            predicted_route="inbox",
            predicted_classification="interview_request",
            confidence=0.86,
            subject="Recommended jobs",
            body="Apply for new onsite roles and opportunities.",
            expected_route="filter",
            expected_subtype="job_alert",
            is_correct="no",
            error_bucket="false_positive_opportunity_as_lifecycle",
        ),
        _row(
            case_id="three",
            sender_domain="gmail.com",
            predicted_route="conversation",
            predicted_classification="conversation",
            confidence=0.5,
            subject="Intro",
            body="A recruiter wants to connect about your background.",
            expected_route="conversation",
            expected_subtype="recruiter_outreach",
            is_correct="yes",
            error_bucket="correct",
        ),
    ]
    _write_labels(label_path, rows)

    metrics = compute_labeled_eda(label_path)

    assert metrics["label_metrics"]["totals"]["labeled_rows"] == 3
    assert any(row["theme"] == "handshake_job_alert_filter" for row in metrics["theme_clusters"])
    assert any(row["pattern"] == "apply_language" and row["matched_rows"] == 2 for row in metrics["pattern_diagnostics"])
    assert any(row["group"] == "false_positive_opportunity_as_lifecycle" for row in metrics["error_ngram_lift"])
    assert metrics["examples"]


def test_write_artifacts_creates_workspace_files(tmp_path: Path):
    label_path = tmp_path / "labels.csv"
    _write_labels(
        label_path,
        [
            _row(
                case_id="one",
                sender_domain="gmail.com",
                predicted_route="conversation",
                predicted_classification="conversation",
                confidence=0.5,
                subject="Intro",
                body="Recruiter wants to connect.",
                expected_route="conversation",
                expected_subtype="recruiter_outreach",
                is_correct="yes",
                error_bucket="correct",
            )
        ],
    )

    output_dir = write_artifacts(label_path)

    assert (output_dir / "labeled_eda_report.md").exists()
    assert (output_dir / "labeled_eda_metrics.json").exists()
    assert (output_dir / "theme_clusters.csv").exists()
    assert (output_dir / "pattern_diagnostics.csv").exists()
    assert (output_dir / "redacted_examples_by_theme.md").exists()
    assert (output_dir / "gmail_labeled_eda_workspace.ipynb").exists()
    assert (output_dir / "charts/route_confusion_heatmap.svg").exists()
    notebook = json.loads((output_dir / "gmail_labeled_eda_workspace.ipynb").read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    namespace: dict[str, object] = {}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            exec("".join(cell["source"]), namespace)
