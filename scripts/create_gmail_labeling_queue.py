#!/usr/bin/env python3
"""Create private Gmail classifier labeling CSVs from a real-data audit run."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_RUN_GLOB = "audit/runs/gmail_combined_real_baseline*"

EXPECTED_ROUTES = [
    "filter",
    "application_inbox",
    "opportunity_discovery",
    "conversation",
    "action_review",
    "unsure",
]

EXPECTED_SUBTYPES = [
    "application_received",
    "application_status_update",
    "interview_request",
    "rejection",
    "offer",
    "assessment_or_task",
    "document_request",
    "recruiter_outreach",
    "referral_or_networking",
    "job_alert",
    "job_board_promo",
    "career_fair_or_event",
    "company_newsletter",
    "marketing_promo",
    "finance_noise",
    "retail_noise",
    "system_notification",
    "personal_email",
    "school_or_alumni_update",
    "unknown_other",
    "unsure",
]

ERROR_BUCKETS = [
    "correct",
    "false_positive_noise",
    "false_positive_opportunity_as_lifecycle",
    "false_positive_marketing_as_conversation",
    "wrong_route",
    "wrong_stage",
    "overconfident_score",
    "false_negative_job_related",
    "missing_context",
    "pii_redaction_issue",
    "duplicate_or_thread_noise",
    "unsure",
]

OPPORTUNITY_DISCOVERY_DOMAIN_HINTS = (
    "handshake",
    "joinhandshake",
    "indeed",
    "linkedin",
    "glassdoor",
    "ziprecruiter",
)
MARKETING_DOMAIN_HINTS = (
    "carvana",
    "foodlion",
    "salliemae",
    "discounttire",
    "chick-fil-a",
    "fanduel",
    "shein",
)


@dataclass(frozen=True)
class LabelRow:
    data: dict[str, Any]
    priority_score: int
    priority_reason: str


def _latest_run_dir(pattern: str = DEFAULT_RUN_GLOB) -> Path:
    candidates = [path for path in Path(".").glob(pattern) if path.is_dir()]
    if not candidates:
        raise SystemExit(f"No run directories found for {pattern!r}.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_trace_rows(run_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for trace_path in sorted(run_dir.glob("events_*/trace.jsonl")):
        account_label = trace_path.parent.name.replace("events_", "")
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append((account_label, json.loads(line)))
    return rows


def _joined(values: object) -> str:
    if isinstance(values, list):
        return ";".join(str(value) for value in values)
    return str(values or "")


def _truncate(text: str | None, limit: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _contains_domain_hint(domain: str, hints: tuple[str, ...]) -> bool:
    normalized = (domain or "").lower()
    return any(hint in normalized for hint in hints)


def _priority_for_case(row: dict[str, Any]) -> tuple[int, str]:
    sender_domain = row["sender_domain"]
    predicted_classification = row["predicted_classification"]
    predicted_confidence = float(row["predicted_confidence"] or 0)
    matched_features = row["matched_features"]
    decision_path = row["decision_path"]

    reasons: list[str] = []
    score = 0
    if _contains_domain_hint(sender_domain, OPPORTUNITY_DISCOVERY_DOMAIN_HINTS):
        score += 80
        reasons.append("opportunity_domain")
    if predicted_classification == "interview_request" and "scheduler_url" not in matched_features:
        score += 40
        reasons.append("interview_without_scheduler")
    if predicted_confidence >= 0.8 and _contains_domain_hint(sender_domain, OPPORTUNITY_DISCOVERY_DOMAIN_HINTS):
        score += 30
        reasons.append("overconfident_opportunity_cluster")
    if decision_path == "ambiguous_no_model_fallback":
        score += 25
        reasons.append("ambiguous_no_model")
    if _contains_domain_hint(sender_domain, MARKETING_DOMAIN_HINTS):
        score += 25
        reasons.append("marketing_domain")
    if predicted_classification == "conversation" and predicted_confidence <= 0.55:
        score += 15
        reasons.append("low_confidence_conversation")
    if row["needs_manual_review"] == "true":
        score += 10
        reasons.append("manual_review_candidate")
    return score, ";".join(reasons) or "baseline_sample"


def _case_to_label_row(account_label: str, case: dict[str, Any]) -> LabelRow:
    existing = case.get("existing") or {}
    hybrid = case.get("hybrid") or {}
    scores = hybrid.get("scores") or {}
    preview = case.get("redacted_email_preview") or {}
    preflight = case.get("preflight") or {}

    data: dict[str, Any] = {
        "case_id": case.get("event_ref") or "",
        "account_label": account_label,
        "received_at": case.get("received_at") or "",
        "sender_domain": case.get("sender_domain") or "",
        "predicted_route": existing.get("route") or hybrid.get("route") or "",
        "predicted_classification": existing.get("classification") or hybrid.get("classification") or "",
        "predicted_confidence": existing.get("confidence") if existing.get("confidence") is not None else hybrid.get("confidence"),
        "confidence_band": hybrid.get("confidence_band") or "",
        "decision_path": hybrid.get("decision_path") or "",
        "job_signal_score": scores.get("job_signal_score"),
        "noise_score": scores.get("noise_score"),
        "top_category": scores.get("top_category"),
        "top_score": scores.get("top_score"),
        "second_score": scores.get("second_score"),
        "margin": scores.get("margin"),
        "matched_features": _joined(hybrid.get("matched_features")),
        "ambiguity_reasons": _joined(hybrid.get("ambiguity_reasons")),
        "review_reasons": _joined(case.get("review_reasons")),
        "needs_manual_review": str(bool(case.get("needs_manual_review"))).lower(),
        "would_call_llm": str(bool(preflight.get("would_call_llm"))).lower(),
        "prompt_leak_count": len(preflight.get("leak_findings") or []),
        "redacted_subject": _truncate(preview.get("subject"), 220),
        "redacted_body_preview": _truncate(preview.get("body_preview"), 900),
        "expected_route": "",
        "expected_subtype": "",
        "is_correct": "",
        "error_bucket": "",
        "review_notes": "",
    }
    score, reason = _priority_for_case(data)
    data["priority_reason"] = reason
    return LabelRow(data=data, priority_score=score, priority_reason=reason)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _render_guidelines() -> str:
    route_lines = "\n".join(f"- `{item}`" for item in EXPECTED_ROUTES)
    subtype_lines = "\n".join(f"- `{item}`" for item in EXPECTED_SUBTYPES)
    error_lines = "\n".join(f"- `{item}`" for item in ERROR_BUCKETS)
    return f"""# Gmail Classifier Labeling Guidelines

These files are private real-email-derived artifacts. Keep them under `audit/runs/` and do not commit completed labels.

## What To Fill

For each row, fill:

```text
expected_route
expected_subtype
is_correct
error_bucket
review_notes
```

Use `is_correct=yes` only when both the predicted route and predicted classification/subtype are acceptable for the product.

## Expected Routes

{route_lines}

Route definitions:

- `filter`: should not appear in AppTrail.
- `application_inbox`: active application lifecycle email tied to an application or candidate process.
- `opportunity_discovery`: reserved for future non-user-facing discovery/source-intelligence signals, not normal job-board emails.
- `conversation`: human recruiter, referral, alumni, or networking message that belongs in conversations.
- `action_review`: job-related but too ambiguous for a confident route; should wait for review.
- `unsure`: not enough information from the redacted preview.

## Expected Subtypes

{subtype_lines}

Subtype notes:

- Use `job_alert` for repeated opportunity recommendation emails. In the current product, job-board alerts normally pair with `expected_route=filter`.
- Use `job_board_promo` for platform marketing that is job-adjacent but not an application lifecycle event. In the current product, this normally pairs with `expected_route=filter`.
- Use `interview_request` only when there is actual scheduling/interview-process evidence, not just work-location text like `Onsite`.
- Use `recruiter_outreach` when a human or recruiter appears to be directly contacting the user about a role.

## Error Buckets

{error_lines}

Error bucket notes:

- `false_positive_opportunity_as_lifecycle`: job alert/opportunity email was routed as application inbox or lifecycle stage.
- `overconfident_score`: prediction may be directionally related but the score is too high for the evidence.
- `wrong_stage`: right route, wrong lifecycle subtype.
- `wrong_route`: job-related but sent to the wrong AppTrail surface.
- `missing_context`: redacted preview is insufficient to label confidently.

## Recommended Labeling Order

1. Label `label_queue_priority.csv` first.
2. Focus on Handshake/opportunity-alert rows.
3. Then review low-confidence conversations and non-ATS `interview_request` rows.
4. Use `label_queue_all_stored.csv` only if you want full coverage.
"""


def create_labeling_queues(run_dir: Path, output_dir: Path | None = None, *, priority_limit: int = 160) -> Path:
    output_dir = output_dir or run_dir / "labels"
    rows = [_case_to_label_row(account_label, case) for account_label, case in _load_trace_rows(run_dir)]
    sorted_rows = sorted(rows, key=lambda row: (-row.priority_score, row.data["account_label"], row.data["case_id"]))
    all_rows = [row.data for row in sorted_rows]
    priority_rows = [row.data for row in sorted_rows if row.priority_score > 0][:priority_limit]

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "label_queue_all_stored.csv", all_rows)
    _write_csv(output_dir / "label_queue_priority.csv", priority_rows)
    (output_dir / "label_values.json").write_text(
        json.dumps(
            {
                "expected_routes": EXPECTED_ROUTES,
                "expected_subtypes": EXPECTED_SUBTYPES,
                "error_buckets": ERROR_BUCKETS,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (output_dir / "labeling_guidelines.md").write_text(_render_guidelines(), encoding="utf-8")
    (output_dir / "README.md").write_text(
        "# Gmail Labeling Queues\n\n"
        "Private real-email-derived labeling queues. Fill the blank expected/review columns locally. "
        "These files live under `audit/runs/` and should not be committed.\n",
        encoding="utf-8",
    )
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, help="Input audit run directory. Defaults to latest combined real baseline.")
    parser.add_argument("--output-dir", type=Path, help="Optional output directory. Defaults to <run-dir>/labels.")
    parser.add_argument("--priority-limit", type=int, default=160)
    args = parser.parse_args()

    run_dir = args.run_dir or _latest_run_dir()
    output_dir = create_labeling_queues(run_dir, args.output_dir, priority_limit=args.priority_limit)
    print(output_dir)


if __name__ == "__main__":
    main()
