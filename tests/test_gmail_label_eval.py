import csv
import json
from pathlib import Path

from scripts.run_gmail_label_eval import compute_label_metrics, normalize_predicted_route, write_artifacts


def _write_labels(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _row(
    *,
    case_id: str,
    predicted_route: str,
    predicted_classification: str,
    confidence: float,
    expected_route: str,
    expected_subtype: str,
    is_correct: str,
    error_bucket: str,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "account_label": "account_test",
        "received_at": "2026-05-07T00:00:00Z",
        "sender_domain": "notifications.joinhandshake.com",
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
        "matched_features": "interview_request_phrase:onsite",
        "ambiguity_reasons": "",
        "review_reasons": "",
        "needs_manual_review": "false",
        "would_call_llm": "false",
        "prompt_leak_count": 0,
        "redacted_subject": "Redacted",
        "redacted_body_preview": "Redacted preview",
        "expected_route": expected_route,
        "expected_subtype": expected_subtype,
        "is_correct": is_correct,
        "error_bucket": error_bucket,
        "review_notes": "",
        "priority_reason": "opportunity_domain",
    }


def test_normalize_predicted_route_maps_legacy_inbox_to_application_inbox():
    assert normalize_predicted_route({"predicted_route": "inbox", "predicted_classification": "interview_request"}) == "application_inbox"
    assert normalize_predicted_route({"predicted_route": "conversation", "predicted_classification": "conversation"}) == "conversation"
    assert normalize_predicted_route({"predicted_route": "inbox", "predicted_classification": "not_relevant"}) == "filter"


def test_normalize_predicted_subtype_prefers_route_first_subtype():
    row = {
        "predicted_subtype": "recruiter_outreach",
        "predicted_classification": "conversation",
    }

    from scripts.run_gmail_label_eval import normalize_predicted_subtype

    assert normalize_predicted_subtype(row) == "recruiter_outreach"


def test_compute_label_metrics_scores_route_and_subtype(tmp_path: Path):
    label_path = tmp_path / "labels.csv"
    _write_labels(
        label_path,
        [
            _row(
                case_id="one",
                predicted_route="inbox",
                predicted_classification="interview_request",
                confidence=0.86,
                expected_route="filter",
                expected_subtype="job_alert",
                is_correct="no",
                error_bucket="false_positive_opportunity_as_lifecycle",
            ),
            _row(
                case_id="two",
                predicted_route="inbox",
                predicted_classification="interview_request",
                confidence=0.94,
                expected_route="application_inbox",
                expected_subtype="interview_request",
                is_correct="yes",
                error_bucket="correct",
            ),
        ],
    )

    metrics = compute_label_metrics(label_path)

    assert metrics["validation"]["is_valid"]
    assert metrics["totals"]["labeled_rows"] == 2
    assert metrics["totals"]["route_accuracy_pct"] == 50.0
    assert metrics["totals"]["subtype_exact_match_pct"] == 50.0
    assert metrics["totals"]["high_confidence_wrong_count"] == 1
    assert metrics["distributions"]["error_bucket"]["false_positive_opportunity_as_lifecycle"] == 1


def test_write_artifacts_creates_report_metrics_confusions_and_charts(tmp_path: Path):
    label_path = tmp_path / "labels.csv"
    _write_labels(
        label_path,
        [
            _row(
                case_id="one",
                predicted_route="conversation",
                predicted_classification="conversation",
                confidence=0.5,
                expected_route="conversation",
                expected_subtype="recruiter_outreach",
                is_correct="partial",
                error_bucket="wrong_stage",
            )
        ],
    )

    output_dir = write_artifacts(label_path)

    assert (output_dir / "label_eval_report.md").exists()
    assert (output_dir / "label_eval_metrics.json").exists()
    assert (output_dir / "route_confusion.csv").exists()
    assert (output_dir / "subtype_confusion_top.csv").exists()
    assert (output_dir / "charts/error_buckets.svg").exists()
    metrics = json.loads((output_dir / "label_eval_metrics.json").read_text(encoding="utf-8"))
    assert metrics["totals"]["human_partial_pct"] == 100.0
