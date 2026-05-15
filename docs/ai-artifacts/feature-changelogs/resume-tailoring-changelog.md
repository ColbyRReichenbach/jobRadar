# Resume Tailoring Evidence Retrieval Changelog

## Architecture Decision Context

Resume tailoring is not just a writing problem. A prompt-only resume tailorer can make a bullet sound polished while quietly inventing experience, overstating a weak project, or leaking private contact data. For AppTrail, the safer architecture is evidence-grounded:

```text
resume / project docs / job description
  -> privacy and format preflight
  -> resume-safe evidence cards
  -> JD requirement extraction and cleaning
  -> retrieval over evidence cards
  -> pairwise support verification
  -> generate only from verified evidence IDs
  -> abstain when support is weak
```

The current conclusion is not that resume tailoring is a dead end. The conclusion is that automatic generation should wait until the evidence-card and citation layer is reliable.

## Current Implementation

Current eval-only code:

- `backend/services/evals/resume_tailoring_eval.py`
- `backend/services/evals/resume_project_ingest.py`
- `backend/services/evals/resume_requirement_cleaner.py`
- `backend/services/evals/resume_support_verifier.py`
- `scripts/run_resume_tailoring_evidence_eval.py`
- `scripts/build_resume_tailoring_jd_label_pack.py`
- `scripts/convert_resume_jd_label_pack_to_eval_cases.py`
- `scripts/build_resume_parent_citation_labels.py`
- `scripts/build_resume_curated_evidence_labels.py`
- `scripts/build_resume_curated_review_queues.py`
- `scripts/analyze_resume_retrieval_eval.py`

Current product-facing boundary:

- This is still offline/eval work.
- Production resume tailoring should not be promoted from the current retriever.
- The safest near-term feature shape is an evidence-grounded resume assistant: show matched evidence, support status, suggested bullet candidates, and explicit gaps.

## Baseline Failure Mode

Prompt-only generation is the control condition. Across the current artifacts, prompt-only generation repeatedly produced a `100.0%` unsupported-bullet rate because it does not cite verified evidence IDs. Evidence-grounded generation stayed at `0.0%` unsupported bullets in these evals because it only generated when accepted evidence intersected reviewed expected evidence.

That safety result is useful, but it does not solve retrieval quality. If retrieval misses valid evidence, the system abstains too often. If retrieval returns weak evidence, the verifier has to block it.

## Evidence Card Experiments

The first project-doc extraction used automated section/atomic splitting from six local project reports:

- AppTrail/jobRadar
- AiBS ABS Observatory
- Augusta Defended
- Pulse Tracker
- ShelfOps
- S.P.E.C. NYC

The reports were strong enough to support resume-safe evidence, but the automated extractor created cards that were often too broad, too mechanical, or too generic. Examples of weak representation included cards like "The UI includes..." or broad cards mixing ETL, AI, frontend, governance, and analytics in one claim.

The next iteration added curated cards in:

- `docs/ai-artifacts/resume-tailoring-curated-evidence/`

Policy for curated cards:

- Keep each claim small enough to cite.
- Preserve the source-report evidence boundary.
- Avoid claiming production outcomes where the report only supports prototype, benchmark, artifact, or local implementation evidence.
- Split broad sections into line-level capabilities: ETL, model evaluation, governance, privacy controls, integrations, UI surfaces, and operational controls.
- Keep broad project-level skills in `project_tags`.
- Keep per-card `evidence_skills` narrow so retrieval/support does not treat every card as proving every skill used anywhere in the project.

## Current Eval Result

Expansion v3 uses 25 job cases and 118 requirement rows. The curated label view is still machine-derived from existing reviewed parent labels plus the deterministic support verifier, so it is diagnostic rather than final human truth.

Comparison:

| Run | Citation labels | Citation recall@3 | Citation precision@3 | Unsupported false support | Unsupported rows with returns | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Auto atomic lexical + support | 61 | 19.1% | 35.0% | 23.8% | 5 | 27 ms |
| Auto atomic parent-child + support | 61 | 24.6% | 38.8% | 23.8% | 5 | 36 ms |
| Auto atomic OpenAI embedding + support | 61 | 21.2% | 38.2% | 23.8% | 5 | 646 ms |
| Curated raw lexical | 69 | 16.2% | 7.6% | 100.0% | 49 | 12 ms |
| Curated lexical + support | 69 | 38.3% | 63.4% | 6.1% | 3 | 24 ms |
| Curated OpenAI embedding + support | 69 | 37.9% | 61.3% | 10.2% | 5 | 589 ms |
| Curated OpenAI hybrid + support | 69 | 40.9% | 62.6% | 10.2% | 5 | 495 ms |

Interpretation:

- Cleaner evidence cards helped more than switching to embeddings.
- Splitting broad `project_tags` from narrow `evidence_skills` reduced skill leakage before manual review.
- Curated lexical + requirement cleaner + support verifier is the best conservative diagnostic path: highest precision, lowest false-support rate, and lowest latency.
- OpenAI hybrid has slightly higher recall, but added significant latency and a higher false-support rate.
- This is evidence that representation is currently higher leverage than model complexity.

## Architecture Decision

Current decision:

```text
Do not promote automatic resume generation yet.
Do build evidence matching and safe bullet suggestions.
Do keep lexical + cleaner/support as the cheap baseline.
Do compare embeddings only as a measured challenger.
Do not try transformers/cross-encoders until candidate-pool EDA proves ranking is the bottleneck.
```

The immediate product path should be:

```text
curated evidence cards
  -> human-reviewed citation labels
  -> JD requirement extraction
  -> lexical retrieval + support verifier
  -> suggested bullets only from verified evidence
  -> "no evidence" gaps where the user should not claim a requirement
```

## Remaining Gaps

- The curated evidence cards need human review.
- The curated JD citation labels are machine-derived and need human review.
- The evidence-card authoring workflow is not yet a product surface.
- The support verifier is deterministic and useful for evals, but not a final semantic judge.
- The eval set is still small and should be treated as failure discovery/regression evidence, not statistical proof.

## Next Iteration

The review queues now exist and the two compact queues have been reviewed. This was not a restart of the JD labels; it was a review pass over the new evidence-card and citation layer.

| File | Rows | Use |
| --- | ---: | --- |
| `curated_evidence_card_review_queue.csv` | 83 | Reviewed: all 83 kept after source-backed card/skill check. |
| `curated_citation_requirement_review_queue.csv` | 118 | Reviewed: 25 accepted, 63 edited, 30 marked none, 0 left unresolved. |
| `curated_citation_candidate_review_queue.csv` | 776 | Deep audit queue for hard requirement-card matches. |

Reviewed support label counts:

| Label | Count |
| --- | ---: |
| `direct` | 24 |
| `partial` | 64 |
| `none` | 30 |
| blank / unresolved | 0 |

The second review pass converted the 9 collaboration-heavy unresolved rows to `partial` only where the evidence supported the substantive capability after stripping phrases like "partner with" or "work with." The review notes still preserve the caveat when direct stakeholder partnership, A/B-test ownership, executive communication, or the exact business domain is not evidenced.

Reviewed rerun:

| Run | Citation labels | Citation recall@3 | Citation precision@3 | Unsupported false support | Unsupported rows with returns | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Reviewed raw lexical | 88 | 25.8% | 35.3% | 46.7% | 14 | 24 ms |
| Reviewed lexical + cleaner/support | 88 | 23.2% | 42.1% | 26.7% | 8 | 20 ms |
| Reviewed OpenAI embedding + cleaner/support | 88 | 23.3% | 42.2% | 26.7% | 8 | 761 ms |
| Reviewed OpenAI hybrid + cleaner/support | 88 | 24.7% | 43.8% | 26.7% | 8 | 721 ms |

Read: hybrid gives a small lift over lexical + support, but it does not reduce false support and it is much slower. The current bottleneck is still evidence/support quality, not model class.

Next step:

1. Inspect the 8 unsupported false-return rows.
2. Bucket the 38-45 supported misses from the lexical/hybrid EDA reports.
3. Only consider reranking/cross-encoder support if the correct curated citation is present in the candidate pool but ranked below weaker evidence.

## Source Artifacts

- `docs/ai-artifacts/resume-tailoring-decision-log.md`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/`
- `scripts/apply_resume_curated_review_labels.py`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence/summary.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_evidence_cards.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_jd_cases_labeled.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed/curated_jd_cases_reviewed.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/README.md`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/summary.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_evidence_card_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_citation_requirement_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_citation_candidate_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/manual_review_summary.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-lexical-support/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-openai-embedding/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-openai-hybrid/metrics.json`

## Prompt-Only Tailoring Control

Added a prompt-only control run so the later article can compare three behaviors:

```text
lazy prompt-only rewrite
  -> fluent but can invent exact-match experience

engineered prompt-only rewrite
  -> safer and more transparent, but still limited to the resume text

evidence-grounded assistant
  -> lower recall today, but can cite supported project facts and abstain
```

What changed:

- Added `scripts/run_resume_prompt_tailoring_experiment.py`.
- Ran two prompts against the same redacted resume input:
  - `lazy`: generic ATS/tailoring prompt.
  - `engineered`: factual-accuracy prompt with changed-bullet evidence, unsupported requirements, and risk notes.
- Tested a close-fit Ironclad Senior Staff Data Scientist, AI case and a near-miss Anthropic Data Scientist, Marketing case.
- Captured prompt text, redacted resume input, output, token usage, latency, and estimated cost for each run.

Results:

| Case | Mode | Prompt tokens | Output tokens | Total tokens | Latency | Est. cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Ironclad Senior Staff Data Scientist, AI | lazy | 972 | 692 | 1,664 | 6.8s | $0.01 |
| Ironclad Senior Staff Data Scientist, AI | engineered | 1,151 | 1,143 | 2,294 | 10.0s | $0.02 |
| Anthropic Data Scientist, Marketing | lazy | 938 | 765 | 1,703 | 9.7s | $0.01 |
| Anthropic Data Scientist, Marketing | engineered | 1,117 | 912 | 2,029 | 8.2s | $0.02 |

Read:

- Lazy prompting made the Ironclad resume look stronger by adding weak or unsupported claims such as model-accuracy dashboards, A/B tests with AI engineers, golden datasets, annotation guidelines, error taxonomies, and user intent classification.
- Lazy prompting made the Anthropic Marketing near-miss look plausible by adding or implying causal inference, campaign effectiveness, go-to-market strategy, and customer/channel analysis.
- Engineered prompting reduced hallucination risk and explicitly called out unsupported requirements, but it still cannot prove a tailored claim from project artifacts.

Product impact:

This supports the pivot from full automatic resume rewriting to an AI-guided resume assistant. The safer product path is to retrieve verified project evidence, suggest grounded bullets, and show unsupported gaps instead of producing a full rewritten resume that may overstate the user's work.

Artifacts:

- `scripts/run_resume_prompt_tailoring_experiment.py`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/prompt_experiment_summary.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030445Z/exp-v3-ironclad-senior-staff-ds-ai/lazy/output.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030445Z/exp-v3-ironclad-senior-staff-ds-ai/engineered/output.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030506Z/exp-v3-anthropic-ds-marketing/lazy/output.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030506Z/exp-v3-anthropic-ds-marketing/engineered/output.md`
