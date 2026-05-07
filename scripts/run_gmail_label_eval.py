#!/usr/bin/env python3
"""Evaluate completed Gmail classifier human labels.

This script reads a private labeling CSV produced by
``scripts/create_gmail_labeling_queue.py`` and writes aggregate eval artifacts
next to it. The input may contain real-email-derived redacted previews, so the
report intentionally avoids copying row-level email text into the eval output.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.create_gmail_labeling_queue import ERROR_BUCKETS, EXPECTED_ROUTES, EXPECTED_SUBTYPES


DEFAULT_LABEL_PATH = (
    "audit/runs/gmail_combined_real_baseline_3acct_2026-05-07T00-22-23Z/"
    "labels/label_queue_priority.csv"
)

CURRENT_CLASSIFICATION_TO_SUBTYPE = {
    "job_update": "application_status_update",
    "interview_request": "interview_request",
    "rejection": "rejection",
    "offer": "offer",
    "action_item": "assessment_or_task",
    "not_relevant": "unknown_other",
    # The old classifier has only a generic conversation label, so keep this
    # intentionally untyped. That makes the subtype gap visible in the eval.
    "conversation": "conversation_untyped",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _float(value: object) -> float:
    try:
        return float(str(value or "0"))
    except ValueError:
        return 0.0


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)) * 100, 2) if denominator else 0.0


def _clean(value: object) -> str:
    return str(value or "").strip()


def normalize_predicted_route(row: dict[str, str]) -> str:
    route = _clean(row.get("predicted_route")).lower()
    classification = _clean(row.get("predicted_classification")).lower()
    if classification == "not_relevant" or route in {"skip", "filter", "filtered"}:
        return "filter"
    if classification == "conversation" or route == "conversation":
        return "conversation"
    if route in {"inbox", "application_inbox", "application"}:
        return "application_inbox"
    return route or "unknown"


def normalize_predicted_subtype(row: dict[str, str]) -> str:
    predicted_subtype = _clean(row.get("predicted_subtype")).lower()
    if predicted_subtype:
        return predicted_subtype
    classification = _clean(row.get("predicted_classification")).lower()
    return CURRENT_CLASSIFICATION_TO_SUBTYPE.get(classification, classification or "unknown")


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: value for key, value in counter.most_common()}


def _matrix(rows: list[dict[str, str]], expected_key: str, predicted_key: str) -> tuple[list[str], list[str], list[list[int]]]:
    expected_labels = sorted({_clean(row.get(expected_key)) for row in rows if _clean(row.get(expected_key))})
    predicted_labels = sorted({_clean(row.get(predicted_key)) for row in rows if _clean(row.get(predicted_key))})
    expected_index = {label: index for index, label in enumerate(expected_labels)}
    predicted_index = {label: index for index, label in enumerate(predicted_labels)}
    matrix = [[0 for _ in predicted_labels] for _ in expected_labels]
    for row in rows:
        expected = _clean(row.get(expected_key))
        predicted = _clean(row.get(predicted_key))
        if expected in expected_index and predicted in predicted_index:
            matrix[expected_index[expected]][predicted_index[predicted]] += 1
    return expected_labels, predicted_labels, matrix


def _matrix_rows(expected_labels: list[str], predicted_labels: list[str], matrix: list[list[int]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for expected, values in zip(expected_labels, matrix):
        row: dict[str, Any] = {"expected": expected}
        for predicted, count in zip(predicted_labels, values):
            row[predicted] = count
        output.append(row)
    return output


def validate_labels(rows: list[dict[str, str]]) -> dict[str, Any]:
    route_values = set(EXPECTED_ROUTES)
    subtype_values = set(EXPECTED_SUBTYPES)
    error_values = set(ERROR_BUCKETS)
    valid_correctness = {"yes", "no", "partial"}

    invalid_routes = Counter(_clean(row.get("expected_route")) for row in rows if _clean(row.get("expected_route")) not in route_values)
    invalid_subtypes = Counter(_clean(row.get("expected_subtype")) for row in rows if _clean(row.get("expected_subtype")) not in subtype_values)
    invalid_errors = Counter(_clean(row.get("error_bucket")) for row in rows if _clean(row.get("error_bucket")) not in error_values)
    invalid_correctness = Counter(_clean(row.get("is_correct")).lower() for row in rows if _clean(row.get("is_correct")).lower() not in valid_correctness)
    missing_by_column = {
        column: sum(1 for row in rows if not _clean(row.get(column)))
        for column in ["expected_route", "expected_subtype", "is_correct", "error_bucket"]
    }
    return {
        "invalid_routes": _counter_dict(invalid_routes),
        "invalid_subtypes": _counter_dict(invalid_subtypes),
        "invalid_error_buckets": _counter_dict(invalid_errors),
        "invalid_is_correct": _counter_dict(invalid_correctness),
        "missing_by_column": missing_by_column,
        "is_valid": not any(
            [
                invalid_routes,
                invalid_subtypes,
                invalid_errors,
                invalid_correctness,
                any(missing_by_column.values()),
            ]
        ),
    }


def compute_label_metrics(label_path: Path) -> dict[str, Any]:
    rows = _read_csv(label_path)
    enriched_rows: list[dict[str, str]] = []
    for row in rows:
        enriched = dict(row)
        enriched["normalized_predicted_route"] = normalize_predicted_route(row)
        enriched["normalized_predicted_subtype"] = normalize_predicted_subtype(row)
        enriched["route_match"] = str(enriched["normalized_predicted_route"] == _clean(row.get("expected_route"))).lower()
        enriched["subtype_match"] = str(enriched["normalized_predicted_subtype"] == _clean(row.get("expected_subtype"))).lower()
        enriched["full_match"] = str(enriched["route_match"] == "true" and enriched["subtype_match"] == "true").lower()
        enriched_rows.append(enriched)

    total = len(enriched_rows)
    correctness = Counter(_clean(row.get("is_correct")).lower() for row in enriched_rows)
    error_buckets = Counter(_clean(row.get("error_bucket")) for row in enriched_rows)
    expected_routes = Counter(_clean(row.get("expected_route")) for row in enriched_rows)
    predicted_routes = Counter(row["normalized_predicted_route"] for row in enriched_rows)
    expected_subtypes = Counter(_clean(row.get("expected_subtype")) for row in enriched_rows)
    predicted_subtypes = Counter(row["normalized_predicted_subtype"] for row in enriched_rows)
    route_pairs = Counter(
        (row["normalized_predicted_route"], _clean(row.get("expected_route")))
        for row in enriched_rows
    )
    subtype_pairs = Counter(
        (row["normalized_predicted_subtype"], _clean(row.get("expected_subtype")))
        for row in enriched_rows
    )
    classification_to_expected = Counter(
        (_clean(row.get("predicted_classification")), _clean(row.get("expected_subtype")))
        for row in enriched_rows
    )
    domain_error = Counter(
        (_clean(row.get("sender_domain")), _clean(row.get("error_bucket")))
        for row in enriched_rows
    )

    high_confidence_wrong = [
        row
        for row in enriched_rows
        if _float(row.get("predicted_confidence")) >= 0.8 and _clean(row.get("is_correct")).lower() == "no"
    ]
    confidence_by_correctness: dict[str, list[float]] = defaultdict(list)
    for row in enriched_rows:
        confidence_by_correctness[_clean(row.get("is_correct")).lower()].append(_float(row.get("predicted_confidence")))
    confidence_summary = {
        key: {
            "count": len(values),
            "avg_confidence": round(sum(values) / len(values), 4) if values else 0,
            "min_confidence": min(values) if values else 0,
            "max_confidence": max(values) if values else 0,
        }
        for key, values in sorted(confidence_by_correctness.items())
    }

    route_expected, route_predicted, route_matrix = _matrix(
        enriched_rows,
        "expected_route",
        "normalized_predicted_route",
    )
    subtype_expected, subtype_predicted, subtype_matrix = _matrix(
        enriched_rows,
        "expected_subtype",
        "normalized_predicted_subtype",
    )

    metrics = {
        "label_path": str(label_path),
        "sample_note": (
            "This is a priority/high-yield human-labeled sample, not a random production sample. "
            "Use it for failure discovery and architecture decisions, not population-level accuracy claims."
        ),
        "validation": validate_labels(enriched_rows),
        "totals": {
            "labeled_rows": total,
            "route_accuracy_pct": _pct(sum(1 for row in enriched_rows if row["route_match"] == "true"), total),
            "subtype_exact_match_pct": _pct(sum(1 for row in enriched_rows if row["subtype_match"] == "true"), total),
            "full_exact_match_pct": _pct(sum(1 for row in enriched_rows if row["full_match"] == "true"), total),
            "human_acceptable_pct": _pct(correctness.get("yes", 0), total),
            "human_partial_pct": _pct(correctness.get("partial", 0), total),
            "human_not_acceptable_pct": _pct(correctness.get("no", 0), total),
            "high_confidence_wrong_count": len(high_confidence_wrong),
            "high_confidence_wrong_rate_pct": _pct(len(high_confidence_wrong), total),
        },
        "distributions": {
            "is_correct": _counter_dict(correctness),
            "error_bucket": _counter_dict(error_buckets),
            "expected_route": _counter_dict(expected_routes),
            "predicted_route": _counter_dict(predicted_routes),
            "expected_subtype": _counter_dict(expected_subtypes),
            "predicted_subtype": _counter_dict(predicted_subtypes),
        },
        "confidence_summary_by_is_correct": confidence_summary,
        "top_route_pairs": [
            {"predicted_route": predicted, "expected_route": expected, "count": count}
            for (predicted, expected), count in route_pairs.most_common(20)
        ],
        "top_subtype_pairs": [
            {"predicted_subtype": predicted, "expected_subtype": expected, "count": count}
            for (predicted, expected), count in subtype_pairs.most_common(30)
        ],
        "top_classification_to_expected_subtype": [
            {"predicted_classification": predicted, "expected_subtype": expected, "count": count}
            for (predicted, expected), count in classification_to_expected.most_common(30)
        ],
        "top_domain_error_buckets": [
            {"sender_domain": domain, "error_bucket": error_bucket, "count": count}
            for (domain, error_bucket), count in domain_error.most_common(25)
        ],
        "route_confusion": {
            "expected_labels": route_expected,
            "predicted_labels": route_predicted,
            "matrix": route_matrix,
        },
        "subtype_confusion": {
            "expected_labels": subtype_expected,
            "predicted_labels": subtype_predicted,
            "matrix": subtype_matrix,
        },
    }
    return metrics


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


def _svg_bar_chart(
    title: str,
    rows: list[tuple[str, float]],
    *,
    value_suffix: str = "",
    width: int = 900,
    row_height: int = 34,
    left_margin: int = 330,
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
                f'<text x="24" y="{y + 18}" font-family="Arial, sans-serif" font-size="13" fill="#374151">{html.escape(label[:54])}</text>',
                f'<rect x="{left_margin}" y="{y}" width="{chart_width}" height="20" rx="3" fill="#f3f4f6"/>',
                f'<rect x="{left_margin}" y="{y}" width="{bar_width}" height="20" rx="3" fill="#dc2626"/>',
                f'<text x="{left_margin + bar_width + 8}" y="{y + 15}" font-family="Arial, sans-serif" font-size="12" fill="#111827">{value:g}{html.escape(value_suffix)}</text>',
            ]
        )
    parts.append("</svg>")
    return "\n".join(parts)


def render_report(metrics: dict[str, Any]) -> str:
    totals = metrics["totals"]
    distributions = metrics["distributions"]
    confidence_rows = [
        [
            key,
            value["count"],
            value["avg_confidence"],
            value["min_confidence"],
            value["max_confidence"],
        ]
        for key, value in metrics["confidence_summary_by_is_correct"].items()
    ]
    return "\n".join(
        [
            "# Gmail Priority Label Eval",
            "",
            f"- Label file: `{metrics['label_path']}`",
            f"- Sample note: {metrics['sample_note']}",
            "",
            "## Summary",
            "",
            _markdown_table(
                ["metric", "value"],
                [
                    ["labeled rows", totals["labeled_rows"]],
                    ["human acceptable", f"{totals['human_acceptable_pct']}%"],
                    ["human partial", f"{totals['human_partial_pct']}%"],
                    ["human not acceptable", f"{totals['human_not_acceptable_pct']}%"],
                    ["route accuracy", f"{totals['route_accuracy_pct']}%"],
                    ["subtype exact match", f"{totals['subtype_exact_match_pct']}%"],
                    ["full exact match", f"{totals['full_exact_match_pct']}%"],
                    ["high-confidence wrong rows", totals["high_confidence_wrong_count"]],
                    ["high-confidence wrong rate", f"{totals['high_confidence_wrong_rate_pct']}%"],
                ],
            ),
            "",
            "## Human Correctness Labels",
            "",
            _markdown_table(["is_correct", "count"], [[key, value] for key, value in distributions["is_correct"].items()]),
            "",
            "## Error Buckets",
            "",
            _markdown_table(["error_bucket", "count"], [[key, value] for key, value in distributions["error_bucket"].items()]),
            "",
            "## Route Distributions",
            "",
            "### Expected Route",
            "",
            _markdown_table(["expected_route", "count"], [[key, value] for key, value in distributions["expected_route"].items()]),
            "",
            "### Normalized Predicted Route",
            "",
            _markdown_table(["predicted_route", "count"], [[key, value] for key, value in distributions["predicted_route"].items()]),
            "",
            "## Top Route Confusions",
            "",
            _markdown_table(
                ["predicted_route", "expected_route", "count"],
                [
                    [row["predicted_route"], row["expected_route"], row["count"]]
                    for row in metrics["top_route_pairs"]
                ],
            ),
            "",
            "## Top Classification To Expected Subtype",
            "",
            _markdown_table(
                ["predicted_classification", "expected_subtype", "count"],
                [
                    [row["predicted_classification"], row["expected_subtype"], row["count"]]
                    for row in metrics["top_classification_to_expected_subtype"][:15]
                ],
            ),
            "",
            "## Confidence By Human Correctness",
            "",
            _markdown_table(["is_correct", "count", "avg_confidence", "min", "max"], confidence_rows),
            "",
            "## Top Domain Failure Clusters",
            "",
            _markdown_table(
                ["sender_domain", "error_bucket", "count"],
                [[row["sender_domain"], row["error_bucket"], row["count"]] for row in metrics["top_domain_error_buckets"][:15]],
            ),
            "",
            "## Interpretation",
            "",
            "This labeled priority sample evaluates the current route-first architecture on high-risk real-email examples. "
            "The model is no longer mainly failing because job-board alerts are inserted into the application pipeline. "
            "The remaining failures are concentrated in conversation-vs-application routing, ambiguous `action_review` cases, "
            "and subtype distinctions inside otherwise safe routes.",
            "",
            "The next classifier change should not be broad threshold loosening. It should target the largest labeled failure clusters:",
            "",
            "```text",
            "1. Separate outbound/user-authored recruiter networking from application lifecycle mail.",
            "2. Improve application confirmation vs generic status-update subtype handling.",
            "3. Add negative rules for finance/product marketing that currently reaches action_review.",
            "4. Keep job-board recommendations filtered unless they are direct recruiter messages or active application events.",
            "```",
            "",
        ]
    )


def write_artifacts(label_path: Path, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or label_path.parent / "eval"
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = compute_label_metrics(label_path)
    if not metrics["validation"]["is_valid"]:
        raise SystemExit(f"Label file has invalid or missing values: {json.dumps(metrics['validation'], indent=2)}")

    (output_dir / "label_eval_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "label_eval_report.md").write_text(render_report(metrics), encoding="utf-8")

    route_confusion = metrics["route_confusion"]
    route_rows = _matrix_rows(
        route_confusion["expected_labels"],
        route_confusion["predicted_labels"],
        route_confusion["matrix"],
    )
    _write_csv(output_dir / "route_confusion.csv", route_rows, ["expected", *route_confusion["predicted_labels"]])

    subtype_rows = [
        row
        for row in metrics["top_subtype_pairs"]
    ]
    _write_csv(
        output_dir / "subtype_confusion_top.csv",
        subtype_rows,
        ["predicted_subtype", "expected_subtype", "count"],
    )

    charts_dir = output_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    charts = {
        "error_buckets.svg": _svg_bar_chart(
            "Error buckets",
            [(key, value) for key, value in metrics["distributions"]["error_bucket"].items()],
        ),
        "human_correctness.svg": _svg_bar_chart(
            "Human correctness",
            [(key, value) for key, value in metrics["distributions"]["is_correct"].items()],
        ),
        "expected_routes.svg": _svg_bar_chart(
            "Expected routes",
            [(key, value) for key, value in metrics["distributions"]["expected_route"].items()],
        ),
        "top_route_confusions.svg": _svg_bar_chart(
            "Top route pairs",
            [
                (f"{row['predicted_route']} -> {row['expected_route']}", row["count"])
                for row in metrics["top_route_pairs"][:10]
            ],
        ),
        "top_domain_failures.svg": _svg_bar_chart(
            "Top domain failure clusters",
            [
                (f"{row['sender_domain']} / {row['error_bucket']}", row["count"])
                for row in metrics["top_domain_error_buckets"][:10]
                if row["error_bucket"] != "correct"
            ],
        ),
    }
    for filename, content in charts.items():
        (charts_dir / filename).write_text(content, encoding="utf-8")
    (output_dir / "charts.md").write_text(
        "\n".join(
            [
                "# Gmail Priority Label Eval Charts",
                "",
                *[
                    f"## {filename.removesuffix('.svg').replace('_', ' ').title()}\n\n![{filename}](charts/{filename})\n"
                    for filename in charts
                ],
            ]
        ),
        encoding="utf-8",
    )
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-path", type=Path, default=Path(DEFAULT_LABEL_PATH))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = write_artifacts(args.label_path, args.output_dir)
    print(output_dir)


if __name__ == "__main__":
    main()
