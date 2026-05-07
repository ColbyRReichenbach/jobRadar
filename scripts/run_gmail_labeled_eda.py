#!/usr/bin/env python3
"""Create a data-science workspace for labeled Gmail classifier evals.

The input is a private human-labeled CSV generated from real Gmail-derived
redacted previews. The output stays next to the label file under
``audit/runs/.../labels/labeled_eda`` and includes aggregate charts, n-gram
lift, pattern diagnostics, theme clusters, and a reproducible notebook.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_gmail_label_eval import compute_label_metrics, normalize_predicted_route, normalize_predicted_subtype


DEFAULT_LABEL_PATH = (
    "audit/runs/gmail_combined_real_baseline_3acct_2026-05-07T00-22-23Z/"
    "labels/label_queue_priority.csv"
)

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "and",
    "any",
    "are",
    "around",
    "because",
    "been",
    "before",
    "being",
    "between",
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
    "she",
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
    "onsite_location_language": re.compile(r"\b(onsite|on-site|hybrid|remote|in[- ]person)\b", re.I),
    "recruiter_language": re.compile(r"\b(recruiter|sourcer|talent|hiring manager|connect|connection|network|message)\b", re.I),
    "scheduler_language": re.compile(r"\b(calendly|schedule a time|book a time|availability|calendar|reschedule)\b", re.I),
    "marketing_language": re.compile(r"\b(sale|deal|discount|newsletter|subscribe|unsubscribe|promo|rewards|offer expires)\b", re.I),
    "finance_noise_language": re.compile(r"\b(account|statement|payment|loan|credit|mortgage|bank|balance)\b", re.I),
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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


def _float(value: object) -> float:
    try:
        return float(str(value or "0"))
    except ValueError:
        return 0.0


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) / float(denominator)) * 100, 2) if denominator else 0.0


def _text(row: dict[str, str]) -> str:
    return f"{row.get('redacted_subject') or ''} {row.get('redacted_body_preview') or ''}"


def _domain_family(domain: str) -> str:
    normalized = domain.lower()
    if "handshake" in normalized:
        return "handshake"
    if any(token in normalized for token in ["linkedin", "glassdoor", "indeed", "ziprecruiter"]):
        return "job_board"
    if any(token in normalized for token in ["gmail", "outlook", "yahoo"]):
        return "personal_email"
    if any(token in normalized for token in ["bank", "wellsfargo", "salliemae", "lendingtree"]):
        return "finance"
    if any(token in normalized for token in ["discount", "foodlion", "chick-fil-a", "carvana", "lowes"]):
        return "retail_marketing"
    return "other"


def _tokens(text: str) -> list[str]:
    raw_tokens = re.findall(r"[a-z][a-z0-9_'-]{2,}", text.lower())
    return [token.strip("'") for token in raw_tokens if token not in STOPWORDS and not token.startswith("redacted")]


def _terms(text: str) -> set[str]:
    tokens = _tokens(text)
    bigrams = [f"{left} {right}" for left, right in zip(tokens, tokens[1:])]
    return set(tokens + bigrams)


def _matched_features(row: dict[str, str]) -> list[str]:
    return [item for item in _clean(row.get("matched_features")).split(";") if item]


def _active_patterns(row: dict[str, str]) -> list[str]:
    text = _text(row)
    features = " ".join(_matched_features(row))
    combined = f"{text} {features}"
    return [name for name, pattern in PATTERNS.items() if pattern.search(combined)]


def _enrich_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = dict(row)
        item["normalized_predicted_route"] = normalize_predicted_route(row)
        item["normalized_predicted_subtype"] = normalize_predicted_subtype(row)
        item["domain_family"] = _domain_family(_clean(row.get("sender_domain")))
        item["active_patterns"] = _active_patterns(row)
        item["token_terms"] = sorted(_terms(_text(row)))
        item["is_correct_normalized"] = _clean(row.get("is_correct")).lower()
        item["predicted_confidence_float"] = _float(row.get("predicted_confidence"))
        enriched.append(item)
    return enriched


def _theme_for_row(row: dict[str, Any]) -> str:
    expected_route = _clean(row.get("expected_route"))
    expected_subtype = _clean(row.get("expected_subtype"))
    family = _clean(row.get("domain_family"))
    patterns = set(row.get("active_patterns") or [])
    if expected_route == "filter" and "marketing_language" in patterns:
        return "marketing_or_non_job_filter"
    if expected_route == "filter" and family in {"finance", "retail_marketing"}:
        return f"{family}_filter"
    if expected_subtype in {"job_alert", "job_board_promo"}:
        if expected_route == "filter":
            return f"{family}_job_alert_filter"
        return f"{family}_opportunity_discovery"
    if expected_subtype == "application_received":
        return "application_confirmation"
    if expected_subtype in {"interview_request", "document_request", "assessment_or_task"}:
        return "application_action_or_interview"
    if expected_subtype == "recruiter_outreach":
        return "recruiter_outreach_conversation"
    if expected_subtype == "referral_or_networking":
        return "networking_conversation"
    if expected_route == "conversation":
        return "other_conversation"
    return "other"


def _top_terms_for_rows(rows: list[dict[str, Any]], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(row.get("token_terms") or [])
    return [term for term, _ in counter.most_common(limit)]


def _term_lift(rows: list[dict[str, Any]], group_key: str, *, min_group_count: int = 2, limit_per_group: int = 12) -> list[dict[str, Any]]:
    total_docs = len(rows)
    term_docs: Counter[str] = Counter()
    group_docs: Counter[str] = Counter()
    group_term_docs: Counter[tuple[str, str]] = Counter()
    for row in rows:
        group = _clean(row.get(group_key))
        if not group:
            continue
        terms = set(row.get("token_terms") or [])
        group_docs[group] += 1
        term_docs.update(terms)
        for term in terms:
            group_term_docs[(group, term)] += 1

    output: list[dict[str, Any]] = []
    for group, doc_count in group_docs.items():
        candidates: list[dict[str, Any]] = []
        for (candidate_group, term), count in group_term_docs.items():
            if candidate_group != group or count < min_group_count:
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


def _feature_lift(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    error_docs: Counter[str] = Counter()
    feature_docs: Counter[str] = Counter()
    error_feature_docs: Counter[tuple[str, str]] = Counter()
    for row in rows:
        error = _clean(row.get("error_bucket"))
        features = set(_matched_features(row))
        error_docs[error] += 1
        feature_docs.update(features)
        for feature in features:
            error_feature_docs[(error, feature)] += 1
    total = len(rows)
    for (error, feature), count in error_feature_docs.items():
        if count < 2:
            continue
        error_count = error_docs[error]
        in_rate = count / error_count if error_count else 0
        out_docs = max(total - error_count, 1)
        out_count = max(feature_docs[feature] - count, 0)
        out_rate = out_count / out_docs
        output.append(
            {
                "error_bucket": error,
                "matched_feature": feature,
                "error_count": count,
                "error_rate_pct": _pct(count, error_count),
                "overall_count": feature_docs[feature],
                "lift": round((in_rate + 0.01) / (out_rate + 0.01), 3),
            }
        )
    output.sort(key=lambda item: (item["lift"], item["error_count"]), reverse=True)
    return output[:80]


def _pattern_diagnostics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for pattern_name in PATTERNS:
        matched = [row for row in rows if pattern_name in (row.get("active_patterns") or [])]
        if not matched:
            continue
        wrong = [row for row in matched if row.get("is_correct_normalized") == "no"]
        predicted_application = [row for row in matched if row.get("normalized_predicted_route") == "application_inbox"]
        expected_filter = [row for row in matched if row.get("expected_route") == "filter"]
        output.append(
            {
                "pattern": pattern_name,
                "matched_rows": len(matched),
                "wrong_rows": len(wrong),
                "wrong_rate_pct": _pct(len(wrong), len(matched)),
                "predicted_application_inbox": len(predicted_application),
                "expected_filter": len(expected_filter),
                "top_expected_route": Counter(_clean(row.get("expected_route")) for row in matched).most_common(1)[0][0],
                "top_error_bucket": Counter(_clean(row.get("error_bucket")) for row in matched).most_common(1)[0][0],
            }
        )
    output.sort(key=lambda item: (item["wrong_rows"], item["matched_rows"]), reverse=True)
    return output


def _theme_clusters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_theme[_theme_for_row(row)].append(row)
    output: list[dict[str, Any]] = []
    for theme, items in sorted(by_theme.items(), key=lambda pair: len(pair[1]), reverse=True):
        output.append(
            {
                "theme": theme,
                "count": len(items),
                "human_not_acceptable": sum(1 for row in items if row.get("is_correct_normalized") == "no"),
                "not_acceptable_rate_pct": _pct(sum(1 for row in items if row.get("is_correct_normalized") == "no"), len(items)),
                "top_expected_route": Counter(_clean(row.get("expected_route")) for row in items).most_common(1)[0][0],
                "top_expected_subtype": Counter(_clean(row.get("expected_subtype")) for row in items).most_common(1)[0][0],
                "top_error_bucket": Counter(_clean(row.get("error_bucket")) for row in items).most_common(1)[0][0],
                "top_domain_family": Counter(_clean(row.get("domain_family")) for row in items).most_common(1)[0][0],
                "top_terms": ";".join(_top_terms_for_rows(items, limit=8)),
            }
        )
    return output


def _matrix_counts(rows: list[dict[str, Any]], expected_key: str, predicted_key: str) -> dict[str, Any]:
    expected_labels = sorted({_clean(row.get(expected_key)) for row in rows if _clean(row.get(expected_key))})
    predicted_labels = sorted({_clean(row.get(predicted_key)) for row in rows if _clean(row.get(predicted_key))})
    matrix = [[0 for _ in predicted_labels] for _ in expected_labels]
    expected_index = {label: index for index, label in enumerate(expected_labels)}
    predicted_index = {label: index for index, label in enumerate(predicted_labels)}
    for row in rows:
        expected = _clean(row.get(expected_key))
        predicted = _clean(row.get(predicted_key))
        if expected in expected_index and predicted in predicted_index:
            matrix[expected_index[expected]][predicted_index[predicted]] += 1
    return {"expected_labels": expected_labels, "predicted_labels": predicted_labels, "matrix": matrix}


def compute_labeled_eda(label_path: Path) -> dict[str, Any]:
    rows = _enrich_rows(_read_csv(label_path))
    label_metrics = compute_label_metrics(label_path)
    themes = _theme_clusters(rows)
    pattern_diagnostics = _pattern_diagnostics(rows)
    error_ngram_lift = _term_lift(rows, "error_bucket")
    route_ngram_lift = _term_lift(rows, "expected_route")
    feature_error_lift = _feature_lift(rows)
    route_matrix = _matrix_counts(rows, "expected_route", "normalized_predicted_route")

    examples: list[dict[str, Any]] = []
    for theme in themes:
        theme_rows = [row for row in rows if _theme_for_row(row) == theme["theme"]]
        selected = sorted(
            theme_rows,
            key=lambda row: (row.get("is_correct_normalized") == "yes", -_float(row.get("predicted_confidence"))),
        )[:3]
        for row in selected:
            examples.append(
                {
                    "theme": theme["theme"],
                    "case_id": row.get("case_id"),
                    "sender_domain": row.get("sender_domain"),
                    "predicted": f"{row.get('normalized_predicted_route')} / {row.get('predicted_classification')}",
                    "expected": f"{row.get('expected_route')} / {row.get('expected_subtype')}",
                    "is_correct": row.get("is_correct"),
                    "error_bucket": row.get("error_bucket"),
                    "confidence": row.get("predicted_confidence"),
                    "active_patterns": ";".join(row.get("active_patterns") or []),
                    "subject": row.get("redacted_subject"),
                    "body_preview": row.get("redacted_body_preview"),
                }
            )

    return {
        "label_path": str(label_path),
        "sample_note": label_metrics["sample_note"],
        "label_metrics": label_metrics,
        "theme_clusters": themes,
        "pattern_diagnostics": pattern_diagnostics,
        "error_ngram_lift": error_ngram_lift,
        "route_ngram_lift": route_ngram_lift,
        "feature_error_lift": feature_error_lift,
        "route_matrix": route_matrix,
        "examples": examples,
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


def _svg_heatmap(title: str, expected_labels: list[str], predicted_labels: list[str], matrix: list[list[int]]) -> str:
    cell = 64
    left = 190
    top = 92
    width = left + cell * len(predicted_labels) + 40
    height = top + cell * len(expected_labels) + 70
    max_value = max((value for row in matrix for value in row), default=0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="34" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#111827">{html.escape(title)}</text>',
    ]
    for col, label in enumerate(predicted_labels):
        x = left + col * cell + cell / 2
        parts.append(
            f'<text x="{x}" y="72" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#374151" transform="rotate(-25 {x} 72)">{html.escape(label[:18])}</text>'
        )
    for row_index, expected in enumerate(expected_labels):
        y = top + row_index * cell
        parts.append(
            f'<text x="24" y="{y + 38}" font-family="Arial, sans-serif" font-size="12" fill="#374151">{html.escape(expected[:24])}</text>'
        )
        for col_index, _predicted in enumerate(predicted_labels):
            value = matrix[row_index][col_index]
            intensity = 0 if max_value <= 0 else value / max_value
            blue = 245 - round(135 * intensity)
            fill = f"rgb({blue},{blue + 6},{255})"
            x = left + col_index * cell
            parts.extend(
                [
                    f'<rect x="{x}" y="{y}" width="{cell - 3}" height="{cell - 3}" rx="4" fill="{fill}" stroke="#e5e7eb"/>',
                    f'<text x="{x + cell / 2}" y="{y + 37}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#111827">{value}</text>',
                ]
            )
    parts.append("</svg>")
    return "\n".join(parts)


def render_report(metrics: dict[str, Any]) -> str:
    totals = metrics["label_metrics"]["totals"]
    themes = metrics["theme_clusters"]
    patterns = metrics["pattern_diagnostics"]
    error_terms = metrics["error_ngram_lift"]
    feature_lift = metrics["feature_error_lift"]
    return "\n".join(
        [
            "# Gmail Labeled Classifier EDA Workspace",
            "",
            f"- Label file: `{metrics['label_path']}`",
            f"- Sample note: {metrics['sample_note']}",
            "",
            "## What This Workspace Does",
            "",
            "This is a data-science workspace for turning the labeled priority queue into implementation decisions. "
            "It combines aggregate eval metrics with lexical diagnostics, theme clusters, feature lift, confidence checks, and redacted examples.",
            "",
            "Methods used:",
            "",
            "- Human-label validation against the route/subtype/error taxonomy.",
            "- Route and subtype confusion analysis.",
            "- Pattern prevalence analysis for terms such as apply, interview, onsite, recruiter, marketing, and scheduler language.",
            "- N-gram lift by error bucket and expected route to surface discriminative language.",
            "- Matched-feature lift by error bucket to locate brittle rules.",
            "- Redacted example sampling by theme cluster for qualitative RCA.",
            "",
            "Methods intentionally not used yet:",
            "",
            "- Supervised probability model training, because the labeled set is small and priority-biased.",
            "- Transformer/embedding clustering, because the current failure is mostly taxonomy and route design, not semantic capacity.",
            "",
            "## Label Eval Summary",
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
                    ["high-confidence wrong rate", f"{totals['high_confidence_wrong_rate_pct']}%"],
                ],
            ),
            "",
            "## Theme Clusters",
            "",
            _markdown_table(
                ["theme", "count", "not acceptable", "not acceptable rate", "top subtype", "top error", "top terms"],
                [
                    [
                        row["theme"],
                        row["count"],
                        row["human_not_acceptable"],
                        f"{row['not_acceptable_rate_pct']}%",
                        row["top_expected_subtype"],
                        row["top_error_bucket"],
                        row["top_terms"],
                    ]
                    for row in themes
                ],
            ),
            "",
            "## Pattern Diagnostics",
            "",
            _markdown_table(
                ["pattern", "matched", "wrong", "wrong rate", "predicted app inbox", "expected filter", "top error"],
                [
                    [
                        row["pattern"],
                        row["matched_rows"],
                        row["wrong_rows"],
                        f"{row['wrong_rate_pct']}%",
                        row["predicted_application_inbox"],
                        row["expected_filter"],
                        row["top_error_bucket"],
                    ]
                    for row in patterns
                ],
            ),
            "",
            "## Top Error-Bucket N-Gram Lift",
            "",
            _markdown_table(
                ["error_bucket", "term", "group count", "group rate", "lift"],
                [
                    [row["group"], row["term"], row["group_count"], f"{row['group_rate_pct']}%", row["lift"]]
                    for row in error_terms[:24]
                ],
            ),
            "",
            "## Matched Feature Lift By Error Bucket",
            "",
            _markdown_table(
                ["error_bucket", "matched_feature", "count", "rate", "lift"],
                [
                    [row["error_bucket"], row["matched_feature"], row["error_count"], f"{row['error_rate_pct']}%", row["lift"]]
                    for row in feature_lift[:24]
                ],
            ),
            "",
            "## Working Hypotheses",
            "",
            "1. `apply` and generic job alert language are not enough to route to `application_inbox`; the route needs evidence of a user-applied process.",
            "2. `onsite` should be treated as location context unless accompanied by scheduler/interview-process evidence.",
            "3. Handshake and job-board alerts should be filtered from user workflows while preserving `job_alert` / `job_board_promo` subtype evidence.",
            "4. Marketing language should be a stronger negative feature even when the sender or copy mentions jobs.",
            "5. Conversation should split into recruiter outreach and networking only after the route is already `conversation`.",
            "",
            "## Next Modeling Decision",
            "",
            "The next model should still be a deterministic/hybrid classifier, not a trained transformer. "
            "The labeled sample shows that the main fix is route decomposition and feature gating. "
            "A learned probability model becomes useful after a broader labeled sample includes enough true positives and true negatives per route.",
            "",
        ]
    )


def _code_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source.splitlines(keepends=True)}


def _markdown_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def render_notebook(label_path: Path, output_dir: Path, metrics: dict[str, Any], report: str) -> dict[str, Any]:
    setup = f"""from pathlib import Path
import csv, json
from collections import Counter
from pprint import pprint

LABEL_PATH = Path({str(label_path.resolve())!r})
EDA_DIR = Path({str(output_dir.resolve())!r})

if not LABEL_PATH.exists():
    raise FileNotFoundError(f"Label file not found: {{LABEL_PATH}}")
if not (EDA_DIR / 'labeled_eda_metrics.json').exists():
    raise FileNotFoundError(f"Metrics file not found: {{EDA_DIR / 'labeled_eda_metrics.json'}}")

with LABEL_PATH.open(newline='', encoding='utf-8') as handle:
    rows = list(csv.DictReader(handle))

metrics = json.loads((EDA_DIR / 'labeled_eda_metrics.json').read_text(encoding='utf-8'))
print(f"Loaded {{len(rows)}} labeled rows")
pprint(metrics['label_metrics']['totals'])
"""
    cell_bootstrap = f"""from pathlib import Path
import csv, json
from collections import Counter
from pprint import pprint

LABEL_PATH = Path({str(label_path.resolve())!r})
EDA_DIR = Path({str(output_dir.resolve())!r})
with LABEL_PATH.open(newline='', encoding='utf-8') as handle:
    rows = list(csv.DictReader(handle))
metrics = json.loads((EDA_DIR / 'labeled_eda_metrics.json').read_text(encoding='utf-8'))
"""
    inspect = cell_bootstrap + """
route_counts = Counter(row['expected_route'] for row in rows)
error_counts = Counter(row['error_bucket'] for row in rows)

print("Expected route counts")
pprint(route_counts.most_common())

print("\\nError bucket counts")
pprint(error_counts.most_common())
"""
    term = cell_bootstrap + """
# Inspect discriminative terms for the largest error bucket.
terms = [
    row for row in metrics['error_ngram_lift']
    if row['group'] == 'false_positive_opportunity_as_lifecycle'
]
pprint(terms[:20])
"""
    return {
        "cells": [
            _markdown_cell("# Gmail Labeled Classifier EDA\n\n"
                           "Generated private notebook from redacted real-email-derived labels."),
            _code_cell(setup),
            _markdown_cell(report),
            _markdown_cell("## Charts\n\n"
                           "![Theme clusters](charts/theme_clusters.svg)\n\n"
                           "![Route confusion heatmap](charts/route_confusion_heatmap.svg)\n\n"
                           "![Pattern wrong rates](charts/pattern_wrong_rates.svg)"),
            _code_cell(inspect),
            _code_cell(term),
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def render_examples(metrics: dict[str, Any]) -> str:
    lines = [
        "# Redacted Labeled Examples By Theme",
        "",
        "Private redacted examples. These are included for qualitative RCA and should remain under `audit/runs/`.",
        "",
    ]
    for example in metrics["examples"]:
        lines.extend(
            [
                f"## {example['theme']} / {example['case_id']}",
                "",
                f"- sender_domain: `{example['sender_domain']}`",
                f"- predicted: `{example['predicted']}`",
                f"- expected: `{example['expected']}`",
                f"- is_correct: `{example['is_correct']}`",
                f"- error_bucket: `{example['error_bucket']}`",
                f"- confidence: `{example['confidence']}`",
                f"- active_patterns: `{example['active_patterns']}`",
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


def write_artifacts(label_path: Path, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or label_path.parent / "labeled_eda"
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = compute_labeled_eda(label_path)
    report = render_report(metrics)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(exist_ok=True)

    _write_csv(output_dir / "theme_clusters.csv", metrics["theme_clusters"])
    _write_csv(output_dir / "pattern_diagnostics.csv", metrics["pattern_diagnostics"])
    _write_csv(output_dir / "error_ngram_lift.csv", metrics["error_ngram_lift"])
    _write_csv(output_dir / "route_ngram_lift.csv", metrics["route_ngram_lift"])
    _write_csv(output_dir / "feature_error_lift.csv", metrics["feature_error_lift"])
    _write_csv(
        output_dir / "example_index.csv",
        [
            {key: value for key, value in example.items() if key not in {"subject", "body_preview"}}
            for example in metrics["examples"]
        ],
    )

    route_matrix = metrics["route_matrix"]
    charts = {
        "theme_clusters.svg": _svg_bar_chart(
            "Theme clusters",
            [(row["theme"], row["count"]) for row in metrics["theme_clusters"]],
            fill="#2563eb",
        ),
        "theme_not_acceptable_rates.svg": _svg_bar_chart(
            "Theme not-acceptable rates",
            [(row["theme"], row["not_acceptable_rate_pct"]) for row in metrics["theme_clusters"]],
            value_suffix="%",
            fill="#dc2626",
        ),
        "pattern_wrong_rates.svg": _svg_bar_chart(
            "Pattern wrong rates",
            [(row["pattern"], row["wrong_rate_pct"]) for row in metrics["pattern_diagnostics"]],
            value_suffix="%",
            fill="#dc2626",
        ),
        "top_error_terms.svg": _svg_bar_chart(
            "Top error terms by lift",
            [(f"{row['group']} / {row['term']}", row["lift"]) for row in metrics["error_ngram_lift"][:15]],
            fill="#7c3aed",
        ),
        "feature_error_lift.svg": _svg_bar_chart(
            "Matched feature lift by error bucket",
            [(f"{row['error_bucket']} / {row['matched_feature']}", row["lift"]) for row in metrics["feature_error_lift"][:15]],
            fill="#ea580c",
        ),
        "route_confusion_heatmap.svg": _svg_heatmap(
            "Route confusion heatmap",
            route_matrix["expected_labels"],
            route_matrix["predicted_labels"],
            route_matrix["matrix"],
        ),
    }
    for filename, content in charts.items():
        (charts_dir / filename).write_text(content, encoding="utf-8")

    (output_dir / "charts.md").write_text(
        "\n".join(
            [
                "# Gmail Labeled EDA Charts",
                "",
                *[
                    f"## {filename.removesuffix('.svg').replace('_', ' ').title()}\n\n![{filename}](charts/{filename})\n"
                    for filename in charts
                ],
            ]
        ),
        encoding="utf-8",
    )
    (output_dir / "labeled_eda_metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    (output_dir / "labeled_eda_report.md").write_text(report, encoding="utf-8")
    (output_dir / "redacted_examples_by_theme.md").write_text(render_examples(metrics), encoding="utf-8")
    (output_dir / "gmail_labeled_eda_workspace.ipynb").write_text(
        json.dumps(render_notebook(label_path, output_dir, metrics, report), indent=2),
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
