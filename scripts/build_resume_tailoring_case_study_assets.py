#!/usr/bin/env python3
"""Build SVG/media assets for the resume-tailoring case study."""

from __future__ import annotations

import html
import json
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs/ai-artifacts/resume-tailoring-case-study-assets"
MEDIA_MD = ROOT / "docs/ai-artifacts/resume-tailoring-media-pack.md"
PROMPT_RUN_DIR = ROOT / "docs/ai-artifacts/generated/resume-tailoring-prompt-experiment"


COLORS = {
    "ink": "#102027",
    "muted": "#607d8b",
    "grid": "#d7dee2",
    "soft": "#f6f8f9",
    "blue": "#2563eb",
    "teal": "#00897b",
    "orange": "#f59e0b",
    "red": "#dc2626",
    "purple": "#7c3aed",
    "green": "#16a34a",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="32" y="40" font-size="24" font-weight="700" fill="{COLORS["ink"]}">{esc(title)}</text>',
    ]


def add_wrapped_text(
    out: list[str],
    text: str,
    x: int,
    y: int,
    *,
    width: int = 44,
    line_height: int = 17,
    size: int = 13,
    fill: str | None = None,
    weight: str = "400",
) -> int:
    fill = fill or COLORS["ink"]
    for line in wrap(text, width):
        out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}">{esc(line)}</text>')
        y += line_height
    return y


def workflow_svg() -> None:
    width, height = 1180, 480
    out = svg_header(width, height, "Evidence-grounded resume assistant architecture")
    out.append(f'<text x="32" y="68" font-size="13" fill="{COLORS["muted"]}">The product moved from direct rewriting to verified evidence retrieval plus user-approved suggestions.</text>')

    steps = [
        ("1", "Resume + JD + project docs", "User inputs are scoped and redacted before any model path."),
        ("2", "Evidence cards", "Project material is converted into small, resume-safe claims."),
        ("3", "Requirement extraction", "The JD is split into concrete requirements before matching."),
        ("4", "Retrieval + support check", "Cards are retrieved, then checked against each requirement."),
        ("5", "Suggested bullets + gaps", "Only supported evidence becomes suggestions; weak areas are shown."),
    ]
    x, y = 38, 112
    box_w, box_h, gap = 200, 170, 28
    for idx, title, desc in steps:
        out.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" fill="{COLORS["soft"]}" stroke="#dbe4ea"/>')
        out.append(f'<circle cx="{x+24}" cy="{y+30}" r="15" fill="{COLORS["blue"]}"/>')
        out.append(f'<text x="{x+19}" y="{y+35}" font-size="14" font-weight="700" fill="#ffffff">{idx}</text>')
        add_wrapped_text(out, title, x + 48, y + 35, width=19, line_height=18, size=15, weight="700")
        add_wrapped_text(out, desc, x + 18, y + 84, width=25, line_height=17, size=12, fill="#455a64")
        if idx != "5":
            ax = x + box_w + 6
            ay = y + 83
            out.append(f'<line x1="{ax}" y1="{ay}" x2="{ax+gap-10}" y2="{ay}" stroke="{COLORS["muted"]}" stroke-width="2"/>')
            out.append(f'<path d="M {ax+gap-10} {ay-5} L {ax+gap-2} {ay} L {ax+gap-10} {ay+5}" fill="none" stroke="{COLORS["muted"]}" stroke-width="2"/>')
        x += box_w + gap

    out.append(f'<rect x="120" y="340" width="940" height="88" rx="12" fill="#fff7ed" stroke="#fed7aa"/>')
    out.append(f'<text x="146" y="374" font-size="17" font-weight="700" fill="#9a3412">Product constraint</text>')
    add_wrapped_text(
        out,
        "The LLM can still help with wording, but only after AppTrail retrieves verified evidence and preserves unsupported gaps.",
        146,
        402,
        width=118,
        line_height=17,
        size=13,
        fill="#7c2d12",
    )
    out.append("</svg>")
    write(ASSET_DIR / "evidence-grounded-resume-workflow.svg", "\n".join(out))


def prompt_comparison_svg() -> None:
    width, height = 1180, 560
    out = svg_header(width, height, "Prompt-only vs engineered vs evidence-grounded")
    out.append(f'<text x="32" y="68" font-size="13" fill="{COLORS["muted"]}">The same resume can produce very different product risk depending on whether claims need evidence.</text>')

    cards = [
        (
            "Lazy prompt",
            COLORS["red"],
            "Make me look like a strong fit.",
            [
                "Fluent rewritten resume",
                "Adds exact-match claims",
                "Does not show unsupported gaps",
                "High risk on near-miss roles",
            ],
            "Example: added Tableau and customer-acquisition forecasting for a DraftKings Analyst I role.",
        ),
        (
            "Engineered prompt",
            COLORS["orange"],
            "Preserve factual accuracy.",
            [
                "Flags weak requirements",
                "Fewer unsupported claims",
                "Still only knows resume text",
                "Cannot cite project artifacts",
            ],
            "Example: called out Tableau, Databricks/Airflow, and marketing requirements as weak or unsupported.",
        ),
        (
            "Evidence-grounded assistant",
            COLORS["teal"],
            "Only suggest what evidence supports.",
            [
                "Retrieves project facts",
                "Cites evidence IDs",
                "Can abstain",
                "Lower recall today, safer output",
            ],
            "Example: no verified marketing evidence-grounded bullets for the Anthropic near-miss.",
        ),
    ]
    x, y = 42, 108
    card_w, card_h = 340, 370
    for title, color, subtitle, bullets, example in cards:
        out.append(f'<rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="12" fill="#ffffff" stroke="#dbe4ea"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{card_w}" height="64" rx="12" fill="{color}"/>')
        out.append(f'<text x="{x+22}" y="{y+38}" font-size="22" font-weight="700" fill="#ffffff">{esc(title)}</text>')
        add_wrapped_text(out, subtitle, x + 22, y + 96, width=34, line_height=19, size=15, weight="700")
        by = y + 150
        for bullet in bullets:
            out.append(f'<circle cx="{x+28}" cy="{by-4}" r="4" fill="{color}"/>')
            add_wrapped_text(out, bullet, x + 42, by, width=34, line_height=17, size=13, fill="#263238")
            by += 38
        out.append(f'<rect x="{x+18}" y="{y+298}" width="{card_w-36}" height="52" rx="8" fill="{COLORS["soft"]}"/>')
        add_wrapped_text(out, example, x + 32, y + 320, width=38, line_height=15, size=12, fill="#455a64")
        x += card_w + 36
    out.append("</svg>")
    write(ASSET_DIR / "prompt-output-comparison.svg", "\n".join(out))


def prompt_metrics_svg() -> None:
    width, height = 1040, 520
    out = svg_header(width, height, "Prompt run cost, latency, and token footprint")
    out.append(f'<text x="32" y="68" font-size="13" fill="{COLORS["muted"]}">Single resume/JD runs are cheap; the product issue is scale, repeat runs, context bloat, and factuality.</text>')
    rows = [
        ("DraftKings lazy", 1559, 8.5, "$0.01", COLORS["red"]),
        ("DraftKings engineered", 2021, 7.8, "$0.02", COLORS["orange"]),
        ("Marketing lazy", 1703, 9.7, "$0.01", COLORS["red"]),
        ("Marketing engineered", 2029, 8.2, "$0.02", COLORS["orange"]),
    ]
    left, top = 230, 120
    max_tokens = max(r[1] for r in rows)
    max_latency = max(r[2] for r in rows)
    out.append(f'<text x="{left}" y="{top-18}" font-size="13" fill="{COLORS["muted"]}">Total tokens</text>')
    out.append(f'<text x="680" y="{top-18}" font-size="13" fill="{COLORS["muted"]}">Latency</text>')
    for i, (label, tokens, latency, cost, color) in enumerate(rows):
        y = top + i * 82
        out.append(f'<text x="36" y="{y+22}" font-size="14" font-weight="700" fill="{COLORS["ink"]}">{esc(label)}</text>')
        bar_w = int(tokens / max_tokens * 380)
        out.append(f'<rect x="{left}" y="{y}" width="380" height="28" rx="6" fill="#eef2f5"/>')
        out.append(f'<rect x="{left}" y="{y}" width="{bar_w}" height="28" rx="6" fill="{color}"/>')
        out.append(f'<text x="{left+bar_w+10}" y="{y+20}" font-size="13" fill="#263238">{tokens:,}</text>')
        lat_w = int(latency / max_latency * 190)
        out.append(f'<rect x="680" y="{y}" width="190" height="28" rx="6" fill="#eef2f5"/>')
        out.append(f'<rect x="680" y="{y}" width="{lat_w}" height="28" rx="6" fill="{COLORS["blue"]}"/>')
        out.append(f'<text x="{880}" y="{y+20}" font-size="13" fill="#263238">{latency:.1f}s</text>')
        out.append(f'<text x="954" y="{y+20}" font-size="13" font-weight="700" fill="{COLORS["ink"]}">{cost}</text>')
    out.append(f'<text x="36" y="478" font-size="12" fill="{COLORS["muted"]}">Pricing uses local app config; verify current provider pricing before publication.</text>')
    out.append("</svg>")
    write(ASSET_DIR / "prompt-token-latency-cost.svg", "\n".join(out))


def retrieval_metrics_svg() -> None:
    width, height = 1180, 560
    out = svg_header(width, height, "Retrieval quality: model upgrade was not the main fix")
    out.append(f'<text x="32" y="68" font-size="13" fill="{COLORS["muted"]}">Reviewed label set: 25 JD cases, 118 requirements, 88 citation-labeled requirements, 30 unsupported.</text>')
    rows = [
        ("Raw lexical", 25.8, 35.3, 46.7, 24, COLORS["purple"]),
        ("Lexical + support", 23.2, 42.1, 26.7, 20, COLORS["teal"]),
        ("Embedding + support", 23.3, 42.2, 26.7, 761, COLORS["blue"]),
        ("Hybrid + support", 24.7, 43.8, 26.7, 721, COLORS["orange"]),
    ]
    x0, y0 = 64, 125
    group_gap = 265
    bar_w = 46
    max_metric = 50
    chart_h = 240
    labels = [("Recall@3", 0), ("Precision@3", 1), ("False support", 2)]
    for gi, (name, recall, precision, false_support, latency, color) in enumerate(rows):
        x = x0 + gi * group_gap
        out.append(f'<text x="{x}" y="{y0-20}" font-size="15" font-weight="700" fill="{COLORS["ink"]}">{esc(name)}</text>')
        vals = [recall, precision, false_support]
        for bi, (metric_name, _) in enumerate(labels):
            val = vals[bi]
            h = int(val / max_metric * chart_h)
            bx = x + bi * (bar_w + 18)
            by = y0 + chart_h - h
            fill = color if metric_name != "False support" else COLORS["red"]
            out.append(f'<rect x="{bx}" y="{y0}" width="{bar_w}" height="{chart_h}" fill="#f1f5f9"/>')
            out.append(f'<rect x="{bx}" y="{by}" width="{bar_w}" height="{h}" fill="{fill}"/>')
            out.append(f'<text x="{bx+bar_w/2}" y="{by-8}" text-anchor="middle" font-size="12" font-weight="700" fill="#263238">{val:.1f}%</text>')
            out.append(f'<text x="{bx+bar_w/2}" y="{y0+chart_h+20}" text-anchor="middle" font-size="11" fill="{COLORS["muted"]}">{metric_name.split("@")[0]}</text>')
        out.append(f'<text x="{x}" y="{y0+chart_h+54}" font-size="13" fill="{COLORS["muted"]}">p95 latency: <tspan font-weight="700" fill="{COLORS["ink"]}">{latency} ms</tspan></text>')
    out.append(f'<rect x="68" y="470" width="1040" height="54" rx="10" fill="#ecfdf5" stroke="#bbf7d0"/>')
    add_wrapped_text(
        out,
        "Embeddings/hybrid gave small recall and precision lifts, but false support stayed flat and latency rose sharply. The bottleneck is evidence/support quality, not just model class.",
        92,
        500,
        width=132,
        line_height=17,
        size=13,
        fill="#14532d",
    )
    out.append("</svg>")
    write(ASSET_DIR / "retrieval-metrics-comparison.svg", "\n".join(out))


def support_distribution_svg() -> None:
    width, height = 920, 360
    out = svg_header(width, height, "Reviewed evidence labels")
    out.append(f'<text x="32" y="68" font-size="13" fill="{COLORS["muted"]}">Manual review kept 83 evidence cards and labeled 118 JD requirements.</text>')
    data = [("direct", 24, COLORS["green"]), ("partial", 64, COLORS["orange"]), ("none", 30, COLORS["red"])]
    total = sum(v for _, v, _ in data)
    x, y, w, h = 80, 138, 760, 58
    current = x
    for label, value, color in data:
        seg_w = value / total * w
        out.append(f'<rect x="{current}" y="{y}" width="{seg_w}" height="{h}" fill="{color}"/>')
        out.append(f'<text x="{current+seg_w/2}" y="{y+35}" text-anchor="middle" font-size="15" font-weight="700" fill="#ffffff">{value}</text>')
        current += seg_w
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#cfd8dc"/>')
    ly = 245
    lx = 180
    for label, value, color in data:
        pct = value / total * 100
        out.append(f'<circle cx="{lx}" cy="{ly}" r="8" fill="{color}"/>')
        out.append(f'<text x="{lx+16}" y="{ly+5}" font-size="14" fill="{COLORS["ink"]}">{label}: {value} ({pct:.1f}%)</text>')
        lx += 210
    out.append(f'<text x="80" y="320" font-size="13" fill="{COLORS["muted"]}">This is enough for failure discovery and product direction, not statistical proof.</text>')
    out.append("</svg>")
    write(ASSET_DIR / "support-label-distribution.svg", "\n".join(out))


def output_excerpts_svg() -> None:
    width, height = 1180, 680
    out = svg_header(width, height, "Actual output excerpts: fluent vs supported")
    out.append(f'<text x="32" y="68" font-size="13" fill="{COLORS["muted"]}">Redacted prompt outputs and evidence-grounded suggestions from the local run artifacts.</text>')
    cards = [
        (
            "Lazy prompt resume rewrite",
            COLORS["red"],
            [
                "Tableau",
                "commitment to improving customer acquisition forecasting",
                "enhancing forecast accuracy and business visibility",
            ],
            "Fluent, but the exact tool and domain claims are not directly supported.",
        ),
        (
            "Engineered prompt risk notes",
            COLORS["orange"],
            [
                "The resume does not mention Tableau.",
                "Databricks or Airflow are not mentioned in the resume.",
                "Marketing performance / GTM strategy should not be claimed.",
            ],
            "Better behavior: it calls out gaps instead of filling all of them.",
        ),
        (
            "Evidence-grounded suggestion",
            COLORS["teal"],
            [
                "Produced readable model evidence artifacts including PPE10, MdAPE, R-squared...",
                "[evidence: CUR-SPEC-MODEL-EVIDENCE]",
                "No verified evidence-grounded bullets for the marketing near-miss.",
            ],
            "Less magical, but traceable and able to abstain.",
        ),
    ]
    x, y = 42, 118
    card_w, card_h = 340, 470
    for title, color, lines, footer in cards:
        out.append(f'<rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="12" fill="#ffffff" stroke="#dbe4ea"/>')
        out.append(f'<text x="{x+20}" y="{y+36}" font-size="18" font-weight="700" fill="{color}">{esc(title)}</text>')
        out.append(f'<line x1="{x+20}" y1="{y+55}" x2="{x+card_w-20}" y2="{y+55}" stroke="#e5edf2"/>')
        yy = y + 92
        for line in lines:
            out.append(f'<rect x="{x+20}" y="{yy-22}" width="{card_w-40}" height="84" rx="8" fill="{COLORS["soft"]}"/>')
            yy = add_wrapped_text(out, line, x + 36, yy, width=36, line_height=17, size=13, fill="#263238")
            yy += 42
        out.append(f'<rect x="{x+20}" y="{y+390}" width="{card_w-40}" height="58" rx="8" fill="#fff7ed" stroke="#fed7aa"/>')
        add_wrapped_text(out, footer, x + 36, y + 416, width=36, line_height=16, size=12, fill="#7c2d12")
        x += card_w + 36
    out.append("</svg>")
    write(ASSET_DIR / "actual-output-excerpts.svg", "\n".join(out))


def media_pack_md() -> None:
    content = """# Resume Tailoring Media Pack

Generated: 2026-05-14

Use this as the source list for article screenshots, carousel slides, or PDF callouts. All prompt inputs used the redacted resume text produced by `scripts/run_resume_prompt_tailoring_experiment.py`.

## Visual Assets

| Asset | Use |
| --- | --- |
| `docs/ai-artifacts/resume-tailoring-case-study-assets/evidence-grounded-resume-workflow.svg` | Architecture diagram for the evidence-grounded assistant. |
| `docs/ai-artifacts/resume-tailoring-case-study-assets/prompt-output-comparison.svg` | Three-way comparison: lazy prompt, engineered prompt, evidence-grounded assistant. |
| `docs/ai-artifacts/resume-tailoring-case-study-assets/prompt-token-latency-cost.svg` | Token/latency/cost snapshot for the four live prompt runs. |
| `docs/ai-artifacts/resume-tailoring-case-study-assets/support-label-distribution.svg` | Manual review label mix. |
| `docs/ai-artifacts/resume-tailoring-case-study-assets/retrieval-metrics-comparison.svg` | Retrieval metrics across lexical, embedding, and hybrid runs. |
| `docs/ai-artifacts/resume-tailoring-case-study-assets/actual-output-excerpts.svg` | Media-friendly excerpts from actual outputs. |

## Actual Prompt Output Paths

| Case | Mode | Clean PDF | Source markdown |
| --- | --- | --- | --- |
| DraftKings Analyst I | lazy | `docs/ai-artifacts/resume-tailoring-generated-resumes/draftkings-analyst-i-lazy.pdf` | `docs/ai-artifacts/resume-tailoring-generated-resumes/draftkings-analyst-i-lazy.md` |
| DraftKings Analyst I | engineered | `docs/ai-artifacts/resume-tailoring-generated-resumes/draftkings-analyst-i-engineered.pdf` | `docs/ai-artifacts/resume-tailoring-generated-resumes/draftkings-analyst-i-engineered.md` |
| Anthropic Marketing | lazy | `docs/ai-artifacts/resume-tailoring-generated-resumes/anthropic-marketing-near-miss-lazy.pdf` | `docs/ai-artifacts/resume-tailoring-generated-resumes/anthropic-marketing-near-miss-lazy.md` |
| Anthropic Marketing | engineered | `docs/ai-artifacts/resume-tailoring-generated-resumes/anthropic-marketing-near-miss-engineered.pdf` | `docs/ai-artifacts/resume-tailoring-generated-resumes/anthropic-marketing-near-miss-engineered.md` |

Raw prompt-run outputs remain under `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/`, which is intentionally treated as a scratch/output directory. Re-render the clean PDFs with `python3 scripts/render_resume_generated_output_pdfs.py`.

## Evidence-Grounded Suggestion Paths

| Artifact | Use |
| --- | --- |
| `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-openai-hybrid/generated_bullets.csv` | Full reviewed OpenAI hybrid output table with prompt-only rows and evidence-grounded rows. |
| `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-openai-hybrid/evidence_cards.csv` | Evidence card source table for the cited `CUR-*` IDs. |
| `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-openai-hybrid/metrics.json` | Metrics for the reviewed OpenAI hybrid run. |

## Report-Ready Excerpts

### Lazy DraftKings Prompt

```text
Tableau
commitment to improving customer acquisition forecasting
enhancing forecast accuracy and business visibility
```

Read: fluent and aligned, but these are exact-match claims the resume text does not directly prove.

### Engineered DraftKings Prompt

```text
Experience with Tableau or similar data visualization platforms: The resume does not mention Tableau.
Specific experience with Databricks or Airflow: These tools are not mentioned in the resume.
```

Read: stronger prompt behavior. It names weak areas instead of filling every gap.

### Lazy Anthropic Marketing Prompt

```text
Causal Inference
Designed experiments and causal inference studies...
Analyzed performance data to define metrics and guide strategic decisions...
```

Read: the near-miss role exposes the product risk. The output makes marketing/channel claims that are not supported by the source resume.

### Evidence-Grounded Suggestion

```text
Produced readable model evidence artifacts including overall test rows, PPE10, MdAPE,
R-squared, segment performance, price-tier performance, train/test row counts, model version,
artifact tag, and training timestamp.
[evidence: CUR-SPEC-MODEL-EVIDENCE]
```

Read: narrower than the prompt-only resume, but traceable to a cited evidence card.

## Recommended Slide Order

1. Problem: prompt-only resume tailoring can quietly stretch the truth.
2. Lazy prompt output: polished but unsupported claims.
3. Engineered prompt output: safer but still not project-grounded.
4. Architecture: evidence-grounded assistant.
5. Retrieval metrics: embeddings did not solve false support.
6. Product pivot: guided suggestions and explicit gaps instead of full automatic rewriting.
"""
    write(MEDIA_MD, content)


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    workflow_svg()
    prompt_comparison_svg()
    prompt_metrics_svg()
    support_distribution_svg()
    retrieval_metrics_svg()
    output_excerpts_svg()
    media_pack_md()
    print(f"Wrote assets to {ASSET_DIR}")
    print(f"Wrote media pack to {MEDIA_MD}")


if __name__ == "__main__":
    main()
