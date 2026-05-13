from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


OUTPUT_REPORT = Path("docs/ai-artifacts/gmail-classifier-ml-vs-heuristics-case-study.md")
OUTPUT_LINKEDIN = Path("docs/ai-artifacts/gmail-classifier-linkedin-post.md")
CHART_DIR = Path("docs/ai-artifacts/gmail-classifier-case-study-assets")

PRIOR_LABELS = Path("audit/runs/gmail_combined_real_baseline_3acct_2026-05-07T00-22-23Z/labels/label_queue_priority.csv")
CURRENT_LABELS = Path("audit/runs/gmail_labeling_sample/2026-05-12T20-40-container/label_queue_priority_policy_corrected.csv")
ROUTE_FIRST_METRICS = Path(
    "audit/runs/gmail_combined_real_baseline_3acct_2026-05-07T00-22-23Z/labels/route_first_subset_eval/metrics.json"
)
CURRENT_LABEL_EVAL = Path("audit/runs/gmail_labeling_sample/2026-05-12T20-40-container/label_eval_summary.json")
LR_METRICS = Path("audit/runs/gmail_lr_shadow_eval/2026-05-12Tnew-only-policy-corrected/metrics.json")
HIERARCHY_METRICS = Path("audit/runs/gmail_hierarchical_subtype_eval/2026-05-12Tglobal-vs-hierarchical-subtype/metrics.json")
SYNTHETIC_FAILURE_EXAMPLE = Path(
    "audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-live-synthetic-v2/synthetic_scenarios.csv"
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _labeled_count(path: Path) -> tuple[int, int, Counter[str], Counter[str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labeled = [
        row
        for row in rows
        if str(row.get("expected_route") or "").strip() and str(row.get("expected_subtype") or "").strip()
    ]
    return (
        len(rows),
        len(labeled),
        Counter(str(row.get("expected_route") or "").strip() for row in labeled),
        Counter(str(row.get("expected_subtype") or "").strip() for row in labeled),
    )


def _load_labeled_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _short_text(value: str, max_chars: int = 180) -> str:
    cleaned = " ".join((value or "").replace("\u200c", " ").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "..."


def _publication_safe_text(value: str, max_chars: int = 180) -> str:
    text = _short_text(value, max_chars)
    text = re.sub(r"\b(Hi|Hello|Hey|Dear)\s+[A-Z][A-Za-z.'-]+\b", r"\1 [PERSON]", text)
    text = re.sub(r"\bDS\s+\d{4,}\b", "[REFERENCE_ID]", text)
    text = re.sub(r"\b\d{5,}\b", "[ID]", text)
    return text


def _compact_redactions(value: str) -> str:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return value or "{}"
    if not parsed:
        return "{}"
    return "; ".join(f"{key}={count}" for key, count in sorted(parsed.items()))


def _md_cell(value: str) -> str:
    return html.escape(value, quote=False).replace("|", "\\|")


def _load_synthetic_failure_example() -> dict[str, str]:
    with SYNTHETIC_FAILURE_EXAMPLE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("subject") == "Job Alert: New Software Developer Openings":
                return row
    raise RuntimeError(f"Could not find synthetic failure example in {SYNTHETIC_FAILURE_EXAMPLE}")


def _synthetic_failure_block(row: dict[str, str]) -> str:
    body = _short_text(row.get("body") or "", 230)
    artifact = SYNTHETIC_FAILURE_EXAMPLE.as_posix()
    return f"""One early run made the risk obvious. The generator produced the row below as `{row.get('expected_route')}/{row.get('expected_subtype')}` and, before the review gate was tightened, marked it `training_eligible={row.get('training_eligible')}` even though `human_reviewed={row.get('human_reviewed')}`.

```text
Subject: {row.get('subject')}
Assigned label: {row.get('expected_route')}/{row.get('expected_subtype')}
Body excerpt: {body}
Generator rationale: {row.get('rationale')}
```

Source: `{artifact}`. That is not a subtle failure. The email is clearly a job alert, and the generator's own rationale says it should be filtered. If I had trained on this without checking it, I would have taught the model that a job alert belongs in the application inbox. That is exactly the kind of label noise that makes a classifier look better in a lab and worse in the product.
"""


def _pick_redacted_examples(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selectors = [
        (
            "Ambiguous marketing/noise row",
            lambda row: row.get("would_call_llm") == "true"
            and row.get("expected_route") == "filter"
            and row.get("expected_subtype") == "marketing_promo",
        ),
        (
            "Application confirmation with lifecycle ambiguity",
            lambda row: row.get("expected_route") == "application_inbox"
            and row.get("expected_subtype") == "application_received"
            and row.get("would_call_llm") == "true",
        ),
        (
            "Recruiter conversation with private reply context",
            lambda row: row.get("expected_route") == "conversation"
            and row.get("expected_subtype") == "recruiter_outreach"
            and row.get("would_call_llm") == "true",
        ),
    ]
    examples: list[dict[str, str]] = []
    used_case_ids: set[str] = set()
    for label, predicate in selectors:
        for row in rows:
            if not predicate(row):
                continue
            case_id = row.get("case_id") or ""
            if case_id in used_case_ids:
                continue
            used_case_ids.add(case_id)
            examples.append(
                {
                    "example": label,
                    "expected": f"{row.get('expected_route')}/{row.get('expected_subtype')}",
                    "predicted": f"{row.get('predicted_route')}/{row.get('predicted_subtype')}",
                    "subject": _publication_safe_text(row.get("redacted_subject") or "", 120),
                    "body": _publication_safe_text(row.get("redacted_body_preview") or row.get("redacted_snippet") or "", 220),
                    "redactions": _compact_redactions(row.get("redaction_counts") or "{}"),
                    "preflight": "blocked" if row.get("preflight_blocked") == "true" else "eligible" if row.get("would_call_llm") == "true" else "not called",
                }
            )
            break
    return examples


def _redacted_example_blocks(examples: list[dict[str, str]]) -> str:
    rows = []
    for example in examples:
        rows.append(
            f"""**{example["example"]}**

- Expected: `{example["expected"]}`
- Current prediction: `{example["predicted"]}`
- Redacted subject: {example["subject"]}
- Redacted body excerpt: {example["body"]}
- Redactions: `{example["redactions"]}`
- Preflight: {example["preflight"]}
"""
        )
    return "\n".join(rows)


def _preflight_summary(rows: list[dict[str, str]]) -> dict[str, int]:
    labeled = [
        row
        for row in rows
        if str(row.get("expected_route") or "").strip() and str(row.get("expected_subtype") or "").strip()
    ]
    would_call = [row for row in labeled if row.get("would_call_llm") == "true"]
    blocked = [row for row in labeled if row.get("preflight_blocked") == "true"]
    return {
        "labeled": len(labeled),
        "would_call_llm": len(would_call),
        "preflight_blocked": len(blocked),
    }


def _pct(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        value = float(value)
    if value <= 1:
        value *= 100
    return f"{value:.1f}%"


def _pct_num(value: float | int | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, int):
        value = float(value)
    if value <= 1:
        value *= 100
    return float(value)


def _agg(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    if isinstance(value, dict):
        return _pct_num(value.get("mean"))
    return _pct_num(value)


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _bar_svg(
    path: Path,
    *,
    title: str,
    series: list[tuple[str, float, str]],
    width: int = 920,
    height: int = 430,
    max_value: float | None = None,
    suffix: str = "%",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 230
    margin_right = 45
    margin_top = 70
    row_height = 43
    bar_height = 24
    max_value = max_value or max(value for _, value, _ in series) or 1
    usable_width = width - margin_left - margin_right
    chart_height = margin_top + (row_height * len(series)) + 35
    height = max(height, chart_height)
    rows = []
    for index, (label, value, color) in enumerate(series):
        y = margin_top + index * row_height
        bar_width = max(0, min(usable_width, usable_width * (value / max_value)))
        rows.append(
            f'<text x="20" y="{y + 18}" font-size="14" fill="#263238">{_escape(label)}</text>'
            f'<rect x="{margin_left}" y="{y}" width="{usable_width}" height="{bar_height}" fill="#eef2f3" rx="4"/>'
            f'<rect x="{margin_left}" y="{y}" width="{bar_width:.1f}" height="{bar_height}" fill="{color}" rx="4"/>'
            f'<text x="{margin_left + bar_width + 8:.1f}" y="{y + 17}" font-size="13" fill="#263238">{value:.1f}{suffix}</text>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="20" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <text x="{margin_left}" y="58" font-size="12" fill="#607d8b">0</text>
  <text x="{margin_left + usable_width - 28}" y="58" font-size="12" fill="#607d8b">{max_value:.0f}{suffix}</text>
  <line x1="{margin_left}" y1="62" x2="{margin_left + usable_width}" y2="62" stroke="#cfd8dc"/>
  {''.join(rows)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _grouped_bar_svg(
    path: Path,
    *,
    title: str,
    groups: list[tuple[str, list[tuple[str, float, str]]]],
    width: int = 940,
    height: int = 500,
    max_value: float = 100,
    suffix: str = "%",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 170
    margin_right = 35
    margin_top = 78
    group_gap = 22
    bar_gap = 7
    bar_height = 18
    usable_width = width - margin_left - margin_right
    y = margin_top
    rows: list[str] = []
    for group_label, bars in groups:
        rows.append(f'<text x="20" y="{y + 14}" font-size="15" font-weight="700" fill="#263238">{_escape(group_label)}</text>')
        for label, value, color in bars:
            bar_width = max(0, min(usable_width, usable_width * (value / max_value)))
            rows.append(
                f'<text x="42" y="{y + 39}" font-size="13" fill="#455a64">{_escape(label)}</text>'
                f'<rect x="{margin_left}" y="{y + 23}" width="{usable_width}" height="{bar_height}" fill="#eef2f3" rx="4"/>'
                f'<rect x="{margin_left}" y="{y + 23}" width="{bar_width:.1f}" height="{bar_height}" fill="{color}" rx="4"/>'
                f'<text x="{margin_left + bar_width + 8:.1f}" y="{y + 37}" font-size="12" fill="#263238">{value:.1f}{suffix}</text>'
            )
            y += bar_height + bar_gap
        y += group_gap
    height = max(height, y + 20)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="20" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <text x="{margin_left}" y="60" font-size="12" fill="#607d8b">0</text>
  <text x="{margin_left + usable_width - 35}" y="60" font-size="12" fill="#607d8b">{max_value:.0f}{suffix}</text>
  <line x1="{margin_left}" y1="64" x2="{margin_left + usable_width}" y2="64" stroke="#cfd8dc"/>
  {''.join(rows)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _stacked_bar_svg(
    path: Path,
    *,
    title: str,
    groups: list[tuple[str, int, list[tuple[str, float, str]]]],
    width: int = 940,
    height: int = 430,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 190
    margin_right = 35
    margin_top = 86
    row_height = 52
    bar_height = 24
    usable_width = width - margin_left - margin_right
    legend_items: dict[str, str] = {}
    rows: list[str] = []
    for index, (label, total, segments) in enumerate(groups):
        y = margin_top + index * row_height
        x = margin_left
        rows.append(f'<text x="20" y="{y + 18}" font-size="14" font-weight="700" fill="#263238">{_escape(label)}</text>')
        rows.append(f'<text x="20" y="{y + 36}" font-size="12" fill="#607d8b">n={total}</text>')
        for segment_label, value, color in segments:
            if total <= 0:
                continue
            segment_width = usable_width * (value / total)
            legend_items.setdefault(segment_label, color)
            rows.append(
                f'<rect x="{x:.1f}" y="{y}" width="{segment_width:.1f}" height="{bar_height}" fill="{color}"/>'
            )
            if segment_width >= 58:
                pct = value / total * 100
                rows.append(
                    f'<text x="{x + segment_width / 2:.1f}" y="{y + 17}" text-anchor="middle" font-size="12" fill="#ffffff">{pct:.0f}%</text>'
                )
            x += segment_width
        rows.append(f'<rect x="{margin_left}" y="{y}" width="{usable_width}" height="{bar_height}" fill="none" stroke="#cfd8dc"/>')
    legend_x = 20
    legend_y = 56
    legend: list[str] = []
    for label, color in legend_items.items():
        legend.append(
            f'<rect x="{legend_x}" y="{legend_y}" width="12" height="12" fill="{color}"/>'
            f'<text x="{legend_x + 18}" y="{legend_y + 11}" font-size="12" fill="#455a64">{_escape(label)}</text>'
        )
        legend_x += 18 + len(label) * 7 + 34
    height = max(height, margin_top + len(groups) * row_height + 35)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="20" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  {''.join(legend)}
  {''.join(rows)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _waffle_svg(
    path: Path,
    *,
    title: str,
    counts: dict[str, int],
    colors: dict[str, str],
    width: int = 920,
    height: int = 390,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = sum(counts.values()) or 1
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    floors: dict[str, int] = {label: int((count / total) * 100) for label, count in ordered}
    remainder = 100 - sum(floors.values())
    residuals = sorted(
        ((label, (count / total) * 100 - floors[label]) for label, count in ordered),
        key=lambda item: item[1],
        reverse=True,
    )
    for label, _ in residuals[:remainder]:
        floors[label] += 1

    cells: list[str] = []
    cell_labels: list[str] = []
    for label, _ in ordered:
        cell_labels.extend([label] * floors[label])
    size = 20
    gap = 5
    start_x = 48
    start_y = 78
    for index, label in enumerate(cell_labels[:100]):
        row = index // 10
        col = index % 10
        cells.append(
            f'<rect x="{start_x + col * (size + gap)}" y="{start_y + row * (size + gap)}" width="{size}" height="{size}" rx="3" fill="{colors.get(label, "#78909c")}"/>'
        )

    legend: list[str] = []
    legend_x = 365
    legend_y = 86
    for index, (label, count) in enumerate(ordered):
        y = legend_y + index * 42
        pct = count / total * 100
        legend.append(
            f'<rect x="{legend_x}" y="{y - 14}" width="14" height="14" rx="2" fill="{colors.get(label, "#78909c")}"/>'
            f'<text x="{legend_x + 22}" y="{y - 3}" font-size="14" font-weight="700" fill="#263238">{_escape(label)}</text>'
            f'<text x="{legend_x + 190}" y="{y - 3}" font-size="14" fill="#455a64">{count} rows / {pct:.1f}%</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="30" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <text x="30" y="58" font-size="13" fill="#607d8b">Each square is approximately 1% of the labeled set.</text>
  {''.join(cells)}
  {''.join(legend)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _dumbbell_svg(
    path: Path,
    *,
    title: str,
    series: list[tuple[str, float, float]],
    width: int = 920,
    height: int = 360,
    max_value: float = 100,
    suffix: str = "%",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 260
    margin_right = 80
    margin_top = 88
    row_height = 58
    usable_width = width - margin_left - margin_right
    rows: list[str] = []
    for index, (label, old_value, new_value) in enumerate(series):
        y = margin_top + index * row_height
        old_x = margin_left + usable_width * (old_value / max_value)
        new_x = margin_left + usable_width * (new_value / max_value)
        delta = new_value - old_value
        rows.append(f'<text x="28" y="{y + 5}" font-size="14" fill="#263238">{_escape(label)}</text>')
        rows.append(f'<line x1="{old_x:.1f}" y1="{y}" x2="{new_x:.1f}" y2="{y}" stroke="#90a4ae" stroke-width="4" stroke-linecap="round"/>')
        rows.append(f'<circle cx="{old_x:.1f}" cy="{y}" r="8" fill="#78909c"/>')
        rows.append(f'<circle cx="{new_x:.1f}" cy="{y}" r="8" fill="#00897b"/>')
        rows.append(f'<text x="{old_x:.1f}" y="{y + 27}" text-anchor="middle" font-size="12" fill="#455a64">{old_value:.1f}{suffix}</text>')
        rows.append(f'<text x="{new_x:.1f}" y="{y - 15}" text-anchor="middle" font-size="12" font-weight="700" fill="#00695c">{new_value:.1f}{suffix}</text>')
        rows.append(f'<text x="{width - 42}" y="{y + 5}" text-anchor="end" font-size="13" fill="#263238">{delta:+.1f} pts</text>')
    height = max(height, margin_top + row_height * len(series) + 45)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="28" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <text x="{margin_left}" y="62" font-size="12" fill="#607d8b">0{suffix}</text>
  <text x="{margin_left + usable_width - 35}" y="62" font-size="12" fill="#607d8b">{max_value:.0f}{suffix}</text>
  <line x1="{margin_left}" y1="68" x2="{margin_left + usable_width}" y2="68" stroke="#cfd8dc"/>
  <circle cx="{width - 188}" cy="34" r="7" fill="#78909c"/><text x="{width - 176}" y="38" font-size="12" fill="#455a64">before</text>
  <circle cx="{width - 120}" cy="34" r="7" fill="#00897b"/><text x="{width - 108}" y="38" font-size="12" fill="#455a64">after</text>
  {''.join(rows)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _dot_plot_svg(
    path: Path,
    *,
    title: str,
    series: list[tuple[str, int]],
    threshold: int,
    width: int = 940,
    height: int = 690,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 245
    margin_right = 60
    margin_top = 76
    row_height = 38
    usable_width = width - margin_left - margin_right
    max_value = max((value for _, value in series), default=1)
    threshold_x = margin_left + usable_width * (threshold / max_value)
    rows: list[str] = []
    for index, (label, value) in enumerate(series):
        y = margin_top + index * row_height
        x = margin_left + usable_width * (value / max_value)
        color = "#00897b" if value >= threshold else "#ef5350"
        rows.append(f'<line x1="{margin_left}" y1="{y}" x2="{margin_left + usable_width}" y2="{y}" stroke="#eceff1"/>')
        rows.append(f'<text x="24" y="{y + 5}" font-size="13" fill="#263238">{_escape(label)}</text>')
        rows.append(f'<circle cx="{x:.1f}" cy="{y}" r="8" fill="{color}"/>')
        rows.append(f'<text x="{x + 13:.1f}" y="{y + 5}" font-size="12" fill="#263238">{value}</text>')
    height = max(height, margin_top + row_height * len(series) + 45)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="24" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <line x1="{margin_left}" y1="54" x2="{margin_left + usable_width}" y2="54" stroke="#cfd8dc"/>
  <line x1="{threshold_x:.1f}" y1="58" x2="{threshold_x:.1f}" y2="{height - 28}" stroke="#f9a825" stroke-dasharray="5 5"/>
  <text x="{threshold_x + 8:.1f}" y="71" font-size="12" fill="#8d6e00">10-row rough floor</text>
  <text x="{margin_left}" y="48" font-size="12" fill="#607d8b">0</text>
  <text x="{margin_left + usable_width - 22}" y="48" font-size="12" fill="#607d8b">{max_value}</text>
  {''.join(rows)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _pareto_svg(
    path: Path,
    *,
    title: str,
    series: list[tuple[str, int, str]],
    width: int = 940,
    height: int = 440,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 78
    margin_right = 70
    margin_top = 112
    chart_height = 220
    chart_width = width - margin_left - margin_right
    total = sum(value for _, value, _ in series) or 1
    max_value = max((value for _, value, _ in series), default=1)
    bar_gap = 18
    bar_width = (chart_width - bar_gap * (len(series) - 1)) / max(len(series), 1)
    bars: list[str] = []
    points: list[tuple[float, float]] = []
    cumulative = 0
    friendly_labels = {
        "false_negative_job_related": ["False negative", "job-related"],
        "wrong_stage": ["Wrong subtype"],
        "wrong_route": ["Wrong route"],
        "false_positive_noise": ["False positive", "noise"],
        "false_positive_opportunity_as_lifecycle": ["False positive", "oppty lifecycle"],
    }
    for index, (label, value, color) in enumerate(series):
        x = margin_left + index * (bar_width + bar_gap)
        bar_height = chart_height * (value / max_value)
        y = margin_top + chart_height - bar_height
        cumulative += value
        pct = cumulative / total * 100
        point_x = x + bar_width / 2
        point_y = margin_top + chart_height * (1 - pct / 100)
        points.append((point_x, point_y))
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{color}" rx="5"/>')
        bars.append(f'<text x="{point_x:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-size="13" fill="#263238">{value}</text>')
        label_lines = friendly_labels.get(label, [label.replace("_", " ")])
        label_tspans = "".join(
            f'<tspan x="{point_x:.1f}" dy="{0 if line_index == 0 else 13}">{_escape(line)}</tspan>'
            for line_index, line in enumerate(label_lines)
        )
        bars.append(
            f'<text x="{point_x:.1f}" y="{margin_top + chart_height + 24}" text-anchor="middle" font-size="11" fill="#455a64">{label_tspans}</text>'
        )
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#102027"/>' for x, y in points)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="24" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <text x="24" y="56" font-size="12" fill="#607d8b">Bars show error counts; line shows cumulative share of all errors.</text>
  <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + chart_height}" stroke="#cfd8dc"/>
  <line x1="{margin_left}" y1="{margin_top + chart_height}" x2="{margin_left + chart_width}" y2="{margin_top + chart_height}" stroke="#cfd8dc"/>
  <text x="{margin_left - 10}" y="{margin_top + 5}" text-anchor="end" font-size="12" fill="#607d8b">{max_value}</text>
  <text x="{width - margin_right + 8}" y="{margin_top + 5}" font-size="12" fill="#607d8b">100%</text>
  <polyline points="{polyline}" fill="none" stroke="#102027" stroke-width="2.5"/>
  {circles}
  {''.join(bars)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _line_svg(
    path: Path,
    *,
    title: str,
    series: list[tuple[str, int]],
    width: int = 920,
    height: int = 390,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 78
    margin_right = 48
    margin_top = 100
    chart_height = 190
    chart_width = width - margin_left - margin_right
    max_value = max((value for _, value in series), default=1)
    step = chart_width / max(len(series) - 1, 1)
    points: list[tuple[float, float, str, int]] = []
    for index, (label, value) in enumerate(series):
        x = margin_left + index * step
        y = margin_top + chart_height * (1 - value / max_value)
        points.append((x, y, label, value))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in points)
    point_nodes = []
    for x, y, label, value in points:
        point_nodes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="#00897b"/>')
        point_nodes.append(f'<text x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle" font-size="13" fill="#263238">{value}</text>')
        point_nodes.append(f'<text x="{x:.1f}" y="{margin_top + chart_height + 28}" text-anchor="middle" font-size="13" fill="#455a64">{_escape(label)}</text>')
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="24" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <text x="24" y="56" font-size="12" fill="#607d8b">Accepted means schema-valid generation, not approved training data.</text>
  <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + chart_height}" stroke="#cfd8dc"/>
  <line x1="{margin_left}" y1="{margin_top + chart_height}" x2="{margin_left + chart_width}" y2="{margin_top + chart_height}" stroke="#cfd8dc"/>
  <text x="{margin_left - 10}" y="{margin_top + 5}" text-anchor="end" font-size="12" fill="#607d8b">{max_value}</text>
  <text x="{margin_left - 10}" y="{margin_top + chart_height}" text-anchor="end" font-size="12" fill="#607d8b">0</text>
  <polyline points="{polyline}" fill="none" stroke="#00897b" stroke-width="3"/>
  <line x1="{margin_left}" y1="{margin_top + chart_height}" x2="{margin_left + chart_width}" y2="{margin_top + chart_height}" stroke="#ef5350" stroke-width="2" stroke-dasharray="6 5"/>
  <text x="{margin_left + chart_width - 210}" y="{margin_top + chart_height - 10}" font-size="12" fill="#b71c1c">training eligible after review = 0</text>
  {''.join(point_nodes)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _signed_delta_svg(
    path: Path,
    *,
    title: str,
    series: list[tuple[str, float]],
    width: int = 900,
    height: int = 340,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    margin_left = 245
    margin_right = 55
    margin_top = 72
    row_height = 48
    bar_height = 24
    usable_width = width - margin_left - margin_right
    zero_x = margin_left + usable_width / 2
    max_abs = max(abs(value) for _, value in series) or 1.0
    rows: list[str] = []
    for index, (label, value) in enumerate(series):
        y = margin_top + index * row_height
        width_scale = (usable_width / 2) * (abs(value) / max_abs)
        x = zero_x if value >= 0 else zero_x - width_scale
        color = "#00897b" if value >= 0 else "#ef5350"
        rows.append(f'<text x="20" y="{y + 18}" font-size="14" fill="#263238">{_escape(label)}</text>')
        rows.append(f'<rect x="{x:.1f}" y="{y}" width="{width_scale:.1f}" height="{bar_height}" fill="{color}" rx="4"/>')
        if value >= 0:
            rows.append(
                f'<text x="{x + width_scale + 8:.1f}" y="{y + 17}" text-anchor="start" font-size="13" fill="#263238">{value:+.1f} pts</text>'
            )
        else:
            rows.append(
                f'<text x="{x + width_scale / 2:.1f}" y="{y + 17}" text-anchor="middle" font-size="13" font-weight="700" fill="#ffffff">{value:+.1f} pts</text>'
            )
    height = max(height, margin_top + row_height * len(series) + 35)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="20" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <line x1="{zero_x:.1f}" y1="54" x2="{zero_x:.1f}" y2="{height - 28}" stroke="#607d8b" stroke-width="1.5"/>
  <text x="{zero_x - 8:.1f}" y="58" text-anchor="end" font-size="12" fill="#607d8b">LR worse</text>
  <text x="{zero_x + 8:.1f}" y="58" font-size="12" fill="#607d8b">LR better</text>
  {''.join(rows)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _confusion_matrix_svg(
    path: Path,
    *,
    title: str,
    labels: list[str],
    matrix: list[list[int]],
    width: int = 940,
    height: int = 650,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    short_labels = {
        "action_review": "action",
        "application_inbox": "app inbox",
        "conversation": "conversation",
        "filter": "filter",
        "opportunity_discovery": "oppty",
    }
    cell = 88
    left = 230
    top = 112
    max_value = max((value for row in matrix for value in row), default=1) or 1
    cells: list[str] = []
    for row_index, row_label in enumerate(labels):
        row = matrix[row_index]
        y = top + row_index * cell
        cells.append(
            f'<text x="{left - 16}" y="{y + cell / 2 + 5:.1f}" text-anchor="end" font-size="13" fill="#263238">{_escape(short_labels.get(row_label, row_label))}</text>'
        )
        for col_index, value in enumerate(row):
            x = left + col_index * cell
            intensity = value / max_value
            if row_index == col_index:
                fill = "#00897b"
                opacity = 0.16 + 0.72 * intensity
            else:
                fill = "#ef5350"
                opacity = 0.08 + 0.62 * intensity if value else 0.03
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{fill}" fill-opacity="{opacity:.2f}" stroke="#ffffff"/>'
                f'<text x="{x + cell / 2:.1f}" y="{y + cell / 2 + 5:.1f}" text-anchor="middle" font-size="18" font-weight="700" fill="#263238">{value}</text>'
            )
    headers: list[str] = []
    for col_index, label in enumerate(labels):
        x = left + col_index * cell + cell / 2
        headers.append(
            f'<text x="{x:.1f}" y="{top - 16}" text-anchor="middle" font-size="13" fill="#263238">{_escape(short_labels.get(label, label))}</text>'
        )
    height = max(height, top + cell * len(labels) + 80)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_escape(title)}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="20" y="34" font-size="22" font-weight="700" fill="#102027">{_escape(title)}</text>
  <text x="{left + cell * len(labels) / 2:.1f}" y="70" text-anchor="middle" font-size="14" fill="#455a64">Predicted route</text>
  <text x="32" y="{top + cell * len(labels) / 2:.1f}" transform="rotate(-90 32 {top + cell * len(labels) / 2:.1f})" text-anchor="middle" font-size="14" fill="#455a64">Expected route</text>
  <rect x="{left}" y="{top}" width="{cell * len(labels)}" height="{cell * len(labels)}" fill="none" stroke="#cfd8dc"/>
  {''.join(headers)}
  {''.join(cells)}
  <text x="{left}" y="{height - 35}" font-size="12" fill="#607d8b">Green diagonal cells are correct route decisions; red off-diagonal cells show route confusion counts.</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _workflow_svg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 980
    height = 360
    boxes = [
        (30, 92, 140, 74, "Gmail sync", "recent messages"),
        (205, 92, 150, 74, "Preflight", "redaction + safety"),
        (390, 92, 150, 74, "Route-first", "filter / convo / app"),
        (575, 92, 150, 74, "Subtype policy", "status gates"),
        (760, 92, 170, 74, "Product surfaces", "store, match, trace"),
    ]
    lower = [
        (390, 230, 150, 70, "Ambiguous?", "action_review"),
        (575, 230, 150, 70, "LLM second pass", "preflight-safe only"),
        (760, 230, 170, 70, "Deterministic fallback", "no unsafe mutation"),
    ]
    def box(x: int, y: int, w: int, h: int, title: str, subtitle: str, fill: str) -> str:
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="#b0bec5"/>'
            f'<text x="{x + w / 2:.1f}" y="{y + 31}" text-anchor="middle" font-size="15" font-weight="700" fill="#102027">{_escape(title)}</text>'
            f'<text x="{x + w / 2:.1f}" y="{y + 53}" text-anchor="middle" font-size="12" fill="#455a64">{_escape(subtitle)}</text>'
        )
    def arrow(x1: int, y1: int, x2: int, y2: int) -> str:
        return (
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#607d8b" stroke-width="2"/>'
            f'<polygon points="{x2},{y2} {x2 - 9},{y2 - 5} {x2 - 9},{y2 + 5}" fill="#607d8b"/>'
        )
    parts = [box(*item, "#e0f2f1") for item in boxes]
    parts.extend(box(*item, "#fff8e1") for item in lower)
    parts.extend(
        [
            arrow(170, 129, 205, 129),
            arrow(355, 129, 390, 129),
            arrow(540, 129, 575, 129),
            arrow(725, 129, 760, 129),
            '<line x1="465" y1="166" x2="465" y2="230" stroke="#607d8b" stroke-width="2"/>',
            '<polygon points="465,230 460,221 470,221" fill="#607d8b"/>',
            arrow(540, 265, 575, 265),
            arrow(725, 265, 760, 265),
        ]
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="AppTrail Gmail classifier workflow">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="30" y="38" font-size="22" font-weight="700" fill="#102027">AppTrail Gmail classifier workflow</text>
  <text x="30" y="62" font-size="13" fill="#607d8b">Cheap deterministic routing handles clear cases; expensive semantic reasoning is reserved for ambiguous workflow-impacting cases.</text>
  {''.join(parts)}
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def _write_charts(
    route_first: dict[str, Any],
    current_eval: dict[str, Any],
    lr: dict[str, Any],
    hierarchy: dict[str, Any],
) -> dict[str, Path]:
    charts: dict[str, Path] = {}
    charts["workflow"] = CHART_DIR / "gmail-classifier-workflow.svg"
    _workflow_svg(charts["workflow"])

    charts["route_first"] = CHART_DIR / "route-first-improvement.svg"
    _dumbbell_svg(
        charts["route_first"],
        title="Route-first rewrite: before vs after",
        series=[
            ("Route accuracy", route_first["old_route_accuracy_pct"], route_first["new_route_accuracy_pct"]),
            ("Subtype accuracy", route_first["old_subtype_accuracy_pct"], route_first["new_subtype_accuracy_pct"]),
            ("Storage-surface accuracy", route_first["old_surface_accuracy_pct"], route_first["new_surface_accuracy_pct"]),
        ],
    )

    charts["current_distribution"] = CHART_DIR / "current-label-route-distribution.svg"
    route_counts = current_eval["expected_route_counts"]
    route_colors = {
        "filter": "#00897b",
        "conversation": "#5c6bc0",
        "application_inbox": "#f9a825",
        "action_review": "#ef5350",
        "opportunity_discovery": "#78909c",
    }
    _waffle_svg(
        charts["current_distribution"],
        title="Current human-labeled route mix",
        counts={str(route): int(count) for route, count in route_counts.items()},
        colors=route_colors,
    )

    account_groups = []
    for account_role, account_metrics in current_eval["by_account"].items():
        counts = account_metrics["expected_route_counts"]
        total = int(account_metrics["count"])
        account_groups.append(
            (
                account_role.replace("_", " "),
                total,
                [
                    (route, float(counts.get(route, 0)), route_colors.get(route, "#78909c"))
                    for route in ["filter", "conversation", "application_inbox", "action_review"]
                    if counts.get(route, 0)
                ],
            )
        )
    charts["account_distribution"] = CHART_DIR / "route-distribution-by-account.svg"
    _stacked_bar_svg(charts["account_distribution"], title="Label mix across my three synced inboxes", groups=account_groups)

    charts["subtype_sparsity"] = CHART_DIR / "subtype-label-sparsity.svg"
    subtype_counts = current_eval["expected_subtype_counts"]
    _dot_plot_svg(
        charts["subtype_sparsity"],
        title="Subtype label coverage is sparse outside the top classes",
        series=[
            (subtype, int(count))
            for subtype, count in sorted(subtype_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        threshold=10,
    )

    charts["lr_splits"] = CHART_DIR / "lr-route-split-comparison.svg"
    split_groups = []
    lr_deltas = []
    for split_name, label in [
        ("random_stratified", "Random split"),
        ("sender_domain_grouped", "Sender-domain grouped"),
        ("source_account_grouped", "Source/account grouped"),
    ]:
        aggregate = lr["eval"]["splits"][split_name]["aggregate"]
        heuristic_acc = _agg(aggregate["heuristic"], "route_accuracy")
        lr_acc = _agg(aggregate["tfidf_lr_text"], "route_accuracy")
        lr_deltas.append((label, lr_acc - heuristic_acc))
        split_groups.append(
            (
                label,
                [
                    ("heuristic route acc", heuristic_acc, "#78909c"),
                    ("LR route acc", lr_acc, "#00897b"),
                    ("heuristic macro F1", _agg(aggregate["heuristic"], "macro_f1"), "#b0bec5"),
                    ("LR macro F1", _agg(aggregate["tfidf_lr_text"], "macro_f1"), "#26a69a"),
                ],
            )
        )
    _grouped_bar_svg(charts["lr_splits"], title="Route-only LR: random split vs grouped splits", groups=split_groups)

    charts["lr_delta"] = CHART_DIR / "lr-generalization-delta.svg"
    _signed_delta_svg(
        charts["lr_delta"],
        title="LR route accuracy lift disappears under source shift",
        series=lr_deltas,
    )

    charts["hierarchy"] = CHART_DIR / "hierarchical-subtype-full-accuracy.svg"
    hierarchy_groups = []
    for split_name, label in [
        ("random_stratified", "Random split"),
        ("sender_domain_grouped", "Sender-domain grouped"),
        ("source_account_grouped", "Source/account grouped"),
    ]:
        aggregate = hierarchy["real_eval"][split_name]["aggregate"]
        hierarchy_groups.append(
            (
                label,
                [
                    ("heuristic", _agg(aggregate["heuristic_current"], "full_route_subtype_accuracy"), "#78909c"),
                    ("global combo LR", _agg(aggregate["global_combo_lr"], "full_route_subtype_accuracy"), "#7e57c2"),
                    ("LR route -> LR subtype", _agg(aggregate["hierarchical_predicted_route_lr"], "full_route_subtype_accuracy"), "#00897b"),
                    ("oracle route -> LR subtype", _agg(aggregate["hierarchical_oracle_route_subtype_lr"], "full_route_subtype_accuracy"), "#f9a825"),
                ],
            )
        )
    _grouped_bar_svg(
        charts["hierarchy"],
        title="Subtype architectures: full route+subtype accuracy",
        groups=hierarchy_groups,
        height=620,
    )

    return charts


def _chart(path: Path) -> str:
    return f"![{path.stem}]({path.relative_to(OUTPUT_REPORT.parent).as_posix()})"


def _report(
    prior: tuple[int, int, Counter[str], Counter[str]],
    current: tuple[int, int, Counter[str], Counter[str]],
    current_rows: list[dict[str, str]],
    route_first: dict[str, Any],
    current_eval: dict[str, Any],
    lr: dict[str, Any],
    hierarchy: dict[str, Any],
    charts: dict[str, Path],
) -> str:
    prior_total, prior_labeled, prior_routes, _ = prior
    current_total, current_labeled, current_routes, current_subtypes = current
    total_reviewed = prior_total + current_total
    total_labeled = prior_labeled + current_labeled
    lr_random = lr["eval"]["splits"]["random_stratified"]["aggregate"]
    lr_sender = lr["eval"]["splits"]["sender_domain_grouped"]["aggregate"]
    lr_source = lr["eval"]["splits"]["source_account_grouped"]["aggregate"]
    hierarchy_source = hierarchy["real_eval"]["source_account_grouped"]["aggregate"]
    kaggle_probe = hierarchy["kaggle"]["application_subtype_probe"]
    kaggle_meta = hierarchy["kaggle"]["metadata"]
    preflight = _preflight_summary(current_rows)
    synthetic_failure = _synthetic_failure_block(_load_synthetic_failure_example())
    labeled_current_rows = [
        row
        for row in current_rows
        if str(row.get("expected_route") or "").strip() and str(row.get("expected_subtype") or "").strip()
    ]
    non_app_status_update_allowed = sum(
        1
        for row in labeled_current_rows
        if row.get("expected_route") != "application_inbox" and row.get("status_update_allowed") == "true"
    )
    predicted_app_expected_non_app = sum(
        1
        for row in labeled_current_rows
        if row.get("expected_route") != "application_inbox" and row.get("predicted_route") == "application_inbox"
    )
    prior_route_rows = "".join(
        f"| `{route}` | {count} |\n"
        for route, count in sorted(prior_routes.items(), key=lambda item: item[1], reverse=True)
    )
    current_route_rows = "".join(
        f"| `{route}` | {count} |\n"
        for route, count in sorted(current_routes.items(), key=lambda item: item[1], reverse=True)
    )
    current_subtype_rows = "".join(
        f"| `{subtype}` | {count} |\n" for subtype, count in current_subtypes.most_common(10)
    )
    error_bucket_rows = "".join(
        f"| `{bucket}` | {count} |\n" for bucket, count in current_eval["error_bucket_counts"].items()
    )

    return f"""# I Built a Gmail Classifier Starting From Zero Labeled Data. Here's What Actually Worked.

<p style="margin-top:-0.06in;margin-bottom:0.2in;color:#455a64;font-size:12.5pt;">By <strong>Colby Reichenbach</strong></p>

There is a version of this story where I tell you I trained a model, hit `{_pct(_agg(lr_random['tfidf_lr_text'], 'route_accuracy'))}` accuracy, and shipped it. That version is technically true. It is also almost completely misleading, and honestly it is the version most people would post.

Here is the real one.

## What I Am Building and Why This Problem Exists

AppTrail is a job-search OS I am building solo. One place to track applications, sync Gmail, follow recruiter conversations, prep for interviews, capture job opportunities, and do research without losing everything across seventeen browser tabs and a spreadsheet you stopped updating three weeks ago.

Gmail sync is central to the whole thing because email is where most job-search events actually land first. Application confirmations, rejections, recruiter replies, interview scheduling links, assessments, job alerts, and a whole lot of noise. The classifier's job is to look at each inbound message and route it into one of four product behaviors:

- **Filter** -- ignore it, suppress it from the product entirely
- **Conversation** -- surface it as a recruiter or networking thread
- **Application inbox** -- attach it to an active application lifecycle
- **Action review** -- something job-related but ambiguous, flag it for a closer look

Sounds like a pretty standard classification problem. Four classes, route each email, done. Except the labels here are not just labels. They are operational decisions with downstream side effects.

A message routed to application inbox can trigger a status update on an active job application. Route a job-board marketing digest there by mistake and you have silently corrupted someone's application state. Route a recruiter reply to filter and you have hidden something the user actually needed to act on. The error cost is not symmetric. Some wrong answers are annoying. Others break the product.

This is the thing that gets lost when people talk about ML accuracy as the primary goal. Accuracy is a proxy. The real question is always: what actually happens downstream when the classifier is wrong?

{_chart(charts['workflow'])}

## The Starting Condition: Zero Labels

Solo builder, real inbox data, zero pre-labeled training data. That is not a unique situation. That is the starting condition for pretty much every applied ML problem that is not a Kaggle competition.

So where do you get data?

I could not treat raw Gmail as a bulk training corpus or something I could freely export, share, or hand to a model. I could use my own synced emails for careful labeling, but only with scoped exports, redaction where needed, and a clear separation between "data I can inspect locally" and "data I would ever send to an external system." I also could not use a public email dataset as the main source of truth because none of them had my route taxonomy. I could not generate synthetic data without first knowing what correct looked like inside my own system. And I could not label at scale while I was also building the product, managing the pipeline, and doing everything else that comes with building solo.

The move in this situation is to start with heuristics and use them to generate signal.

A heuristic classifier is not a fallback. It is not a placeholder you swap out later with real ML. It is a decision policy you can read, explain, and iterate on. It also produces predictions you can label against, which is exactly how you build your first real training set without burning runway or privacy budget.

So that is where I started.

## The First Classifier and How It Broke

The initial version used lifecycle-style signals to decide routing. Does this email mention `onsite`? Does it have a scheduling link? Does it reference an application stage or a hiring decision?

It worked fine on obvious cases. It was a mess on the edge cases that matter.

When I ran my first diagnostic labeling pass, 160 priority rows pulled from live Gmail syncs and manually labeled, the failure mode was pretty clear:

- 63 rows: job-board alerts or digest emails confidently routed to application inbox
- 25 rows: marketing-style emails routed to conversation
- 53 rows: high-confidence predictions that were just wrong

The classifier was chasing surface-level signals without asking whether the email was part of an actual candidate process at all. Words like `onsite`, `apply`, `recommendations`, and `applications due` were treated as lifecycle evidence regardless of context.

The `onsite` signal is a good example. It showed up in 77 emails. Wrong 90% of the time. Because `onsite` in a job-board listing means the job is physically located on-site. Geographic. `onsite` in a scheduling message from a recruiter means interview format. Same word, completely different meaning depending on what kind of email you are actually looking at.

The classifier had no way to resolve that. So it guessed wrong, confidently, over and over.

## The Fix: Route First, Then Subtype

The architectural fix was pretty simple once I saw the failure mode clearly. Decide where an email belongs before you try to figure out what it means within that destination.

The rewrite separated route selection from subtype classification and enforced that order:

```text
email
  -> privacy and safety preflight
  -> local feature extraction
  -> route scoring       <- destination decided here
  -> route selection
  -> subtype classification inside the selected route
  -> deterministic side-effect policy
  -> optional redacted LLM adjudication for ambiguous cases
```

And critically, the side-effect policy -- whether a message can trigger an application status update -- is gated on route and application/status policy, not on subtype confidence alone. That is the layer that prevents a confident but wrong subtype prediction from freely touching downstream state.

The same `onsite` signal now gets interpreted differently depending on which route the email is heading toward. In a filter-bound email it is geographic noise. In a conversation-bound email from a recruiter it might be interview context. The signal did not change. What changed is when and how it gets used.

Results on the original 160-row diagnostic set after the rewrite:

{_chart(charts['route_first'])}

| Metric | Before | After |
| --- | ---: | ---: |
| Route accuracy | {_pct(route_first['old_route_accuracy_pct'])} | {_pct(route_first['new_route_accuracy_pct'])} |
| Storage-surface accuracy | {_pct(route_first['old_surface_accuracy_pct'])} | {_pct(route_first['new_surface_accuracy_pct'])} |
| Unwanted stored rows | {route_first['old_unwanted_store_count']} | {route_first['new_unwanted_store_count']} |
| Marketing-as-conversation errors | 25 | {route_first['new_marketing_as_conversation_count']} |
| Opportunity/filter as lifecycle errors | 63 | {route_first['new_opportunity_or_filter_as_lifecycle_count']} |

The number I care most about is unwanted stored rows. `{route_first['old_unwanted_store_count']}` down to `{route_first['new_unwanted_store_count']}`. That is the product metric. Everything else is how you explain it.

The tradeoff is conservative fallback behavior. About 30% of rows in this subset would have escalated to LLM adjudication rather than making a deterministic call. That is a deliberate choice. In a system where wrong answers have real side effects, saying "I am not sure" is better than being wrong with confidence.

## Building the Label Set

To run actual ML experiments I needed actual labels. I exported two priority-sampled batches from live Gmail syncs: emails that were either high-confidence wrong, in edge-case territory, or from underrepresented categories. Two waves, `{total_reviewed}` total rows, `{total_labeled}` with usable labels.

Because the label policy changed as the route taxonomy became clearer, I did not treat those two waves as one clean training pool. The distribution below is the newer `{current_labeled}`-row policy-corrected set, which is also the set behind the LR metrics later in the report:

That newer set came from three connected inboxes I control, and the mix matters. My main inbox is where most real job applications and recruiter threads land. My alumni inbox has more job-board and career-platform promotional traffic. My old personal inbox is mostly random noise. So when I talk about a source/account split later, it is not an abstract platform metric; it is a practical way to test whether the classifier still works when the inbox personality changes.

{_chart(charts['current_distribution'])}

{_chart(charts['account_distribution'])}

| Route | Count |
| --- | ---: |
{current_route_rows}

Top subtype counts:

| Subtype | Count |
| --- | ---: |
{current_subtype_rows}

{_chart(charts['subtype_sparsity'])}

Several subtypes had fewer than 10 examples. `interview_request` had 4. `action_review` had 6 route-level examples. This is not a sampling problem. It is just reality. Most email is noise. Application lifecycle events are actually rare. Recruiter messages cluster around a small slice of senders.

This is the data problem that tutorials do not really prepare you for. You do not get to choose your class distribution. You work with what your product generates. And if your product is job-search tooling, your classes are naturally imbalanced because real job searches are naturally imbalanced. Most of what lands in your inbox is garbage.

## Running the ML Experiment

With real labels in hand, I ran a TF-IDF + Logistic Regression shadow classifier. Not a transformer, not an embedding model, not an LLM. The simplest thing that could plausibly work.

The numbers below use the newer `{current_labeled}`-row policy-corrected label set, not a blind pool of all `{total_labeled}` historical labels. That matters because the labeling policy changed as the route taxonomy became clearer.

The reasoning was practical: fast to train and evaluate, cheap to run many times, interpretable enough that you can see which tokens drove which predictions, and easy to test under different evaluation conditions without burning a lot of time.

The evaluation design here matters more than the model choice. I used three split strategies.

**Random stratified split** -- shuffle and split, preserving class ratios. Standard evaluation you see in most ML writeups.

**Sender-domain grouped split** -- hold out entire sender domains. Tests whether the model generalizes to email senders it has not seen before.

**Source/account grouped split** -- hold out entire Gmail accounts from that three-inbox set. This is the closest thing I had to real production conditions. A new user connects their Gmail and the model has to classify their inbox cold, having never seen their senders, their writing patterns, or their email history.

Results:

{_chart(charts['lr_splits'])}

{_chart(charts['lr_delta'])}

| Split | Heuristic acc / macro F1 | LR acc / macro F1 |
| --- | ---: | ---: |
| Random stratified | {_pct(_agg(lr_random['heuristic'], 'route_accuracy'))} / {_pct(_agg(lr_random['heuristic'], 'macro_f1'))} | {_pct(_agg(lr_random['tfidf_lr_text'], 'route_accuracy'))} / {_pct(_agg(lr_random['tfidf_lr_text'], 'macro_f1'))} |
| Sender-domain grouped | {_pct(_agg(lr_sender['heuristic'], 'route_accuracy'))} / {_pct(_agg(lr_sender['heuristic'], 'macro_f1'))} | {_pct(_agg(lr_sender['tfidf_lr_text'], 'route_accuracy'))} / {_pct(_agg(lr_sender['tfidf_lr_text'], 'macro_f1'))} |
| Source/account grouped | {_pct(_agg(lr_source['heuristic'], 'route_accuracy'))} / {_pct(_agg(lr_source['heuristic'], 'macro_f1'))} | {_pct(_agg(lr_source['tfidf_lr_text'], 'route_accuracy'))} / {_pct(_agg(lr_source['tfidf_lr_text'], 'macro_f1'))} |

The random split looks great. `{_pct(_agg(lr_random['tfidf_lr_text'], 'route_accuracy'))}`. That is the number you put in a blog post if you want to sound like you shipped something impressive.

The source/account grouped split is the honest one. Under production-like conditions LR dropped to `{_pct(_agg(lr_source['tfidf_lr_text'], 'route_accuracy'))}` accuracy and `{_pct(_agg(lr_source['tfidf_lr_text'], 'macro_f1'))}` macro F1. Application-inbox recall, the most important class for the product, fell to `{_pct(_agg(lr_source['tfidf_lr_text'], 'application_inbox_recall'))}`. The model could not find a single application lifecycle email when evaluated on accounts it had not seen during training.

The heuristic held at `{_pct(_agg(lr_source['heuristic'], 'route_accuracy'))}` under the same split. Heuristics generalize differently from learned models. They are not fitting to the distribution of your training accounts. They are encoding domain rules that apply regardless of who the sender is, because they never trained on accounts at all.

This is the core lesson from the whole experiment. Evaluation design determines what you actually learn. A random split would have told me to ship LR. The grouped split told me the truth. If I had posted the `{_pct(_agg(lr_random['tfidf_lr_text'], 'route_accuracy'))}` number and called it done, I would have shipped something that fails on new users, which is exactly the scenario that matters most.

## The Subtype Experiment

I also ran a hierarchical subtype experiment to see whether decomposing the problem helped. Route first, then a route-conditioned subtype classifier inside each route, compared across a few strategies: current heuristic, a global combo LR, LR route then LR subtype, and an oracle condition where I handed the model the true route as a diagnostic upper bound.

{_chart(charts['hierarchy'])}

| Source/account grouped strategy | Full route+subtype accuracy |
| --- | ---: |
| Current heuristic | {_pct(_agg(hierarchy_source['heuristic_current'], 'full_route_subtype_accuracy'))} |
| Global combo LR | {_pct(_agg(hierarchy_source['global_combo_lr'], 'full_route_subtype_accuracy'))} |
| Global route + global subtype LR | {_pct(_agg(hierarchy_source['global_route_global_subtype_lr'], 'full_route_subtype_accuracy'))} |
| LR route -> LR subtype | {_pct(_agg(hierarchy_source['hierarchical_predicted_route_lr'], 'full_route_subtype_accuracy'))} |
| Oracle route -> LR subtype | {_pct(_agg(hierarchy_source['hierarchical_oracle_route_subtype_lr'], 'full_route_subtype_accuracy'))} |

The oracle result was the most useful thing to come out of it. When I gave the subtype model the actual correct route, full route plus subtype accuracy jumped to `{_pct(_agg(hierarchy_source['hierarchical_oracle_route_subtype_lr'], 'full_route_subtype_accuracy'))}`. With LR-predicted routes it was `{_pct(_agg(hierarchy_source['hierarchical_predicted_route_lr'], 'full_route_subtype_accuracy'))}`. With heuristic routes it was `{_pct(_agg(hierarchy_source['heuristic_current'], 'full_route_subtype_accuracy'))}`.

The read on that: subtype quality right now is bottlenecked by route quality, not by anything specific to the subtype model. There is no point building better subtype models until the route layer improves. This is a pattern worth internalizing in hierarchical ML work. Fixing the upstream error is almost always higher leverage than tuning the downstream model. The oracle gap tells you exactly how much headroom you have if you could solve the upstream problem first.

## Synthetic Data: Proceed With Suspicion

With so few examples in sparse classes, 4 rows of `interview_request` and 6 route-level rows of `action_review`, synthetic data was an obvious thing to try. I prompted an LLM to generate realistic job-search emails for underrepresented categories across five prompt iterations.

The consistent problem: synthetic examples can be schema-valid and semantically wrong. The generated emails looked right and passed format validation. But manual review kept finding subtle drift. The most common failure was that positive-scenario emails for application inbox would leak job-alert and promotional language into the body. Right structure, wrong content texture.

{synthetic_failure}

In the table below, "accepted" means the generator produced rows that passed schema and count checks for that prompt run. It does not mean I approved those rows as training data. After the stricter review pass, I treated the synthetic set as a lab artifact, not as a source of production labels.

| Prompt version | Result | Decision |
| --- | --- | --- |
| v1 | 9 accepted rows, then 78 accepted after per-family calls | Too small/generic; semantic failures found |
| v2 | 78 accepted, 10 semantic warnings | Positive scenarios still leaked job-alert/promo cases |
| v3 | 79 generated, 73 accepted, 6 rejected | Best schema behavior, but manual review found subtle semantic drift |
| v4 | 34 accepted, 12 rejected | Few-shot examples exposed failures but output shape regressed |
| v5 | 52 accepted, 10 rejected | Better shape, still not trusted automatically |

A model trained on that learns the wrong boundary, and it learns it confidently because the training data looked clean. Synthetic data is not useless, but it needs a critic gate: another model reviewing outputs for semantic validity, human spot-check, or both. Injecting it into training data without review is how you build classifiers that are wrong in ways that are hard to diagnose later.

I also tested a public Kaggle job-application email dataset as a research-only probe. It contained `{kaggle_meta['rows_total']}` anonymized rows but did not have AppTrail's route/subtype labels. A weak-label application-inbox subtype probe trained on `{kaggle_probe['training_rows']}` rows reached `{_pct(kaggle_probe['accuracy_on_real_application_inbox_rows'])}` accuracy and `{_pct(kaggle_probe['macro_f1_on_real_application_inbox_rows'])}` macro F1 on only `{kaggle_probe['real_eval_rows']}` real application-inbox rows. Useful signal, not production evidence.

## The LLM Layer (and Why It Is Not the Default)

Raw Gmail content is messy in ways that matter. Names, phone numbers, physical addresses, private scheduling links, quoted thread history going back months. Sending every email to an external model expands the privacy surface, adds latency on every classification, and costs money at scale.

So the LLM in AppTrail's classifier is a second-pass adjudicator, not the primary classifier. Local classification runs first. Only ambiguous cases are considered for escalation. Before any model call, preflight minimizes the body, strips signatures and quoted text, redacts sensitive values, scans for redaction leaks and injection patterns, and blocks the call if the prompt is not safe enough.

In the policy-corrected label set, `{_pct(preflight['would_call_llm'] / preflight['labeled'] if preflight['labeled'] else 0)}` of rows were LLM-eligible and `{preflight['preflight_blocked']}` were blocked in that artifact. The block paths exist and are tested; the zero count just means the eligible slice happened to be clean enough to pass. The important point is that the adjudication model never sees raw inbox content, and even a model result still has to pass the deterministic side-effect policy before it can touch application state.

## What Is Actually in Production

Current production decision: heuristics in production, LR kept in offline shadow evaluation, LLM for ambiguous preflight-safe cases only.

On the current `{current_labeled}`-row policy-corrected eval set:

| Metric | Value |
| --- | ---: |
| Route accuracy | {_pct(lr['eval']['baseline_full']['route_accuracy'])} |
| Application-inbox recall | {_pct(lr['eval']['baseline_full']['application_inbox_recall'])} |
| Conversation recall | {_pct(lr['eval']['baseline_full']['conversation_recall'])} |
| LLM escalation rate | {_pct(current_eval['would_call_llm_rate'])} |
| Original diagnostic unwanted stored rows after route-first | {route_first['new_unwanted_store_count']} |

Not a perfect classifier. Conversation recall at `{_pct(lr['eval']['baseline_full']['conversation_recall'])}` is a real gap I know about. I also still track offline mutation-risk flags separately, so I am not claiming lifecycle risk is solved globally.

But the failure mode it most needed to avoid in the first version -- marketing and job-board messages flooding application workflows -- was eliminated on the diagnostic subset. That is why heuristics stay in production for now. The failure modes they avoid are the ones that break product trust fastest.

## What Has to Change Before I Promote a Learned Model

I know exactly what the promotion gate looks like. Worth writing down explicitly because it is easy to keep moving the bar in your head without committing it anywhere.

For a learned route model to replace the heuristic in production, I would need one gate that combines model quality and data coverage:

- Source/account grouped route accuracy has to match or beat the heuristic baseline
- Source/account grouped macro F1 has to be materially above it
- Application-inbox recall has to stay high
- Conversation recall has to improve
- False-positive lifecycle mutation risk stays near zero
- The model produces calibrated confidence or explicit abstention
- 1,000+ real labeled Gmail examples across multiple account types
- 200+ per major route where feasible
- 50-100+ per key sparse subtypes
- A fresh holdout not used for any tuning decisions

I am at `{total_labeled}` usable labels right now. The bottleneck is not model architecture. It is data diversity. A more complex model would just find better ways to overfit to the three account groups I have labeled so far.

## The Actual Takeaway

Looking back at everything I ran, the diagnostic labeling, the route-first rewrite, the LR shadow experiments, the subtype hierarchy, the synthetic data probes, the useful work was not model selection.

It was identifying which routing errors had product side effects versus which ones were just metrics noise. It was designing evaluation splits that actually reflected production conditions. It was iterating the architecture before touching the model. It was building a label methodology out of a live running system. And it was not shipping something that only looked good under an easy split.

When you are building solo with no existing training data, heuristics are not a failure to do ML. They are the current best decision policy given the actual constraints: label scarcity, distribution shift, latency, cost, privacy, and the fact that wrong answers have real consequences in the product.

The same evaluation loop that tells you heuristics are right today also tells you exactly when that changes. That is the part I think gets skipped most often. Not just "which model should I use?" but: what evidence would actually change my answer?

Define that before you run the experiments. It saves you from convincing yourself a random split is good enough.

<footer style="margin-top:0.34in;padding-top:0.18in;border-top:1px solid #d8e3e8;color:#455a64;">
  <p style="margin:0 0 0.1in 0;"><strong>Colby Reichenbach</strong> -- building AppTrail and writing about applied AI systems that survive real product constraints.</p>
  <p style="margin:0;display:flex;gap:0.14in;align-items:center;flex-wrap:wrap;">
    <a href="https://www.linkedin.com/in/colby-reichenbach/" style="display:inline-flex;align-items:center;gap:0.055in;color:#0d5f73;text-decoration:none;">
      <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style="vertical-align:-2px;"><rect x="2" y="2" width="20" height="20" rx="3" fill="#0A66C2"/><text x="7" y="17" font-size="12" font-family="Arial, sans-serif" font-weight="700" fill="#ffffff">in</text></svg>
      LinkedIn
    </a>
    <a href="https://colbyrreichenbach.github.io/" style="display:inline-flex;align-items:center;gap:0.055in;color:#0d5f73;text-decoration:none;">
      <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style="vertical-align:-2px;"><circle cx="12" cy="12" r="9" fill="none" stroke="#0d5f73" stroke-width="2"/><path d="M3 12h18M12 3c2.4 2.7 3.6 5.7 3.6 9S14.4 18.3 12 21M12 3C9.6 5.7 8.4 8.7 8.4 12S9.6 18.3 12 21" fill="none" stroke="#0d5f73" stroke-width="1.6" stroke-linecap="round"/></svg>
      Portfolio
    </a>
  </p>
</footer>
"""


def _linkedin_post() -> str:
    return """# LinkedIn Draft

Sometimes the right AI decision is not "train a bigger model."

I spent the last few cycles rebuilding and evaluating the Gmail classifier inside AppTrail, my job-search workflow product.

The classifier has a deceptively simple job: decide whether an email is noise, a job alert, a recruiter conversation, an application update, or something that needs review.

But the real problem was not just label prediction. It was product routing.

If the system mistakes a job-board promo for an application update, it pollutes the user's workflow. If it filters out a recruiter reply, the user may miss an opportunity. So I treated this as a business-decision system first and an ML system second.

What I did:

- manually reviewed 300+ real Gmail priority rows across two labeling waves
- built route/subtype labels around product behavior, not generic email categories
- found that phrases like "apply" and "onsite" were causing high-confidence false positives
- rewrote the classifier to route first, then assign subtype
- tested TF-IDF + Logistic Regression as a shadow route model
- tested a route-conditioned subtype architecture
- tested synthetic LLM-generated training examples
- reviewed an external Kaggle job-email dataset as a research-only probe

The result:

- route-first heuristics dramatically reduced unwanted stored workflow rows
- LR looked great on random split: 94.2% route accuracy / 91.6% macro F1
- but LR dropped under source/account grouped testing: 55.9% route accuracy / 22.0% macro F1
- route-conditioned subtype models looked promising only when the route was already correct
- synthetic data was schema-valid but still semantically risky without human/critic review

The decision:

Keep heuristics in production.
Keep LR in shadow.
Use LLMs only for ambiguous, preflight-safe adjudication.
Collect more real labels before promoting a learned model.

The lesson:

ML is not always the first place to look. The first place to look is the business decision, the failure mode, the available data, and the cost of being wrong.

That is where applied AI engineering gets interesting: not picking the fanciest model, but building the evidence loop that tells you when a model is actually ready.
"""


def main() -> None:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    prior = _labeled_count(PRIOR_LABELS)
    current = _labeled_count(CURRENT_LABELS)
    current_rows = _load_labeled_rows(CURRENT_LABELS)
    route_first = _load_json(ROUTE_FIRST_METRICS)
    current_eval = _load_json(CURRENT_LABEL_EVAL)
    lr = _load_json(LR_METRICS)
    hierarchy = _load_json(HIERARCHY_METRICS)
    charts = _write_charts(route_first, current_eval, lr, hierarchy)

    OUTPUT_REPORT.write_text(
        _report(prior, current, current_rows, route_first, current_eval, lr, hierarchy, charts),
        encoding="utf-8",
    )
    OUTPUT_LINKEDIN.write_text(_linkedin_post(), encoding="utf-8")
    print(f"Wrote {OUTPUT_REPORT}")
    print(f"Wrote {OUTPUT_LINKEDIN}")
    print(f"Wrote charts to {CHART_DIR}")


if __name__ == "__main__":
    main()
