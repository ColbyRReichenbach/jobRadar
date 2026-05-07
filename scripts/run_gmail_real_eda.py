#!/usr/bin/env python3
"""Generate private real-data Gmail classifier EDA artifacts.

The input is a local ``audit/runs/gmail_combined_real_baseline*`` folder
generated from Gmail sync audit rows and redacted DB dry-run artifacts. The
output is written under ``<run-dir>/eda`` so real-email-derived artifacts stay
inside ``audit/runs`` and remain ignored by git.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUN_GLOB = "audit/runs/gmail_combined_real_baseline*"
OPPORTUNITY_DISCOVERY_DOMAIN_HINTS = (
    "handshake",
    "joinhandshake",
    "indeed",
    "linkedin",
    "glassdoor",
    "ziprecruiter",
)
OPPORTUNITY_DISCOVERY_CLASSIFICATIONS = {"conversation", "interview_request", "action_item"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _int(value: object) -> int:
    try:
        return int(float(str(value or "0")))
    except ValueError:
        return 0


def _float(value: object) -> float:
    try:
        return float(str(value or "0"))
    except ValueError:
        return 0.0


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)) * 100, 2) if denominator else 0.0


def _latest_run_dir(pattern: str = DEFAULT_RUN_GLOB) -> Path:
    candidates = [path for path in Path(".").glob(pattern) if path.is_dir()]
    if not candidates:
        raise SystemExit(f"No run directories found for {pattern!r}.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


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


def _ascii_bar(value: int, max_value: int, width: int = 24) -> str:
    if max_value <= 0:
        return ""
    filled = max(1, round((value / max_value) * width)) if value else 0
    return "#" * filled + "." * (width - filled)


def _domain_is_opportunity_discovery(domain: str) -> bool:
    normalized = (domain or "").lower()
    return any(hint in normalized for hint in OPPORTUNITY_DISCOVERY_DOMAIN_HINTS)


def _stored_classification_rows(stored_summary: list[dict[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in stored_summary:
        counts[row.get("classification") or "unknown"] += _int(row.get("event_count"))
    return counts


def _sync_bin_rows(decision_summary: list[dict[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in decision_summary:
        decision = row.get("decision") or "unknown"
        reason = row.get("reason") or "unknown"
        classification = row.get("classification") or ""
        if decision == "stored":
            key = f"stored:{classification or 'unknown'}"
        elif decision == "filtered":
            key = f"filtered:{classification or reason}"
        else:
            key = f"{decision}:{reason}"
        counts[key] += _int(row.get("message_count"))
    return counts


def _top_rows(rows: list[dict[str, str]], count_key: str, limit: int = 12) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: _int(row.get(count_key)), reverse=True)[:limit]


def _event_summary_dirs(run_dir: Path) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for summary_path in sorted(run_dir.glob("events_*/summary.json")):
        summaries[summary_path.parent.name.replace("events_", "")] = _read_json(summary_path)
    return summaries


def _load_trace_rows(run_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for trace_path in sorted(run_dir.glob("events_*/trace.jsonl")):
        account_label = trace_path.parent.name.replace("events_", "")
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append((account_label, json.loads(line)))
    return rows


def _trace_value(case: dict[str, Any], *path: str) -> Any:
    value: Any = case
    for item in path:
        if not isinstance(value, dict):
            return None
        value = value.get(item)
    return value


def _confidence_bucket(value: object) -> str:
    score = _float(value)
    if score < 0.5:
        return "0.00-0.49"
    if score < 0.7:
        return "0.50-0.69"
    if score < 0.9:
        return "0.70-0.89"
    return "0.90-1.00"


def _trace_confidence_metrics(run_dir: Path) -> dict[str, Any]:
    confidence_by_class: Counter[tuple[str, str]] = Counter()
    confidence_exact_by_class: Counter[tuple[str, str]] = Counter()
    feature_counts: Counter[str] = Counter()
    overconfident_interview_without_scheduler: Counter[tuple[str, str]] = Counter()
    redacted_examples: list[dict[str, Any]] = []

    for account_label, case in _load_trace_rows(run_dir):
        existing = case.get("existing") or {}
        hybrid = case.get("hybrid") or {}
        preview = case.get("redacted_email_preview") or {}
        classification = str(existing.get("classification") or hybrid.get("classification") or "unknown")
        confidence = existing.get("confidence") if existing.get("confidence") is not None else hybrid.get("confidence")
        confidence_str = f"{_float(confidence):.2f}"
        confidence_by_class[(classification, _confidence_bucket(confidence))] += 1
        confidence_exact_by_class[(classification, confidence_str)] += 1

        matched_features = [str(feature) for feature in hybrid.get("matched_features") or []]
        feature_counts.update(matched_features)

        sender_domain = str(case.get("sender_domain") or "unknown")
        if (
            classification == "interview_request"
            and _float(confidence) >= 0.8
            and not any("scheduler" in feature for feature in matched_features)
        ):
            feature_key = next((feature for feature in matched_features if feature.startswith("interview_request_phrase:")), "no_scheduler_signal")
            overconfident_interview_without_scheduler[(sender_domain, feature_key)] += 1

        if _domain_is_opportunity_discovery(sender_domain) and classification in OPPORTUNITY_DISCOVERY_CLASSIFICATIONS:
            redacted_examples.append(
                {
                    "account_label": account_label,
                    "case_id": case.get("event_ref"),
                    "sender_domain": sender_domain,
                    "predicted_classification": classification,
                    "predicted_route": existing.get("route") or hybrid.get("route"),
                    "confidence": confidence_str,
                    "matched_features": matched_features,
                    "subject": preview.get("subject") or "",
                    "body_preview": preview.get("body_preview") or "",
                }
            )

    return {
        "confidence_bucket_by_classification": [
            {"classification": classification, "confidence_bucket": bucket, "count": count}
            for (classification, bucket), count in confidence_by_class.most_common()
        ],
        "confidence_exact_by_classification": [
            {"classification": classification, "confidence": confidence, "count": count}
            for (classification, confidence), count in confidence_exact_by_class.most_common()
        ],
        "top_matched_features": [
            {"feature": feature, "count": count}
            for feature, count in feature_counts.most_common(25)
        ],
        "overconfident_interview_without_scheduler": [
            {"sender_domain": sender_domain, "feature": feature, "count": count}
            for (sender_domain, feature), count in overconfident_interview_without_scheduler.most_common(20)
        ],
        "redacted_examples": redacted_examples[:20],
    }


def compute_metrics(run_dir: Path) -> dict[str, Any]:
    account_summary = _read_csv(run_dir / "sync_account_summary.csv")
    decision_summary = _read_csv(run_dir / "sync_decision_summary.csv")
    sync_domain_summary = _read_csv(_first_existing(run_dir, "sync_domain_summary_top300.csv", "sync_domain_summary_top250.csv"))
    stored_summary = _read_csv(run_dir / "stored_event_summary.csv")
    stored_domain_summary = _read_csv(
        _first_existing(run_dir, "stored_event_domain_summary_top300.csv", "stored_event_domain_summary_top250.csv")
    )
    latency_summary = _read_csv(run_dir / "sync_run_latency_summary.csv")
    model_call_summary = _read_csv(run_dir / "gmail_classifier_model_call_summary.csv")
    event_summaries = _event_summary_dirs(run_dir)
    confidence_audit = _trace_confidence_metrics(run_dir)

    total_audit_rows = sum(_int(row.get("audit_rows")) for row in account_summary)
    total_stored_rows = sum(_int(row.get("stored_rows")) for row in account_summary)
    total_filtered_rows = sum(_int(row.get("filtered_rows")) for row in account_summary)
    total_skipped_rows = sum(_int(row.get("skipped_rows")) for row in account_summary)
    total_gmail_model_calls = sum(_int(row.get("gmail_classifier_model_call_count")) for row in model_call_summary)

    sync_bins = _sync_bin_rows(decision_summary)
    stored_bins = _stored_classification_rows(stored_summary)
    max_sync_bin = max(sync_bins.values() or [0])

    opportunity_rows = [
        row
        for row in stored_domain_summary
        if _domain_is_opportunity_discovery(row.get("sender_domain") or "")
        and (row.get("classification") or "") in OPPORTUNITY_DISCOVERY_CLASSIFICATIONS
    ]
    opportunity_stored_count = sum(_int(row.get("event_count")) for row in opportunity_rows)
    opportunity_by_domain: Counter[str] = Counter()
    opportunity_by_classification: Counter[str] = Counter()
    for row in opportunity_rows:
        opportunity_by_domain[row.get("sender_domain") or "unknown"] += _int(row.get("event_count"))
        opportunity_by_classification[row.get("classification") or "unknown"] += _int(row.get("event_count"))

    account_rows = []
    for row in account_summary:
        account_rows.append(
            {
                "account_label": row.get("account_label") or "unknown",
                "audit_rows": _int(row.get("audit_rows")),
                "stored_rows": _int(row.get("stored_rows")),
                "filtered_rows": _int(row.get("filtered_rows")),
                "skipped_rows": _int(row.get("skipped_rows")),
                "stored_rate_pct": _float(row.get("stored_rate_pct")),
            }
        )

    latency_rows = []
    for row in latency_summary:
        messages = _int(row.get("message_count"))
        seconds = _int(row.get("audit_window_seconds"))
        latency_rows.append(
            {
                "account_label": row.get("account_label") or "unknown",
                "message_count": messages,
                "audit_window_seconds": seconds,
                "messages_per_second": round(messages / seconds, 3) if seconds else 0.0,
            }
        )

    manual_review_by_account = {
        account: {
            "event_count": _int(summary.get("event_count")),
            "manual_review_count": _int(summary.get("manual_review_count")),
            "manual_review_rate_pct": _pct(_int(summary.get("manual_review_count")), _int(summary.get("event_count"))),
            "would_call_llm_count": _int(summary.get("would_call_llm_count")),
            "prompt_leak_count": _int(summary.get("prompt_leak_count")),
        }
        for account, summary in event_summaries.items()
    }

    high_yield_clusters = _top_rows(stored_domain_summary, "event_count", limit=15)
    sync_domain_clusters = _top_rows(sync_domain_summary, "message_count", limit=15)

    return {
        "run_dir": str(run_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "sync_audit_decisions": total_audit_rows,
            "stored_product_emails": total_stored_rows,
            "filtered_not_relevant": total_filtered_rows,
            "skipped_obvious_noise": total_skipped_rows,
            "stored_rate_pct": _pct(total_stored_rows, total_audit_rows),
            "gmail_classifier_model_calls": total_gmail_model_calls,
        },
        "accounts": account_rows,
        "sync_bins": dict(sync_bins),
        "sync_bin_bars": [
            {"bin": key, "count": value, "bar": _ascii_bar(value, max_sync_bin)}
            for key, value in sync_bins.most_common()
        ],
        "stored_bins": dict(stored_bins),
        "latency": latency_rows,
        "manual_review_by_account": manual_review_by_account,
        "top_sync_domain_clusters": sync_domain_clusters,
        "top_stored_domain_clusters": high_yield_clusters,
        "opportunity_discovery_gap": {
            "stored_event_count": opportunity_stored_count,
            "stored_event_rate_pct": _pct(opportunity_stored_count, total_stored_rows),
            "by_domain": dict(opportunity_by_domain.most_common()),
            "by_current_classification": dict(opportunity_by_classification.most_common()),
            "interpretation": (
                "Opportunity-discovery/job-alert emails are currently forced into existing lifecycle bins, "
                "primarily conversation and interview_request."
            ),
        },
        "confidence_audit": confidence_audit,
    }


def _first_existing(run_dir: Path, *names: str) -> Path:
    for name in names:
        candidate = run_dir / name
        if candidate.exists():
            return candidate
    return run_dir / names[0]


def render_summary_markdown(metrics: dict[str, Any]) -> str:
    totals = metrics["totals"]
    account_rows = [
        [
            row["account_label"],
            row["audit_rows"],
            row["stored_rows"],
            row["filtered_rows"],
            row["skipped_rows"],
            f"{row['stored_rate_pct']}%",
        ]
        for row in metrics["accounts"]
    ]
    stored_rows = [[key, value] for key, value in Counter(metrics["stored_bins"]).most_common()]
    sync_bin_rows = [[row["bin"], row["count"], f"`{row['bar']}`"] for row in metrics["sync_bin_bars"]]
    latency_rows = [
        [row["account_label"], row["message_count"], row["audit_window_seconds"], row["messages_per_second"]]
        for row in metrics["latency"]
    ]
    manual_rows = [
        [
            account,
            summary["event_count"],
            summary["manual_review_count"],
            f"{summary['manual_review_rate_pct']}%",
            summary["would_call_llm_count"],
            summary["prompt_leak_count"],
        ]
        for account, summary in sorted(metrics["manual_review_by_account"].items())
    ]
    stored_domain_rows = [
        [
            row.get("account_label", ""),
            row.get("sender_domain", ""),
            row.get("classification", ""),
            row.get("email_type", ""),
            row.get("event_count", ""),
            row.get("avg_confidence", ""),
        ]
        for row in metrics["top_stored_domain_clusters"][:15]
    ]
    opportunity = metrics["opportunity_discovery_gap"]
    opportunity_domain_rows = [[domain, count] for domain, count in opportunity["by_domain"].items()]
    opportunity_class_rows = [[classification, count] for classification, count in opportunity["by_current_classification"].items()]
    confidence_audit = metrics["confidence_audit"]
    confidence_rows = [
        [row["classification"], row["confidence"], row["count"]]
        for row in confidence_audit["confidence_exact_by_classification"][:12]
    ]
    overconfident_rows = [
        [row["sender_domain"], row["feature"], row["count"]]
        for row in confidence_audit["overconfident_interview_without_scheduler"][:12]
    ]
    feature_rows = [
        [row["feature"], row["count"]]
        for row in confidence_audit["top_matched_features"][:12]
    ]

    return "\n".join(
        [
            "# Gmail Classifier Real-Data EDA",
            "",
            f"- Run directory: `{metrics['run_dir']}`",
            f"- Generated at: `{metrics['generated_at']}`",
            "",
            "## Executive Summary",
            "",
            f"- Sync audit decisions: `{totals['sync_audit_decisions']}`",
            f"- Stored product emails: `{totals['stored_product_emails']}`",
            f"- Filtered as not relevant: `{totals['filtered_not_relevant']}`",
            f"- Skipped as obvious noise: `{totals['skipped_obvious_noise']}`",
            f"- Overall stored rate: `{totals['stored_rate_pct']}%`",
            f"- Gmail classifier model calls: `{totals['gmail_classifier_model_calls']}`",
            "",
            "## Charts",
            "",
            "- [Current routing bins](charts/current_routing_bins.svg)",
            "- [Stored classifications](charts/stored_classifications.svg)",
            "- [Account stored rates](charts/account_stored_rates.svg)",
            "- [Opportunity cluster classifications](charts/opportunity_cluster_classifications.svg)",
            "- [Manual review rates](charts/manual_review_rates.svg)",
            "- [Sync throughput](charts/sync_throughput.svg)",
            "",
            "## Account Mix",
            "",
            _markdown_table(["account", "audit", "stored", "filtered", "skipped", "stored rate"], account_rows),
            "",
            "## Current Routing Bins",
            "",
            _markdown_table(["bin", "count", "relative volume"], sync_bin_rows),
            "",
            "## Stored Classification Bins",
            "",
            _markdown_table(["classification", "stored count"], stored_rows),
            "",
            "## High-Yield Stored Sender Clusters",
            "",
            _markdown_table(
                ["account", "sender_domain", "classification", "email_type", "count", "avg_confidence"],
                stored_domain_rows,
            ),
            "",
            "## Opportunity-Discovery Gap",
            "",
            (
                f"Opportunity-discovery/job-alert-like clusters account for "
                f"`{opportunity['stored_event_count']}` stored events "
                f"(`{opportunity['stored_event_rate_pct']}%` of stored emails)."
            ),
            "",
            "These emails are job-adjacent, but many are not application lifecycle emails. "
            "Because the current taxonomy has no `opportunity_discovery` or `job_alert` bin, "
            "they are forced into `conversation`, `interview_request`, or `action_item`.",
            "",
            "### Opportunity Domains",
            "",
            _markdown_table(["domain", "stored count"], opportunity_domain_rows),
            "",
            "### Current Classifications For Opportunity Cluster",
            "",
            _markdown_table(["current classification", "stored count"], opportunity_class_rows),
            "",
            "## Confidence Audit",
            "",
            "Current `confidence` values are deterministic rule scores, not calibrated probabilities. "
            "This audit highlights score clusters that need human-label calibration before they can be treated as probabilities.",
            "",
            "### Repeated Score Values",
            "",
            _markdown_table(["classification", "score", "count"], confidence_rows),
            "",
            "### Overconfident Interview Without Scheduler",
            "",
            _markdown_table(["sender_domain", "matched feature", "count"], overconfident_rows),
            "",
            "### Top Matched Features",
            "",
            _markdown_table(["feature", "count"], feature_rows),
            "",
            "## Manual Review Load",
            "",
            _markdown_table(
                ["account", "stored events", "manual review", "manual review rate", "would call LLM", "prompt leaks"],
                manual_rows,
            ),
            "",
            "## Sync Latency",
            "",
            _markdown_table(["account", "messages", "audit window seconds", "messages/sec"], latency_rows),
            "",
            "## RCA Hypotheses",
            "",
            "1. The classifier taxonomy is missing an `opportunity_discovery` / `job_alert` route.",
            "2. Generic opportunity/interview language from Handshake-style digests is being interpreted as active application lifecycle evidence.",
            "3. Medium-confidence conversations are a high-review-load region and should not automatically mutate application state.",
            "4. The next change should add a route layer before stage classification rather than only adding sender domains to a blocklist.",
            "",
            "## Next Eval Step",
            "",
            "Label the high-yield stored clusters first, especially Handshake/opportunity alerts, "
            "then rerun this EDA after adding the missing route. Compare stored-rate, "
            "`interview_request` false positives, manual-review rate, latency, and Gmail classifier LLM call rate.",
            "",
        ]
    )


def _code_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def _markdown_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def _svg_bar_chart(
    title: str,
    rows: list[tuple[str, float]],
    *,
    value_suffix: str = "",
    width: int = 860,
    row_height: int = 34,
    left_margin: int = 250,
) -> str:
    rows = [(str(label), float(value)) for label, value in rows if value is not None]
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
        value_text = f"{value:g}{value_suffix}"
        parts.extend(
            [
                f'<text x="24" y="{y + 18}" font-family="Arial, sans-serif" font-size="13" fill="#374151">{html.escape(label[:42])}</text>',
                f'<rect x="{left_margin}" y="{y}" width="{chart_width}" height="20" rx="3" fill="#f3f4f6"/>',
                f'<rect x="{left_margin}" y="{y}" width="{bar_width}" height="20" rx="3" fill="#2563eb"/>',
                f'<text x="{left_margin + bar_width + 8}" y="{y + 15}" font-family="Arial, sans-serif" font-size="12" fill="#111827">{html.escape(value_text)}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


def write_chart_artifacts(metrics: dict[str, Any], output_dir: Path) -> Path:
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    routing_rows = [(row["bin"], row["count"]) for row in metrics["sync_bin_bars"]]
    stored_rows = list(Counter(metrics["stored_bins"]).most_common())
    account_rate_rows = [(row["account_label"], row["stored_rate_pct"]) for row in metrics["accounts"]]
    opportunity_rows = list(metrics["opportunity_discovery_gap"]["by_current_classification"].items())
    manual_rows = [
        (account, summary["manual_review_rate_pct"])
        for account, summary in sorted(metrics["manual_review_by_account"].items())
    ]
    throughput_rows = [(row["account_label"], row["messages_per_second"]) for row in metrics["latency"]]
    confidence_rows = [
        (f"{row['classification']} @ {row['confidence']}", row["count"])
        for row in metrics["confidence_audit"]["confidence_exact_by_classification"][:12]
    ]

    charts = {
        "current_routing_bins.svg": _svg_bar_chart("Current routing bins", routing_rows),
        "stored_classifications.svg": _svg_bar_chart("Stored classifications", stored_rows),
        "account_stored_rates.svg": _svg_bar_chart("Stored rate by account", account_rate_rows, value_suffix="%"),
        "opportunity_cluster_classifications.svg": _svg_bar_chart("Opportunity cluster by current classification", opportunity_rows),
        "manual_review_rates.svg": _svg_bar_chart("Manual review rate by account", manual_rows, value_suffix="%"),
        "sync_throughput.svg": _svg_bar_chart("Sync throughput by account", throughput_rows, value_suffix=" msg/s"),
        "confidence_score_clusters.svg": _svg_bar_chart("Repeated rule-score clusters", confidence_rows),
    }
    for filename, content in charts.items():
        (charts_dir / filename).write_text(content, encoding="utf-8")

    (output_dir / "charts.md").write_text(
        "\n".join(
            [
                "# Gmail EDA Charts",
                "",
                *[
                    f"## {filename.removesuffix('.svg').replace('_', ' ').title()}\n\n![{filename}](charts/{filename})\n"
                    for filename in charts
                ],
            ]
        ),
        encoding="utf-8",
    )
    return charts_dir


def render_redacted_examples_markdown(metrics: dict[str, Any]) -> str:
    lines = [
        "# Redacted Example Clusters",
        "",
        "Private real-email-derived examples. These are redacted previews from ignored local artifacts.",
        "",
    ]
    for example in metrics["confidence_audit"]["redacted_examples"][:12]:
        lines.extend(
            [
                f"## {example['case_id']}",
                "",
                f"- account: `{example['account_label']}`",
                f"- sender_domain: `{example['sender_domain']}`",
                f"- predicted: `{example['predicted_route']}` / `{example['predicted_classification']}`",
                f"- confidence: `{example['confidence']}`",
                f"- matched_features: `{'; '.join(example['matched_features'])}`",
                "",
                "```text",
                f"Subject: {example['subject']}",
                "",
                example["body_preview"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_notebook(metrics: dict[str, Any], summary_markdown: str) -> dict[str, Any]:
    run_dir = metrics["run_dir"]
    setup_code = f"""from pathlib import Path
import csv, json
from collections import Counter

RUN_DIR = Path({run_dir!r})

def read_csv(name):
    with (RUN_DIR / name).open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

account_summary = read_csv('sync_account_summary.csv')
decision_summary = read_csv('sync_decision_summary.csv')
stored_summary = read_csv('stored_event_summary.csv')
stored_domains = read_csv('stored_event_domain_summary_top300.csv')
latency = read_csv('sync_run_latency_summary.csv')
metrics = read_json(RUN_DIR / 'eda' / 'eda_metrics.json')
metrics['totals']
"""
    inspection_code = """def show(rows, limit=10):
    for row in rows[:limit]:
        print(row)

print('Account summary')
show(account_summary)

print('\\nTop stored sender-domain clusters')
show(stored_domains, limit=20)
"""
    opportunity_code = """opportunity_rows = [
    row for row in stored_domains
    if any(token in row['sender_domain'].lower() for token in ['handshake', 'indeed', 'linkedin', 'glassdoor'])
]
show(opportunity_rows, limit=30)
"""
    return {
        "cells": [
            _markdown_cell("# Gmail Classifier Real-Data EDA Notebook\n\n"
                           "This notebook is generated from ignored local artifacts under `audit/runs`. "
                           "It should remain private because it is derived from real Gmail data."),
            _code_cell(setup_code),
            _markdown_cell(summary_markdown),
            _markdown_cell("## Generated Charts\n\n"
                           "![Current routing bins](charts/current_routing_bins.svg)\n\n"
                           "![Opportunity cluster classifications](charts/opportunity_cluster_classifications.svg)\n\n"
                           "![Repeated rule-score clusters](charts/confidence_score_clusters.svg)"),
            _markdown_cell("## Raw Aggregate Inspection\n\n"
                           "The next cells load only aggregate CSVs and redacted dry-run summaries."),
            _code_cell(inspection_code),
            _markdown_cell("## Opportunity-Discovery Cluster\n\n"
                           "Inspect job-alert/opportunity domains that currently land in lifecycle bins."),
            _code_cell(opportunity_code),
            _markdown_cell("## Labeling Plan\n\n"
                           "Start by labeling the largest stored clusters, then sample filtered/skipped rows "
                           "for false negatives. Do not tune thresholds until this review identifies which "
                           "errors are taxonomy gaps versus feature gaps."),
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "pygments_lexer": "ipython3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def write_artifacts(run_dir: Path, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or run_dir / "eda"
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = compute_metrics(run_dir)
    summary = render_summary_markdown(metrics)
    notebook = render_notebook(metrics, summary)
    write_chart_artifacts(metrics, output_dir)

    (output_dir / "eda_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "eda_summary.md").write_text(summary, encoding="utf-8")
    (output_dir / "redacted_examples.md").write_text(render_redacted_examples_markdown(metrics), encoding="utf-8")
    (output_dir / "gmail_classifier_real_eda.ipynb").write_text(json.dumps(notebook, indent=2), encoding="utf-8")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, help="Input audit run directory. Defaults to latest combined real baseline.")
    parser.add_argument("--output-dir", type=Path, help="Optional EDA output directory. Defaults to <run-dir>/eda.")
    args = parser.parse_args()

    run_dir = args.run_dir or _latest_run_dir()
    output_dir = write_artifacts(run_dir, args.output_dir)
    print(output_dir)


if __name__ == "__main__":
    main()
