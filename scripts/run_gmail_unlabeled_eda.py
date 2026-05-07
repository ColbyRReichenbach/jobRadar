#!/usr/bin/env python3
"""Create an unlabeled EDA workspace from a Gmail classifier dry-run trace.

This script consumes the redacted ``trace.jsonl`` produced by
``scripts/run_gmail_db_dry_run.py``. It does not read raw Gmail data directly
and does not call an LLM. The output is intended for private data-science
analysis under ``audit/runs``.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "any",
    "are",
    "around",
    "been",
    "before",
    "being",
    "but",
    "can",
    "com",
    "could",
    "did",
    "does",
    "for",
    "from",
    "get",
    "had",
    "has",
    "have",
    "here",
    "how",
    "into",
    "its",
    "just",
    "like",
    "may",
    "more",
    "not",
    "now",
    "our",
    "out",
    "over",
    "see",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "they",
    "this",
    "through",
    "to",
    "use",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "you",
    "your",
}

PATTERNS: dict[str, re.Pattern[str]] = {
    "apply_language": re.compile(r"\b(apply|applied|application|applications|submit|submitted|resume|candidate)\b", re.I),
    "job_alert_language": re.compile(r"\b(job alert|jobs for you|recommended|opportunities|new jobs|hiring|roles?|open positions?|position)\b", re.I),
    "interview_language": re.compile(r"\b(interview|screening|phone screen|onsite|on-site|availability|schedule|reschedule|zoom|meet)\b", re.I),
    "scheduler_language": re.compile(r"\b(calendly|schedule a time|book a time|availability|calendar|reschedule)\b", re.I),
    "recruiter_language": re.compile(r"\b(recruiter|sourcer|talent|hiring manager|connect|connection|network|message)\b", re.I),
    "marketing_language": re.compile(r"\b(sale|deal|discount|newsletter|subscribe|unsubscribe|promo|rewards|offer expires)\b", re.I),
    "finance_noise_language": re.compile(r"\b(account|statement|payment|loan|credit|mortgage|bank|balance)\b", re.I),
    "system_noise_language": re.compile(r"\b(security alert|verification code|password|sign in|login|receipt)\b", re.I),
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and fieldnames is None:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _clean(value: object) -> str:
    return str(value or "").strip()


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)) * 100, 2) if denominator else 0.0


def _case_text(case: dict[str, Any]) -> str:
    preview = case.get("redacted_email_preview") or {}
    return f"{preview.get('subject') or ''} {preview.get('body_preview') or ''}"


def _tokens(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-z][a-z0-9_'-]{2,}", text.lower())
    return [token.strip("'") for token in raw_tokens if token not in STOPWORDS and not token.startswith("redacted")]


def _terms(text: str) -> set[str]:
    tokens = _tokens(text)
    bigrams = [f"{left} {right}" for left, right in zip(tokens, tokens[1:])]
    return set(tokens + bigrams)


def _domain_family(domain: str) -> str:
    normalized = domain.lower()
    if "handshake" in normalized:
        return "handshake"
    if any(token in normalized for token in ["linkedin", "glassdoor", "indeed", "ziprecruiter", "monster"]):
        return "job_board"
    if any(token in normalized for token in ["greenhouse", "lever", "workday", "successfactors", "smartrecruiters"]):
        return "ats"
    if any(token in normalized for token in ["gmail", "outlook", "yahoo", "icloud"]):
        return "personal_email"
    if any(token in normalized for token in ["bank", "wellsfargo", "salliemae", "lendingtree", "capitalone", "bofa"]):
        return "finance"
    if any(token in normalized for token in ["target", "walmart", "lowes", "foodlion", "chick-fil-a", "carvana"]):
        return "retail_marketing"
    if not normalized:
        return "unknown"
    return "other"


def _surface(route: str) -> str:
    if route == "application_inbox":
        return "application_inbox"
    if route == "conversation":
        return "conversation"
    return "not_stored"


def _hybrid(case: dict[str, Any], key: str, default: object = "") -> Any:
    return (case.get("hybrid") or {}).get(key, default)


def _scores(case: dict[str, Any]) -> dict[str, Any]:
    return (case.get("hybrid") or {}).get("scores") or {}


def _matched_features(case: dict[str, Any]) -> list[str]:
    features = _hybrid(case, "matched_features", [])
    if isinstance(features, list):
        return [_clean(item) for item in features if _clean(item)]
    return [_clean(item) for item in str(features or "").split(";") if _clean(item)]


def _active_patterns(case: dict[str, Any]) -> list[str]:
    text = _case_text(case)
    features = " ".join(_matched_features(case))
    combined = f"{text} {features}"
    return [name for name, pattern in PATTERNS.items() if pattern.search(combined)]


def _counter_rows(counter: Counter[str], *, key_name: str, limit: int | None = None) -> list[dict[str, Any]]:
    rows = [{"count": count, key_name: key} for key, count in counter.most_common(limit)]
    return rows


def _term_lift(cases: list[dict[str, Any]], group_fn: Callable[[dict[str, Any]], str], *, limit_per_group: int = 12) -> list[dict[str, Any]]:
    total_docs = len(cases)
    term_docs: Counter[str] = Counter()
    group_docs: Counter[str] = Counter()
    group_term_docs: Counter[tuple[str, str]] = Counter()
    for case in cases:
        group = group_fn(case)
        if not group:
            continue
        terms = _terms(_case_text(case))
        group_docs[group] += 1
        term_docs.update(terms)
        for term in terms:
            group_term_docs[(group, term)] += 1

    output: list[dict[str, Any]] = []
    for group, doc_count in group_docs.items():
        candidates: list[dict[str, Any]] = []
        for (candidate_group, term), count in group_term_docs.items():
            if candidate_group != group or count < 2:
                continue
            in_group_rate = count / doc_count
            out_group_docs = max(total_docs - doc_count, 1)
            out_group_count = max(term_docs[term] - count, 0)
            out_group_rate = out_group_count / out_group_docs
            lift = (in_group_rate + 0.01) / (out_group_rate + 0.01)
            candidates.append(
                {
                    "group": group,
                    "term": term,
                    "group_count": count,
                    "group_rate_pct": _pct(count, doc_count),
                    "overall_count": term_docs[term],
                    "lift": round(lift, 3),
                }
            )
        candidates.sort(key=lambda item: (item["lift"], item["group_count"]), reverse=True)
        output.extend(candidates[:limit_per_group])
    return output


def _feature_lift(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_docs: Counter[str] = Counter()
    feature_docs: Counter[str] = Counter()
    route_feature_docs: Counter[tuple[str, str]] = Counter()
    for case in cases:
        route = _clean(_hybrid(case, "route"))
        features = set(_matched_features(case))
        route_docs[route] += 1
        feature_docs.update(features)
        for feature in features:
            route_feature_docs[(route, feature)] += 1

    output: list[dict[str, Any]] = []
    total = len(cases)
    for (route, feature), count in route_feature_docs.items():
        if count < 2:
            continue
        route_count = route_docs[route]
        in_rate = count / route_count if route_count else 0.0
        out_docs = max(total - route_count, 1)
        out_count = max(feature_docs[feature] - count, 0)
        out_rate = out_count / out_docs
        output.append(
            {
                "route": route,
                "matched_feature": feature,
                "route_count": count,
                "route_rate_pct": _pct(count, route_count),
                "overall_count": feature_docs[feature],
                "lift": round((in_rate + 0.01) / (out_rate + 0.01), 3),
            }
        )
    output.sort(key=lambda item: (item["lift"], item["route_count"]), reverse=True)
    return output[:120]


def _svg_bar_chart(
    title: str,
    rows: list[tuple[str, float]],
    *,
    value_suffix: str = "",
    width: int = 980,
    row_height: int = 34,
    left_margin: int = 390,
    fill: str = "#2563eb",
) -> str:
    rows = [(str(label), float(value)) for label, value in rows]
    height = max(120, 70 + row_height * len(rows))
    max_value = max((value for _, value in rows), default=0.0)
    chart_width = width - left_margin - 90
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="34" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">{html.escape(title)}</text>',
    ]
    for index, (label, value) in enumerate(rows):
        y = 62 + index * row_height
        bar_width = 0 if max_value <= 0 else round((value / max_value) * chart_width, 2)
        parts.extend(
            [
                f'<text x="24" y="{y + 18}" font-family="Arial, sans-serif" font-size="13" fill="#374151">{html.escape(label[:62])}</text>',
                f'<rect x="{left_margin}" y="{y}" width="{chart_width}" height="20" rx="3" fill="#f3f4f6"/>',
                f'<rect x="{left_margin}" y="{y}" width="{bar_width}" height="20" rx="3" fill="{fill}"/>',
                f'<text x="{left_margin + bar_width + 8}" y="{y + 15}" font-family="Arial, sans-serif" font-size="12" fill="#111827">{value:g}{html.escape(value_suffix)}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


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


def _route_subtype_key(case: dict[str, Any]) -> str:
    return f"{_hybrid(case, 'route')} / {_hybrid(case, 'subtype')}"


def _route_domain_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for case in cases:
        route = _clean(_hybrid(case, "route"))
        domain = _clean(case.get("sender_domain")) or "unknown"
        family = _domain_family(domain)
        counter[(route, family, domain)] += 1
    return [
        {"route": route, "domain_family": family, "sender_domain": domain, "count": count}
        for (route, family, domain), count in counter.most_common(120)
    ]


def _review_candidate_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        route = _clean(_hybrid(case, "route"))
        subtype = _clean(_hybrid(case, "subtype"))
        preflight = case.get("preflight") or {}
        scores = _scores(case)
        if not (preflight.get("would_call_llm") or route == "action_review" or _clean(_hybrid(case, "confidence_band")) != "high"):
            continue
        preview = case.get("redacted_email_preview") or {}
        rows.append(
            {
                "event_ref": case.get("event_ref"),
                "sender_domain": case.get("sender_domain") or "unknown",
                "route": route,
                "subtype": subtype,
                "confidence": _hybrid(case, "confidence"),
                "route_margin": scores.get("route_margin"),
                "subtype_margin": scores.get("subtype_margin"),
                "would_call_llm": str(bool(preflight.get("would_call_llm"))).lower(),
                "review_reasons": ";".join(case.get("review_reasons") or []),
                "subject": preview.get("subject") or "",
            }
        )
    rows.sort(key=lambda row: (row["would_call_llm"] != "true", str(row["route"]), -float(row["confidence"] or 0)))
    return rows[:200]


def _label_bucket(case: dict[str, Any]) -> str:
    route = _clean(_hybrid(case, "route"))
    subtype = _clean(_hybrid(case, "subtype"))
    preflight = case.get("preflight") or {}
    if route == "action_review" or preflight.get("would_call_llm"):
        return "action_review_or_llm"
    if route == "application_inbox":
        return "application_inbox"
    if route == "conversation":
        return "conversation"
    if route == "filter" and subtype in {"job_alert", "job_board_promo"}:
        return "filter_job_alert"
    if route == "opportunity_discovery":
        return "opportunity_discovery_review"
    return "filter_other"


def _targeted_label_row(case: dict[str, Any]) -> dict[str, Any]:
    scores = _scores(case)
    preflight = case.get("preflight") or {}
    preview = case.get("redacted_email_preview") or {}
    bucket = _label_bucket(case)
    return {
        "case_id": case.get("event_ref") or "",
        "label_bucket": bucket,
        "received_at": case.get("received_at") or "",
        "sender_domain": case.get("sender_domain") or "",
        "predicted_route": _clean(_hybrid(case, "route")),
        "predicted_subtype": _clean(_hybrid(case, "subtype")),
        "predicted_classification": _clean(_hybrid(case, "classification")),
        "predicted_confidence": _hybrid(case, "confidence"),
        "confidence_band": _clean(_hybrid(case, "confidence_band")),
        "decision_path": _clean(_hybrid(case, "decision_path")),
        "route_confidence": _hybrid(case, "route_confidence"),
        "subtype_confidence": _hybrid(case, "subtype_confidence"),
        "route_margin": scores.get("route_margin"),
        "subtype_margin": scores.get("subtype_margin"),
        "job_signal_score": scores.get("job_signal_score"),
        "noise_score": scores.get("noise_score"),
        "would_call_llm": str(bool(preflight.get("would_call_llm"))).lower(),
        "prompt_leak_count": len(preflight.get("leak_findings") or []),
        "matched_features": ";".join(_matched_features(case)),
        "ambiguity_reasons": ";".join(_hybrid(case, "ambiguity_reasons", []) or []),
        "review_reasons": ";".join(case.get("review_reasons") or []),
        "redacted_subject": preview.get("subject") or "",
        "redacted_body_preview": " ".join(str(preview.get("body_preview") or "").split())[:1200],
        "expected_route": "",
        "expected_subtype": "",
        "is_correct": "",
        "error_bucket": "",
        "review_notes": "",
    }


def _label_priority(case: dict[str, Any]) -> tuple[int, float]:
    bucket = _label_bucket(case)
    scores = _scores(case)
    route_margin = float(scores.get("route_margin") or 0)
    confidence = float(_hybrid(case, "confidence", 0) or 0)
    preflight = case.get("preflight") or {}
    base = {
        "action_review_or_llm": 100,
        "application_inbox": 90,
        "conversation": 80,
        "filter_job_alert": 70,
        "opportunity_discovery_review": 60,
        "filter_other": 30,
    }.get(bucket, 10)
    if preflight.get("would_call_llm"):
        base += 15
    if _clean(_hybrid(case, "confidence_band")) != "high":
        base += 10
    if case.get("review_reasons"):
        base += 5
    return base, round(1.0 - route_margin + confidence, 4)


def _targeted_label_queue(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bucket_limits = {
        "action_review_or_llm": 60,
        "application_inbox": 35,
        "conversation": 35,
        "filter_job_alert": 35,
        "opportunity_discovery_review": 15,
        "filter_other": 20,
    }
    bucket_order = [
        "action_review_or_llm",
        "application_inbox",
        "conversation",
        "filter_job_alert",
        "opportunity_discovery_review",
        "filter_other",
    ]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str, str]] = set()
    for case in cases:
        row = _targeted_label_row(case)
        key = (
            row["label_bucket"],
            row["sender_domain"],
            row["predicted_route"],
            row["redacted_subject"].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        row["_priority"] = _label_priority(case)
        buckets[row["label_bucket"]].append(row)

    selected: list[dict[str, Any]] = []
    for bucket in bucket_order:
        rows = sorted(buckets.get(bucket, []), key=lambda row: row["_priority"], reverse=True)
        selected.extend(rows[: bucket_limits[bucket]])
    for row in selected:
        row.pop("_priority", None)
    return selected


def _examples(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[_route_subtype_key(case)].append(case)

    examples: list[dict[str, Any]] = []
    for group, items in sorted(grouped.items(), key=lambda pair: len(pair[1]), reverse=True):
        selected = sorted(
            items,
            key=lambda case: (
                not bool((case.get("preflight") or {}).get("would_call_llm")),
                _clean(_hybrid(case, "confidence_band")) == "high",
                -float(_hybrid(case, "confidence", 0) or 0),
            ),
        )[:3]
        for case in selected:
            preview = case.get("redacted_email_preview") or {}
            examples.append(
                {
                    "group": group,
                    "event_ref": case.get("event_ref"),
                    "sender_domain": case.get("sender_domain") or "unknown",
                    "confidence": _hybrid(case, "confidence"),
                    "decision_path": _hybrid(case, "decision_path"),
                    "would_call_llm": str(bool((case.get("preflight") or {}).get("would_call_llm"))).lower(),
                    "review_reasons": ";".join(case.get("review_reasons") or []),
                    "subject": preview.get("subject") or "",
                    "body_preview": preview.get("body_preview") or "",
                }
            )
    return examples


def compute_unlabeled_eda(trace_path: Path) -> dict[str, Any]:
    cases = _read_jsonl(trace_path)
    route_counts = Counter(_clean(_hybrid(case, "route")) for case in cases)
    subtype_counts = Counter(_clean(_hybrid(case, "subtype")) for case in cases)
    route_subtype_counts = Counter(_route_subtype_key(case) for case in cases)
    decision_path_counts = Counter(_clean(_hybrid(case, "decision_path")) for case in cases)
    confidence_band_counts = Counter(_clean(_hybrid(case, "confidence_band")) for case in cases)
    domain_family_counts = Counter(_domain_family(_clean(case.get("sender_domain"))) for case in cases)
    existing_surface_counts = Counter(_surface(_clean((case.get("existing") or {}).get("route"))) for case in cases)
    hybrid_surface_counts = Counter(_surface(_clean(_hybrid(case, "route"))) for case in cases)
    review_reasons: Counter[str] = Counter()
    pattern_counts: Counter[str] = Counter()
    route_pattern_counts: Counter[tuple[str, str]] = Counter()
    for case in cases:
        review_reasons.update(case.get("review_reasons") or [])
        patterns = _active_patterns(case)
        pattern_counts.update(patterns)
        route = _clean(_hybrid(case, "route"))
        for pattern in patterns:
            route_pattern_counts[(route, pattern)] += 1

    would_call_count = sum(1 for case in cases if (case.get("preflight") or {}).get("would_call_llm"))
    blocked_count = sum(1 for case in cases if (case.get("preflight") or {}).get("blocked"))
    leak_count = sum(1 for case in cases if (case.get("preflight") or {}).get("leak_findings"))
    route_change_count = sum(
        1 for case in cases if _clean((case.get("existing") or {}).get("route")) != _clean(_hybrid(case, "route"))
    )
    confidence_low_or_medium = sum(1 for case in cases if _clean(_hybrid(case, "confidence_band")) != "high")

    would_call_by_route = Counter(
        _clean(_hybrid(case, "route")) for case in cases if (case.get("preflight") or {}).get("would_call_llm")
    )
    action_review_by_domain = Counter(
        _clean(case.get("sender_domain")) or "unknown"
        for case in cases
        if _clean(_hybrid(case, "route")) == "action_review"
    )
    filter_job_alert_count = sum(
        1
        for case in cases
        if _clean(_hybrid(case, "route")) == "filter"
        and _clean(_hybrid(case, "subtype")) in {"job_alert", "job_board_promo"}
    )

    pattern_rows = [
        {
            "pattern": pattern,
            "matched_rows": count,
            "matched_rate_pct": _pct(count, len(cases)),
            "top_route": Counter(
                route for (route, item_pattern), route_count in route_pattern_counts.items() for _ in range(route_count) if item_pattern == pattern
            ).most_common(1)[0][0],
        }
        for pattern, count in pattern_counts.most_common()
    ]

    return {
        "trace_path": str(trace_path),
        "case_count": len(cases),
        "summary": {
            "case_count": len(cases),
            "would_call_llm_count": would_call_count,
            "would_call_llm_rate_pct": _pct(would_call_count, len(cases)),
            "preflight_blocked_count": blocked_count,
            "preflight_blocked_rate_pct": _pct(blocked_count, len(cases)),
            "prompt_leak_count": leak_count,
            "prompt_leak_rate_pct": _pct(leak_count, len(cases)),
            "route_change_count": route_change_count,
            "route_change_rate_pct": _pct(route_change_count, len(cases)),
            "low_or_medium_confidence_count": confidence_low_or_medium,
            "low_or_medium_confidence_rate_pct": _pct(confidence_low_or_medium, len(cases)),
            "filter_job_alert_or_promo_count": filter_job_alert_count,
            "model_call_count": 0,
        },
        "route_counts": _counter_rows(route_counts, key_name="route"),
        "subtype_counts": _counter_rows(subtype_counts, key_name="subtype", limit=30),
        "route_subtype_counts": _counter_rows(route_subtype_counts, key_name="route_subtype", limit=40),
        "decision_path_counts": _counter_rows(decision_path_counts, key_name="decision_path"),
        "confidence_band_counts": _counter_rows(confidence_band_counts, key_name="confidence_band"),
        "domain_family_counts": _counter_rows(domain_family_counts, key_name="domain_family"),
        "existing_surface_counts": _counter_rows(existing_surface_counts, key_name="surface"),
        "hybrid_surface_counts": _counter_rows(hybrid_surface_counts, key_name="surface"),
        "review_reason_counts": _counter_rows(review_reasons, key_name="review_reason", limit=30),
        "would_call_by_route": _counter_rows(would_call_by_route, key_name="route"),
        "action_review_by_domain": _counter_rows(action_review_by_domain, key_name="sender_domain", limit=30),
        "pattern_diagnostics": pattern_rows,
        "route_domain_summary": _route_domain_rows(cases),
        "route_ngram_lift": _term_lift(cases, lambda case: _clean(_hybrid(case, "route"))),
        "route_subtype_ngram_lift": _term_lift(cases, _route_subtype_key, limit_per_group=8),
        "feature_route_lift": _feature_lift(cases),
        "review_candidates": _review_candidate_rows(cases),
        "targeted_label_queue": _targeted_label_queue(cases),
        "examples": _examples(cases),
    }


def render_report(metrics: dict[str, Any]) -> str:
    summary = metrics["summary"]
    return "\n".join(
        [
            "# Gmail Classifier Unlabeled EDA",
            "",
            f"- Trace file: `{metrics['trace_path']}`",
            "- Source: DB dry-run trace over stored `email_events`.",
            "- Raw Gmail text is not read by this report. Examples use the dry-run redacted preview fields and should remain under `audit/runs`.",
            "- This is unlabeled EDA, so it does not claim model accuracy. It measures distribution, routing volume, LLM-escalation candidates, and likely labeling targets.",
            "",
            "## Summary",
            "",
            _markdown_table(
                ["metric", "value"],
                [
                    ["cases", summary["case_count"]],
                    ["would call LLM", f"{summary['would_call_llm_count']} ({summary['would_call_llm_rate_pct']}%)"],
                    ["preflight blocked", f"{summary['preflight_blocked_count']} ({summary['preflight_blocked_rate_pct']}%)"],
                    ["prompt leaks detected", f"{summary['prompt_leak_count']} ({summary['prompt_leak_rate_pct']}%)"],
                    ["route changed versus stored classifier", f"{summary['route_change_count']} ({summary['route_change_rate_pct']}%)"],
                    ["low/medium confidence", f"{summary['low_or_medium_confidence_count']} ({summary['low_or_medium_confidence_rate_pct']}%)"],
                    ["filtered job-alert/promo rows", summary["filter_job_alert_or_promo_count"]],
                    ["model calls", summary["model_call_count"]],
                ],
            ),
            "",
            "## Predicted Route Distribution",
            "",
            _markdown_table(["route", "count"], [[row["route"], row["count"]] for row in metrics["route_counts"]]),
            "",
            "## Predicted Subtype Distribution",
            "",
            _markdown_table(["subtype", "count"], [[row["subtype"], row["count"]] for row in metrics["subtype_counts"][:20]]),
            "",
            "## Route/Subtype Pairs",
            "",
            _markdown_table(
                ["route/subtype", "count"],
                [[row["route_subtype"], row["count"]] for row in metrics["route_subtype_counts"][:20]],
            ),
            "",
            "## Review Targets",
            "",
            _markdown_table(
                ["review reason", "count"],
                [[row["review_reason"], row["count"]] for row in metrics["review_reason_counts"][:20]],
            ),
            "",
            "## Pattern Diagnostics",
            "",
            _markdown_table(
                ["pattern", "matched", "matched rate", "top route"],
                [
                    [row["pattern"], row["matched_rows"], f"{row['matched_rate_pct']}%", row["top_route"]]
                    for row in metrics["pattern_diagnostics"][:20]
                ],
            ),
            "",
            "## Top Route N-Gram Lift",
            "",
            _markdown_table(
                ["route", "term", "count", "route rate", "lift"],
                [
                    [row["group"], row["term"], row["group_count"], f"{row['group_rate_pct']}%", row["lift"]]
                    for row in metrics["route_ngram_lift"][:28]
                ],
            ),
            "",
            "## What This Tells Us",
            "",
            "1. Use this run to select the next human-labeling batch, not to declare correctness.",
            "2. If `filter / job_alert` is large, that confirms the product policy change is actively keeping job-board recommendations out of AppTrail workflows.",
            "3. If `action_review` or `would_call_llm` volume is high, label those rows before adding more rules.",
            "4. N-gram and matched-feature lift show which words/rules dominate each predicted route; they are diagnostics, not calibrated probabilities.",
            "",
            "## Next Labeling Move",
            "",
            "Sample from four buckets: `application_inbox`, `conversation`, `filter / job_alert`, and `action_review` or would-call-LLM cases. "
            "That gives enough coverage to judge whether the routing policy is improving precision without hiding real application lifecycle emails.",
            "",
        ]
    )


def render_examples(metrics: dict[str, Any]) -> str:
    lines = [
        "# Redacted Unlabeled Examples By Predicted Route",
        "",
        "Private redacted examples. These are for qualitative inspection and should remain under `audit/runs`.",
        "",
    ]
    for example in metrics["examples"]:
        lines.extend(
            [
                f"## {example['group']} / {example['event_ref']}",
                "",
                f"- sender_domain: `{example['sender_domain']}`",
                f"- confidence: `{example['confidence']}`",
                f"- decision_path: `{example['decision_path']}`",
                f"- would_call_llm: `{example['would_call_llm']}`",
                f"- review_reasons: `{example['review_reasons']}`",
                "",
                "```text",
                f"Subject: {example['subject']}",
                "",
                str(example["body_preview"] or ""),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_notebook(trace_path: Path, output_dir: Path, metrics: dict[str, Any], report: str) -> dict[str, Any]:
    setup = f"""from pathlib import Path
import json
from pprint import pprint

TRACE_PATH = Path({str(trace_path.resolve())!r})
EDA_DIR = Path({str(output_dir.resolve())!r})

if not TRACE_PATH.exists():
    raise FileNotFoundError(f"Trace file not found: {{TRACE_PATH}}")
if not (EDA_DIR / 'unlabeled_eda_metrics.json').exists():
    raise FileNotFoundError(f"Metrics file not found: {{EDA_DIR / 'unlabeled_eda_metrics.json'}}")

metrics = json.loads((EDA_DIR / 'unlabeled_eda_metrics.json').read_text(encoding='utf-8'))
print("Summary")
pprint(metrics['summary'])
"""
    inspect = f"""from pathlib import Path
import json
from pprint import pprint

EDA_DIR = Path({str(output_dir.resolve())!r})
metrics = json.loads((EDA_DIR / 'unlabeled_eda_metrics.json').read_text(encoding='utf-8'))

print("Route/subtype distribution")
pprint(metrics['route_subtype_counts'][:20])

print("\\nWould-call-LLM by route")
pprint(metrics['would_call_by_route'])
"""
    terms = f"""from pathlib import Path
import json
from pprint import pprint

EDA_DIR = Path({str(output_dir.resolve())!r})
metrics = json.loads((EDA_DIR / 'unlabeled_eda_metrics.json').read_text(encoding='utf-8'))

print("Top route n-gram lift")
pprint(metrics['route_ngram_lift'][:30])
"""
    return {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Gmail Unlabeled Classifier EDA\n\n", "Generated from a redacted DB dry-run trace.\n"]},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": setup.splitlines(keepends=True)},
            {"cell_type": "markdown", "metadata": {}, "source": report.splitlines(keepends=True)},
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "## Charts\n\n",
                    "![Route distribution](charts/route_distribution.svg)\n\n",
                    "![Route subtype distribution](charts/route_subtype_distribution.svg)\n\n",
                    "![Would-call-LLM by route](charts/would_call_by_route.svg)\n",
                ],
            },
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": inspect.splitlines(keepends=True)},
            {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": terms.splitlines(keepends=True)},
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def write_artifacts(trace_path: Path, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or trace_path.parent / "unlabeled_eda"
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = compute_unlabeled_eda(trace_path)
    report = render_report(metrics)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(exist_ok=True)

    _write_csv(output_dir / "route_domain_summary.csv", metrics["route_domain_summary"])
    _write_csv(output_dir / "route_ngram_lift.csv", metrics["route_ngram_lift"])
    _write_csv(output_dir / "route_subtype_ngram_lift.csv", metrics["route_subtype_ngram_lift"])
    _write_csv(output_dir / "feature_route_lift.csv", metrics["feature_route_lift"])
    _write_csv(output_dir / "review_candidates.csv", metrics["review_candidates"])
    _write_csv(output_dir / "targeted_label_queue.csv", metrics["targeted_label_queue"])
    _write_csv(output_dir / "pattern_diagnostics.csv", metrics["pattern_diagnostics"])

    charts = {
        "route_distribution.svg": _svg_bar_chart(
            "Predicted route distribution",
            [(row["route"], row["count"]) for row in metrics["route_counts"]],
            fill="#2563eb",
        ),
        "subtype_distribution.svg": _svg_bar_chart(
            "Predicted subtype distribution",
            [(row["subtype"], row["count"]) for row in metrics["subtype_counts"][:18]],
            fill="#7c3aed",
        ),
        "route_subtype_distribution.svg": _svg_bar_chart(
            "Predicted route/subtype distribution",
            [(row["route_subtype"], row["count"]) for row in metrics["route_subtype_counts"][:18]],
            fill="#0f766e",
        ),
        "decision_paths.svg": _svg_bar_chart(
            "Decision paths",
            [(row["decision_path"], row["count"]) for row in metrics["decision_path_counts"]],
            fill="#ea580c",
        ),
        "domain_families.svg": _svg_bar_chart(
            "Sender domain families",
            [(row["domain_family"], row["count"]) for row in metrics["domain_family_counts"]],
            fill="#4f46e5",
        ),
        "would_call_by_route.svg": _svg_bar_chart(
            "Would-call-LLM by route",
            [(row["route"], row["count"]) for row in metrics["would_call_by_route"]],
            fill="#dc2626",
        ),
    }
    for filename, content in charts.items():
        (charts_dir / filename).write_text(content, encoding="utf-8")

    (output_dir / "charts.md").write_text(
        "\n".join(
            [
                "# Gmail Unlabeled EDA Charts",
                "",
                *[
                    f"## {filename.removesuffix('.svg').replace('_', ' ').title()}\n\n![{filename}](charts/{filename})\n"
                    for filename in charts
                ],
            ]
        ),
        encoding="utf-8",
    )
    (output_dir / "unlabeled_eda_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "unlabeled_eda_report.md").write_text(report, encoding="utf-8")
    (output_dir / "redacted_examples_by_route.md").write_text(render_examples(metrics), encoding="utf-8")
    (output_dir / "targeted_labeling_guidelines.md").write_text(
        "# Targeted Gmail Labeling Queue\n\n"
        "Fill `expected_route`, `expected_subtype`, `is_correct`, `error_bucket`, and `review_notes` in "
        "`targeted_label_queue.csv`.\n\n"
        "Use this queue before labeling the full stored set. It is balanced across the current decision risks: "
        "`action_review_or_llm`, `application_inbox`, `conversation`, `filter_job_alert`, "
        "`opportunity_discovery_review`, and `filter_other`.\n\n"
        "Current product policy: job-board recommendations usually should be `expected_route=filter` with "
        "`expected_subtype=job_alert` or `job_board_promo`, unless the message clearly belongs to an active "
        "application/candidate process.\n",
        encoding="utf-8",
    )
    (output_dir / "gmail_unlabeled_eda_workspace.ipynb").write_text(
        json.dumps(render_notebook(trace_path, output_dir, metrics, report), indent=2),
        encoding="utf-8",
    )
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = write_artifacts(args.trace_path, args.output_dir)
    print(output_dir)


if __name__ == "__main__":
    main()
