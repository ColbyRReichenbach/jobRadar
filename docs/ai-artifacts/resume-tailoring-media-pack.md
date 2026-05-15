# Resume Tailoring Media Pack

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
