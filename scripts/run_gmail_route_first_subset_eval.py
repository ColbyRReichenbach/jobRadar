#!/usr/bin/env python3
"""Compare route-first Gmail classifier predictions against labeled rows.

The preferred path matches label CSV case IDs back to stored ``EmailEvent`` rows
and reruns the current classifier on the original stored fields. If the DB is
not available or a row cannot be found, the script falls back to the redacted
subject/body preview from the label CSV. Outputs intentionally avoid raw email
body and sender email values.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.models import EmailEvent
from backend.services.gmail_intelligence.orchestrator import analyze_email
from backend.services.gmail_intelligence.preflight import evaluate_llm_preflight
from backend.services.gmail_intelligence.types import EmailCandidate
from scripts.run_gmail_label_eval import normalize_predicted_route, normalize_predicted_subtype

DEFAULT_LABEL_PATH = (
    "audit/runs/gmail_combined_real_baseline_3acct_2026-05-07T00-22-23Z/"
    "labels/label_queue_priority.csv"
)


@dataclass(frozen=True)
class MatchedCandidate:
    candidate: EmailCandidate
    source: str


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _hash_value(value: object, *, prefix: str = "") -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{digest}" if prefix else digest


def _clean(value: object) -> str:
    return str(value or "").strip()


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)) * 100, 2) if denominator else 0.0


def _redacted_candidate_from_label(row: dict[str, str]) -> EmailCandidate:
    domain = _clean(row.get("sender_domain"))
    sender_email = f"notifications@{domain}" if domain else ""
    return EmailCandidate(
        sender=domain or "redacted-sender",
        sender_email=sender_email,
        subject=_clean(row.get("redacted_subject")),
        body=_clean(row.get("redacted_body_preview")),
    )


async def _load_db_candidates(case_ids: set[str], *, db_limit: int) -> dict[str, MatchedCandidate]:
    try:
        from backend.database import async_session_factory
    except Exception:
        return {}

    try:
        async with async_session_factory() as session:
            stmt = (
                select(EmailEvent)
                .order_by(EmailEvent.received_at.desc().nullslast(), EmailEvent.id.desc())
                .limit(db_limit)
            )
            result = await session.execute(stmt)
            events = list(result.scalars().all())
    except Exception:
        return {}

    matched: dict[str, MatchedCandidate] = {}
    for event in events:
        event_ref = _hash_value(event.id, prefix="email_")
        if event_ref not in case_ids:
            continue
        matched[event_ref] = MatchedCandidate(
            candidate=EmailCandidate(
                sender=event.sender or "",
                sender_email=event.sender_email or "",
                subject=event.subject or "",
                body=event.body or event.snippet or "",
                received_at=event.received_at,
                raw_candidate_urls=tuple(url for url in [event.action_url] if url),
            ),
            source="db_exact",
        )
    return matched


def _old_prediction(row: dict[str, str]) -> tuple[str, str]:
    return normalize_predicted_route(row), normalize_predicted_subtype(row)


def _expected(row: dict[str, str]) -> tuple[str, str]:
    return _clean(row.get("expected_route")), _clean(row.get("expected_subtype"))


def _stored_surface(route: str) -> str:
    if route == "application_inbox":
        return "application_inbox"
    if route == "conversation":
        return "conversation"
    return "not_stored"


async def score_labeled_subset(
    label_path: Path,
    *,
    db_limit: int = 5000,
) -> dict[str, Any]:
    rows = _read_csv(label_path)
    case_ids = {_clean(row.get("case_id")) for row in rows if _clean(row.get("case_id"))}
    db_candidates = await _load_db_candidates(case_ids, db_limit=db_limit)

    case_results: list[dict[str, Any]] = []
    for row in rows:
        case_id = _clean(row.get("case_id"))
        matched = db_candidates.get(case_id) or MatchedCandidate(
            candidate=_redacted_candidate_from_label(row),
            source="redacted_preview",
        )
        analysis = await analyze_email(matched.candidate, ai_enabled=False)
        preflight = evaluate_llm_preflight(matched.candidate, ai_consent=True, thresholds=analysis.thresholds)
        result = analysis.result
        expected_route, expected_subtype = _expected(row)
        old_route, old_subtype = _old_prediction(row)
        old_surface = _stored_surface(old_route)
        new_surface = _stored_surface(result.route)
        expected_surface = _stored_surface(expected_route)
        route_match = result.route == expected_route
        subtype_match = result.subtype == expected_subtype
        full_match = route_match and subtype_match
        surface_match = new_surface == expected_surface
        case_results.append(
            {
                "case_id": case_id,
                "source": matched.source,
                "sender_domain": _clean(row.get("sender_domain")),
                "expected_route": expected_route,
                "expected_subtype": expected_subtype,
                "old_predicted_route": old_route,
                "old_predicted_subtype": old_subtype,
                "old_predicted_classification": _clean(row.get("predicted_classification")),
                "old_predicted_confidence": _clean(row.get("predicted_confidence")),
                "new_predicted_route": result.route,
                "new_predicted_subtype": result.subtype,
                "new_predicted_classification": result.classification,
                "new_confidence": round(float(result.confidence or 0), 4),
                "new_route_confidence": round(float(result.route_confidence or 0), 4),
                "new_subtype_confidence": round(float(result.subtype_confidence or 0), 4),
                "new_decision_path": result.decision_path,
                "new_status_update_allowed": str(result.status_update_allowed).lower(),
                "new_would_call_llm": str(preflight.should_call_llm).lower(),
                "expected_surface": expected_surface,
                "old_surface": old_surface,
                "new_surface": new_surface,
                "route_match": str(route_match).lower(),
                "subtype_match": str(subtype_match).lower(),
                "full_match": str(full_match).lower(),
                "surface_match": str(surface_match).lower(),
                "old_error_bucket": _clean(row.get("error_bucket")),
                "review_notes": _clean(row.get("review_notes")),
                "redacted_subject": _clean(row.get("redacted_subject")),
            }
        )

    return {
        "label_path": str(label_path),
        "case_results": case_results,
        "metrics": _compute_metrics(case_results),
    }


def _compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    old_route_correct = sum(1 for row in rows if row["old_predicted_route"] == row["expected_route"])
    old_subtype_correct = sum(1 for row in rows if row["old_predicted_subtype"] == row["expected_subtype"])
    old_full_correct = sum(
        1
        for row in rows
        if row["old_predicted_route"] == row["expected_route"]
        and row["old_predicted_subtype"] == row["expected_subtype"]
    )
    new_route_correct = sum(1 for row in rows if row["route_match"] == "true")
    new_subtype_correct = sum(1 for row in rows if row["subtype_match"] == "true")
    new_full_correct = sum(1 for row in rows if row["full_match"] == "true")
    old_surface_correct = sum(1 for row in rows if row["old_surface"] == row["expected_surface"])
    new_surface_correct = sum(1 for row in rows if row["surface_match"] == "true")
    source_counts = Counter(row["source"] for row in rows)
    old_route_pairs = Counter((row["old_predicted_route"], row["expected_route"]) for row in rows)
    new_route_pairs = Counter((row["new_predicted_route"], row["expected_route"]) for row in rows)
    new_expected_pairs = Counter((row["new_predicted_route"], row["new_predicted_subtype"]) for row in rows)
    new_would_call_llm = sum(1 for row in rows if row["new_would_call_llm"] == "true")
    old_unwanted_store = sum(
        1
        for row in rows
        if row["expected_surface"] == "not_stored" and row["old_surface"] != "not_stored"
    )
    new_unwanted_store = sum(
        1
        for row in rows
        if row["expected_surface"] == "not_stored" and row["new_surface"] != "not_stored"
    )
    old_missed_store = sum(
        1
        for row in rows
        if row["expected_surface"] != "not_stored" and row["old_surface"] == "not_stored"
    )
    new_missed_store = sum(
        1
        for row in rows
        if row["expected_surface"] != "not_stored" and row["new_surface"] == "not_stored"
    )
    new_high_conf_wrong = sum(
        1
        for row in rows
        if row["full_match"] != "true" and float(row["new_confidence"]) >= 0.8
    )
    opportunity_as_lifecycle = sum(
        1
        for row in rows
        if row["expected_route"] in {"filter", "opportunity_discovery"}
        and row["new_predicted_route"] == "application_inbox"
    )
    marketing_as_conversation = sum(
        1
        for row in rows
        if row["expected_subtype"] == "marketing_promo"
        and row["new_predicted_route"] == "conversation"
    )

    return {
        "row_count": total,
        "source_counts": dict(sorted(source_counts.items())),
        "old_route_accuracy_pct": _pct(old_route_correct, total),
        "new_route_accuracy_pct": _pct(new_route_correct, total),
        "route_accuracy_delta_pct": round(_pct(new_route_correct, total) - _pct(old_route_correct, total), 2),
        "old_subtype_accuracy_pct": _pct(old_subtype_correct, total),
        "new_subtype_accuracy_pct": _pct(new_subtype_correct, total),
        "subtype_accuracy_delta_pct": round(_pct(new_subtype_correct, total) - _pct(old_subtype_correct, total), 2),
        "old_full_accuracy_pct": _pct(old_full_correct, total),
        "new_full_accuracy_pct": _pct(new_full_correct, total),
        "full_accuracy_delta_pct": round(_pct(new_full_correct, total) - _pct(old_full_correct, total), 2),
        "old_surface_accuracy_pct": _pct(old_surface_correct, total),
        "new_surface_accuracy_pct": _pct(new_surface_correct, total),
        "surface_accuracy_delta_pct": round(_pct(new_surface_correct, total) - _pct(old_surface_correct, total), 2),
        "old_unwanted_store_count": old_unwanted_store,
        "new_unwanted_store_count": new_unwanted_store,
        "unwanted_store_delta": new_unwanted_store - old_unwanted_store,
        "old_missed_store_count": old_missed_store,
        "new_missed_store_count": new_missed_store,
        "missed_store_delta": new_missed_store - old_missed_store,
        "new_would_call_llm_count": new_would_call_llm,
        "new_would_call_llm_rate_pct": _pct(new_would_call_llm, total),
        "new_high_confidence_wrong_count": new_high_conf_wrong,
        "new_high_confidence_wrong_rate_pct": _pct(new_high_conf_wrong, total),
        "new_opportunity_or_filter_as_lifecycle_count": opportunity_as_lifecycle,
        "new_marketing_as_conversation_count": marketing_as_conversation,
        "old_top_route_pairs": [
            {"predicted_route": predicted, "expected_route": expected, "count": count}
            for (predicted, expected), count in old_route_pairs.most_common(12)
        ],
        "new_top_route_pairs": [
            {"predicted_route": predicted, "expected_route": expected, "count": count}
            for (predicted, expected), count in new_route_pairs.most_common(12)
        ],
        "new_predicted_route_subtype_counts": [
            {"route": route, "subtype": subtype, "count": count}
            for (route, subtype), count in new_expected_pairs.most_common(20)
        ],
    }


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def render_report(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    return "\n".join(
        [
            "# Gmail Route-First Subset Eval",
            "",
            f"- Label file: `{result['label_path']}`",
            "- Raw email text is not written to this artifact.",
            "",
            "## Summary",
            "",
            _markdown_table(
                ["metric", "value"],
                [
                    ["rows", metrics["row_count"]],
                    ["source counts", json.dumps(metrics["source_counts"], sort_keys=True)],
                    ["old route accuracy", f"{metrics['old_route_accuracy_pct']}%"],
                    ["new route accuracy", f"{metrics['new_route_accuracy_pct']}%"],
                    ["route accuracy delta", f"{metrics['route_accuracy_delta_pct']} pts"],
                    ["old subtype accuracy", f"{metrics['old_subtype_accuracy_pct']}%"],
                    ["new subtype accuracy", f"{metrics['new_subtype_accuracy_pct']}%"],
                    ["subtype accuracy delta", f"{metrics['subtype_accuracy_delta_pct']} pts"],
                    ["old full accuracy", f"{metrics['old_full_accuracy_pct']}%"],
                    ["new full accuracy", f"{metrics['new_full_accuracy_pct']}%"],
                    ["old storage-surface accuracy", f"{metrics['old_surface_accuracy_pct']}%"],
                    ["new storage-surface accuracy", f"{metrics['new_surface_accuracy_pct']}%"],
                    ["storage-surface delta", f"{metrics['surface_accuracy_delta_pct']} pts"],
                    ["old unwanted stored rows", metrics["old_unwanted_store_count"]],
                    ["new unwanted stored rows", metrics["new_unwanted_store_count"]],
                    ["unwanted stored row delta", metrics["unwanted_store_delta"]],
                    ["old missed stored rows", metrics["old_missed_store_count"]],
                    ["new missed stored rows", metrics["new_missed_store_count"]],
                    ["new would-call-LLM rate", f"{metrics['new_would_call_llm_rate_pct']}%"],
                    ["new high-confidence wrong rows", metrics["new_high_confidence_wrong_count"]],
                    ["new opportunity/filter as lifecycle", metrics["new_opportunity_or_filter_as_lifecycle_count"]],
                    ["new marketing as conversation", metrics["new_marketing_as_conversation_count"]],
                ],
            ),
            "",
            "## New Route Pairs",
            "",
            _markdown_table(
                ["predicted_route", "expected_route", "count"],
                [[row["predicted_route"], row["expected_route"], row["count"]] for row in metrics["new_top_route_pairs"]],
            ),
            "",
            "## New Route/Subtype Counts",
            "",
            _markdown_table(
                ["route", "subtype", "count"],
                [[row["route"], row["subtype"], row["count"]] for row in metrics["new_predicted_route_subtype_counts"]],
            ),
            "",
        ]
    )


def write_artifacts(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(json.dumps(result["metrics"], indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(result), encoding="utf-8")
    fieldnames = list(result["case_results"][0].keys()) if result["case_results"] else []
    if fieldnames:
        _write_csv(output_dir / "case_results.csv", result["case_results"], fieldnames)
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-path", type=Path, default=Path(DEFAULT_LABEL_PATH))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--db-limit", type=int, default=5000)
    args = parser.parse_args()

    output_dir = args.output_dir or args.label_path.parent / "route_first_subset_eval"
    result = asyncio.run(score_labeled_subset(args.label_path, db_limit=args.db_limit))
    write_artifacts(result, output_dir)
    print(output_dir)


if __name__ == "__main__":
    main()
