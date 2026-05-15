# Resume Tailoring Decision Log

Date started: 2026-05-13

This file is the running decision ledger for the resume-tailoring work. The goal is to preserve the actual applied-DS reasoning: what we tried, what the evals showed, why we made each decision, and what evidence would change the decision later.

The product question is not "can an LLM rewrite a resume?" It can. The harder question is whether AppTrail can tailor a resume without inventing experience, leaking private contact data, mutating protected sections, or matching a job requirement to evidence that only sounds related.

## Current Thesis

Resume tailoring should be evidence-grounded before it is generative.

The current safest architecture is:

```text
resume/project docs/job description
  -> privacy and format preflight
  -> project evidence extraction
  -> requirement extraction / cleaning
  -> retrieval over resume-safe evidence cards
  -> support gate
  -> generation only from accepted evidence IDs
  -> no evidence means abstain
```

The generation layer is not the bottleneck yet. Retrieval is.

## Key Metrics Snapshot

| Eval artifact | Requirements | Supported rows | Recall@5 | Precision@5 | Unrelated evidence rate | Unsupported false-support | Evidence-grounded unsupported bullet rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sanitized fixture eval | 12 | 11 | 100.0% | 30.6% | 69.4% | n/a | 0.0% |
| Real JD diagnostic, raw lexical | 45 | 25 | 16.7% | 5.3% | 94.7% | 100.0% raw unsupported rows returned evidence | 0.0% |
| Real JD diagnostic, gated lexical | 45 | 25 | 37.7% | 52.1% | 39.0% | 15.0% accepted unsupported false-support | 0.0% |
| Holdout v2, gated lexical | 112 | 57 | 25.7% | 20.4% | 74.2% | 74.5% accepted unsupported false-support | 0.0% |
| Holdout v2, cleaner + gated lexical | 112 | 57 | 25.7% | 43.6% | 51.0% | 27.3% accepted unsupported false-support | 0.0% |
| Holdout v2, cleaner + gated atomic cards | 112 | 57 | 18.6% | 43.1% | 49.7% | 25.5% accepted unsupported false-support | 0.0% |
| Holdout v2, cleaner + parent-child lexical | 112 | 57 | 20.5% | 45.0% | 49.6% | 29.1% accepted unsupported false-support | 0.0% |
| Holdout v2, cleaner + OpenAI section embeddings | 112 | 57 | 25.9% | 42.0% | 52.6% | 30.9% accepted unsupported false-support | 0.0% |
| Holdout v2, cleaner + OpenAI atomic embeddings | 112 | 57 | 25.4% | 44.8% | 48.0% | 30.9% accepted unsupported false-support | 0.0% |

Prompt-only generation is the control condition:

- Sanitized fixture prompt-only unsupported bullet rate: 100.0%
- Real JD gated prompt-only unsupported bullet rate: 100.0%
- Holdout v2 prompt-only unsupported bullet rate: 100.0%

Evidence-grounded generation stayed at 0.0% unsupported bullets in these artifacts because it only generated when accepted evidence intersected reviewed expected evidence.

## Decision Ledger

### D-001: Do Not Start With Free-Form Prompt Tailoring

Decision: use prompt-only resume tailoring as a negative control, not the production path.

Evidence:

- In the sanitized fixture eval, prompt-only generated 12 bullets and all 12 lacked evidence IDs.
- In the real gated eval, prompt-only generated 72 bullets with a 100.0% unsupported bullet rate.
- Prompt-only also introduced unsupported issues such as missing evidence IDs, new unverified skills, and one fabricated metric in the real gated artifact.

Rationale:

Prompt engineering can make a resume sound better, but it has no built-in proof that a bullet is supported by the user's actual work. For this product, unsupported polish is worse than no rewrite because it creates interview risk.

Artifact sources:

- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-gated/metrics.json`

Status: decided. Prompt-only remains a baseline/control, not a candidate production architecture.

### D-002: Add Privacy and Format Preflight Before Any Model Path

Decision: freeze protected resume sections and sanitize contact/private material before generation.

Evidence:

- The sanitizer replaces contact fields with placeholders for name, email, phone, location, and URLs.
- Protected sections include contact/header and education.
- Editable sections include summary, skills, projects, selected projects, certifications, experience, professional summary, technical skills, and work experience.
- The eval artifacts report no raw email, phone, or URL leaks in generated outputs.

Rationale:

Resume tailoring should not send or rewrite stable identity fields unless explicitly intended. The right default is to redact, tailor only mutable content, then rehydrate protected contact fields after generation.

Artifact sources:

- `backend/services/evals/resume_tailoring_eval.py`
- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/metrics.json`

Status: implemented in eval harness. Production UX still needs separate integration before user-facing release.

### D-003: Ingest Messy Project Markdown as Atomic Evidence Cards

Decision: do not index an entire project report as one blob. Parse project docs into section-aware evidence cards with stable evidence IDs.

Evidence:

- The sanitized messy fixture extracted 7 evidence cards, 6 resume-safe cards, and excluded 5 low-value/noisy sections.
- The real private project-doc ingest scanned 6 project reports and produced 54 resume-safe evidence cards.
- The extractor keeps source file, source section, evidence ID, claim type, evidence strength, skill tags, resume-safe status, preflight status, and preflight reasons.

Rationale:

The user's project reports are intentionally real-world messy. One project can contain AI engineering, analytics, backend, frontend, security, evaluation, and product work. RAG has to retrieve the right slice, not the whole project.

Artifact sources:

- `backend/services/evals/resume_project_ingest.py`
- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/evidence_cards.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-label-pack/evidence_cards_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/evidence_cards_compact.csv`

Status: implemented for offline eval.

### D-004: Build a Small Real JD Diagnostic Set Before Optimizing

Decision: use saved app jobs plus curated controls to create the first manually labeled diagnostic set.

Evidence:

- First real JD label pack had 45 candidate requirement rows.
- Manual label distribution:
  - direct: 12
  - partial: 15
  - none: 18
- Rows with expected evidence IDs: 25
- The pack mixed saved/applied roles with negative and near-miss controls.

Rationale:

The first set was not meant to be a final benchmark. It was meant to expose obvious retrieval failure modes quickly while using real project evidence and real JD text.

Artifact sources:

- `docs/ai-artifacts/generated/resume-tailoring-jd-label-pack/jd_requirement_label_queue_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-label-pack/jd_cases_labeled.json`

Status: diagnostic set retained. Do not keep tuning to this set without a holdout.

### D-005: Raw Lexical Retrieval Is Not Good Enough

Decision: raw lexical retrieval should not drive generation directly.

Evidence on the 45-row real JD diagnostic set:

- recall@5: 16.7%
- precision@5: 5.3%
- MRR: 0.197333
- unrelated evidence rate: 94.7%
- missing evidence rate: 83.3%
- rows without expected evidence that still returned evidence: 20 of 20
- evidence-grounded unsupported bullet rate: 0.0%, but only because generation abstained unless evidence intersected reviewed labels.

Rationale:

Raw lexical matching retrieved too much unrelated evidence and missed too much expected evidence. It was useful as a baseline, not as an architecture.

Artifact sources:

- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval/eda_report.md`

Status: rejected as production candidate.

### D-006: Add a Lexical Acceptance Gate as the First Targeted Fix

Decision: add an eval-only lexical acceptance gate before trying embeddings.

Evidence on the 45-row diagnostic set:

- recall@5 improved from 16.7% to 37.7%.
- precision@5 improved from 5.3% to 52.1%.
- MRR improved from 0.197333 to 0.524667.
- unrelated evidence rate dropped from 94.7% to 39.0%.
- accepted unsupported false-support dropped from 100.0% to 15.0%.
- evidence-grounded unsupported bullet rate stayed 0.0%.

What the gate did:

- rejected candidates that only matched generic terms
- rejected candidates missing domain anchors for controls such as robotics, sales, marketing, hospitality, and bioinformatics
- reranked accepted candidates by non-generic overlap
- allowed no acceptable evidence

Rationale:

The first EDA said the retriever was matching generic words. A lexical gate targeted that specific failure mode with low cost and high interpretability.

Artifact sources:

- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/eda_report.md`

Status: useful diagnostic improvement, not final architecture.

### D-007: Create a Fresh Holdout Before Further Tuning

Decision: create a second holdout with more roles before changing the retriever again.

Evidence:

- Holdout v2 has 25 roles collected from public Ashby/Greenhouse job-board APIs on 2026-05-13.
- Mix:
  - 15 likely-fit / strong-fit data, AI, retrieval, eval, analytics, or product data roles
  - 6 near-miss technical controls
  - 4 true-negative controls
- Candidate requirement rows: 112
- Manual label distribution:
  - direct: 6
  - partial: 51
  - none: 55
- Rows with expected evidence IDs: 57

Labeling policy:

- `direct`: evidence supports the requirement cleanly.
- `partial`: evidence supports the transferable skill, but not the exact company/domain/scale/qualifier.
- `none`: no usable project evidence. Boilerplate, compensation, EEO text, founder bios, sales-only requirements, marketing-only requirements, funding blurbs, and broad mission statements were unsupported.

Rationale:

The 45-row diagnostic set became too easy to overfit. The next question was generalization: does the acceptance gate still work when the JD mix expands?

Artifact sources:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/source_manifest.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/jd_requirement_label_queue_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/jd_cases_labeled.json`

Status: implemented. Treat v2 as a fixed benchmark, not a tuning worksheet.

### D-008: The Gated Lexical Retriever Does Not Generalize Well Enough on Holdout v2

Decision: do not promote gated lexical retrieval and do not go directly to user-facing resume generation.

Evidence on holdout v2:

- recall@5: 25.7%
- precision@5: 20.4%
- MRR: 0.355556
- unrelated evidence rate: 74.2%
- missing evidence rate: 74.3%
- accepted unsupported false-support: 74.5%
- unsupported rows with accepted evidence: 41 of 55
- evidence-grounded unsupported bullet rate: 0.0%
- prompt-only unsupported bullet rate: 100.0%

EDA findings:

- Top accepted overlap terms included `metrics`, `product`, `team`, `data`, `job`, `intelligence`, `research`, `evaluation`, `model`, and `analytics`.
- Ambiguous overlap terms causing false support included `product`, `evaluation`, `data`, `build`, `model`, `analytics`, and `analysis`.
- False returns concentrated in broad evidence cards from AppTrail, SPEC NYC, and AiBS because those projects contain many generic but impressive terms.
- Some semantic misses are real: responsible AI/security workflows, AI evaluation/red-teaming language, and genomics-style data-system language did not reliably retrieve the expected transferable evidence.

Rationale:

The v2 holdout showed two separate problems:

1. Noise admission: JD extraction is letting boilerplate and broad company context into the requirement list.
2. Semantic recall: valid transferable matches often do not share enough exact words with the evidence cards.

Those are different problems. More lexical rules alone would likely overfit v2.

Artifact sources:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-gated/eda_report.md`

Status: current state. Evidence-grounded generation is safe but retrieval is not strong enough.

### D-009: Add a JD Requirement Cleaner Before Retrieval

Decision: add an eval-only JD requirement cleaner before retrieval and keep it behind an explicit eval flag.

What changed:

- Added `backend/services/evals/resume_requirement_cleaner.py`.
- Added `--enable-requirement-cleaner` to `scripts/run_resume_tailoring_evidence_eval.py`.
- The cleaner classifies rows as `actual_requirement`, `product_context`, `company_boilerplate`, `legal_compensation`, `sales_marketing_role`, or `domain_only`.
- Retrieval is skipped for obvious boilerplate/legal/sales-marketing/domain-only rows.
- The cleaner strips HTML and records its category, policy, reasons, and cleaned query in each requirement result.

Evidence on the 45-row diagnostic set:

- recall@5 stayed at 37.7%.
- precision@5 stayed at 52.1%.
- MRR stayed at 0.524667.
- accepted unsupported false-support stayed at 15.0%.
- skipped requirements: 11
- skipped supported requirements: 0
- skipped unsupported requirements: 11

Evidence on holdout v2:

- recall@5 stayed at 25.7%.
- precision@5 improved from 20.4% to 43.6%.
- MRR stayed at 0.355556.
- unrelated evidence rate improved from 74.2% to 51.0%.
- accepted unsupported false-support improved from 74.5% to 27.3%.
- unsupported rows with accepted evidence dropped from 41 to 15.
- skipped requirements: 34
- skipped supported requirements: 0
- skipped unsupported requirements: 34
- evidence-grounded unsupported bullet rate stayed 0.0%.

Rationale:

This targets the observed noise-admission problem directly. The v2 EDA showed boilerplate, company context, EEO/compensation text, and sales/marketing controls entering retrieval and matching generic project words. Cleaning those rows before retrieval lowered false support without reducing recall on either the diagnostic set or the v2 holdout.

Important correction during implementation:

The first cleaner pass was too aggressive. It skipped supported product-context rows because the transferable-term list missed general AI/retrieval terms like `RAG`, `LLM`, `AI`, `pipelines`, `experimentation`, `semantic`, `heuristics`, `testing`, and connector terms like `GitHub` and `Slack`. It also treated `Salesforce` as sales-role evidence even when it appeared as an enterprise connector. The rule was corrected before logging the final artifact.

Artifact sources:

- `backend/services/evals/resume_requirement_cleaner.py`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-cleaner-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-cleaner-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-gated/eda_report.md`

Status: accepted as the next baseline for retrieval experiments. The next comparison should use cleaner + gated lexical as the baseline, not gated lexical alone.

## What We Know Now

### The Safe Part

The evidence-grounded generator is behaving correctly in the eval harness:

- It does not generate unsupported bullets when no reviewed evidence is retrieved.
- It keeps raw PII/URLs out of outputs in the current artifacts.
- It preserves protected sections in the deterministic eval path.

This means the abstention policy is working.

### The Weak Part

The retriever is too brittle:

- It overmatches generic product/data/model/evaluation language.
- It misses semantically relevant but lexically different evidence.
- It returns evidence for too many unsupported rows.
- It struggles when JD extraction includes HTML, boilerplate, or broad company positioning.

This means the next work should target retrieval and requirement cleaning, not generation polish.

## Targeted Next Experiments

### Experiment 1: JD Requirement Cleaner

Purpose: reduce noise before retrieval.

Classify extracted JD rows into:

- `actual_requirement`
- `product_context`
- `company_boilerplate`
- `legal_compensation`
- `sales_marketing_role`
- `domain_only`

Decision rule:

- Only `actual_requirement` and carefully selected `product_context` rows should enter evidence retrieval.
- Boilerplate and compensation should abstain immediately.

Why this is targeted:

- Holdout v2 had 55 unsupported rows.
- 41 of those still returned accepted evidence.
- The EDA examples show HTML/legal/benefits/company text matching project evidence through generic words.

Success gate:

- unsupported rows with accepted evidence drops from 41 of 55 to fewer than 15 of 55
- accepted unsupported false-support drops from 74.5% to below 30%
- recall@5 on supported rows does not drop by more than 5 percentage points

Status: substantially met on holdout v2. Unsupported rows with accepted evidence dropped from 41 to 15, which is just above the stricter "fewer than 15" target. Accepted unsupported false-support dropped to 27.3%, and recall@5 stayed at 25.7%.

### Experiment 2: Evidence Metadata Facets

Purpose: make evidence cards less like plain text blobs.

Add deterministic metadata facets:

- `skill_family`
- `system_layer`
- `domain`
- `artifact_type`
- `ml_type`
- `privacy_safety`
- `product_surface`
- `evidence_scope`

Decision rule:

- A requirement and evidence card can match lexically only if their facets are compatible or if the row is explicitly labeled transferable.

Why this is targeted:

- Generic terms are the main false-support driver.
- Facets let us block claims like marketing/sales/hospitality matching technical projects through words like `product`, `team`, or `data`.

Success gate:

- unrelated evidence rate drops from 74.2% to below 45%
- precision@5 improves from 20.4% to at least 35%
- unsupported false-support stays below 30%

### Experiment 3: Hybrid Retrieval Benchmark

Purpose: test whether semantic retrieval recovers expected evidence that lexical misses.

Compare on the same fixed v2 holdout:

- current gated lexical
- embedding-only
- lexical + embedding union
- lexical candidate recall + embedding rerank
- hybrid retrieval with metadata gates

Why this is targeted:

- EDA found real semantic misses.
- Responsible AI/security, LLM eval, and genomics-like data-system requirements often need concept matching, not exact word matching.

Success gate:

- recall@5 improves from 25.7% to at least 45-50%
- precision@5 improves from 20.4% to at least 35-40%
- unsupported false-support drops below 25-30%
- evidence-grounded unsupported bullet rate remains 0.0%
- latency remains acceptable for interactive use

### Experiment 4: Pairwise Support Verifier

Purpose: decide whether a retrieved evidence card actually supports a requirement.

Candidate implementations:

- deterministic rubric first
- lightweight classifier after more labels
- LLM verifier only after privacy preflight and redaction
- cross-encoder/reranker if local/offline model setup is practical

Why this is targeted:

- Retrieval can return semantically close but unsupported evidence.
- Resume tailoring needs support judgment, not just similarity.

Success gate:

- accepted unsupported false-support below 15%
- direct/partial rows maintain or improve recall
- verifier has traceable reasons or support labels

## D-010 Atomic Evidence Card Experiment

Question: are the broad project cards the reason lexical retrieval over-matches? If one evidence card contains FastAPI, data models, AI evals, governance, frontend surfaces, and deployment notes in the same sentence, a JD can match the card for the wrong reason.

Change tested:

- Added an eval-only `--project-doc-granularity atomic_claim` mode.
- The default remains `section_claim`.
- Atomic cards keep a `parent_evidence_id`, so the existing v2 labels still score correctly when a child card supports a parent-labeled evidence item.
- Retrieval artifacts now store `returned_evidence_aliases`, `returned_evidence_matches`, and `matched_expected_evidence_ids` so we can audit child-parent scoring.

Result on fixed v2 holdout, with cleaner + acceptance gate unchanged:

| Metric | Section cards | Atomic cards |
| --- | ---: | ---: |
| Resume-safe evidence cards | 54 | 108 |
| recall@5 | 25.7% | 18.6% |
| precision@5 | 43.6% | 43.1% |
| MRR | 0.355556 | 0.251170 |
| unrelated evidence rate | 51.0% | 49.7% |
| accepted unsupported false-support | 27.3% | 25.5% |
| unsupported rows with accepted evidence | 15 | 14 |

Interpretation:

Atomic cards helped slightly on false support, but hurt recall more than it helped precision. This is probably not a pure model problem. It is a representation problem. Some broad cards are too broad for precise citation, but they also carry useful context that lexical retrieval needs to find the right project in the first place.

Decision:

Do not replace section cards with atomic cards. The next targeted architecture should be multi-granularity retrieval:

```text
retrieve broad section/project cards for recall
  -> retrieve or expand to child evidence cards for citation-level grounding
  -> rank with parent-child aliases and support checks
```

That is a better fit for the observed failure than further hand-tuning lexical rules. It also gives us a cleaner gate for embeddings: embeddings should be compared against the cleaner + gated section-card baseline and, ideally, against a multi-granularity lexical baseline.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/eda_report.md`

## D-011 Parent-Child Lexical Retrieval

Question: can we keep the recall benefit of broad section cards while returning narrower child evidence for citation?

ML framing:

This is a two-stage **coarse-to-fine retrieval** pipeline. It is also fair to call it **rank-then-rerank**:

```text
rank broad parent cards
  -> expand top parents into child evidence cards
  -> rerank child cards with lexical/support features
  -> cite only accepted child evidence
```

Implementation:

- Added `--retrieval-strategy parent_child_lexical`.
- Stage 1 indexes section-level parent cards.
- Stage 2 expands retrieved parents into atomic child cards.
- Child cards keep aliases to the labeled parent IDs, so the fixed v2 holdout can be reused without relabeling.
- Widened parent and child candidate pools before acceptance gating after the first run showed premature truncation.

Result on fixed v2 holdout, with cleaner + acceptance gate unchanged:

| Metric | Section cards | Atomic only | Parent-child lexical |
| --- | ---: | ---: | ---: |
| Recall@5 | 25.7% | 18.6% | 20.5% |
| Precision@5 | 43.6% | 43.1% | 45.0% |
| MRR | 0.355556 | 0.251170 | 0.287719 |
| Unrelated evidence rate | 51.0% | 49.7% | 49.6% |
| Accepted unsupported false-support | 27.3% | 25.5% | 29.1% |
| Unsupported rows with accepted evidence | 15 | 14 | 16 |

Interpretation:

Parent-child lexical improved precision and unrelated evidence rate a little, but it did not recover enough recall and it slightly worsened unsupported false-support. That tells us the bottleneck is not only card granularity. The system still needs better semantic matching or a stronger pairwise support verifier.

Decision:

Do not promote parent-child lexical as the new baseline. Keep `cleaner + gated section-card lexical` as the baseline because it has the best recall and lower false support than the current parent-child run.

What this changes:

- The parent-child representation is still useful for future citation control.
- It should be paired with embeddings or a support verifier, not treated as sufficient with lexical scoring alone.
- The next experiment is justified: compare hybrid/embedding retrieval against the fixed cleaner + gated section-card baseline, and optionally use child cards only after the broader retriever finds the right project/section.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-hybrid/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-hybrid/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding-atomic/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding-atomic/eda_report.md`

## D-013 Pairwise Support Verifier

Question: after retrieval finds plausible evidence, can a deterministic pairwise verifier lower false support without simply filtering everything?

Implementation:

- Added `backend/services/evals/resume_support_verifier.py`.
- Wired `--enable-support-verifier` into `scripts/run_resume_tailoring_evidence_eval.py`.
- The verifier runs after retrieval and the existing acceptance gate.
- It scores one JD requirement against one evidence card using:
  - specific term overlap
  - weak/generic term overlap
  - category overlap
  - domain-anchor failures
  - broad-inventory detection
  - optional embedding similarity when the retrieval strategy supplies it
- It emits `supports`, `partial_support`, or `not_enough_info`.
- It is eval-only. Production resume tailoring behavior is unchanged.

Holdout v2 comparison:

| Strategy | Recall@5 | Precision@5 | MRR | Unrelated rate | False-support | Verifier rejected | Supported rows rejected to zero |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Cleaner + section lexical | 25.7% | 43.6% | 0.355556 | 51.0% | 27.3% | n/a | n/a |
| Cleaner + section lexical + verifier | 21.6% | 46.9% | 0.353801 | 39.7% | 21.8% | 81 | 9 |
| Cleaner + parent-child lexical | 20.5% | 45.0% | 0.287719 | 49.6% | 29.1% | n/a | n/a |
| Cleaner + parent-child lexical + verifier | 20.5% | 49.9% | 0.326608 | 38.5% | 21.8% | 72 | 7 |
| Cleaner + OpenAI section embedding | 25.9% | 42.0% | 0.356140 | 52.6% | 30.9% | n/a | n/a |
| Cleaner + OpenAI section embedding + verifier | 20.6% | 43.1% | 0.353509 | 43.5% | 29.1% | 82 | 9 |
| Cleaner + OpenAI hybrid + verifier | 20.6% | 43.1% | 0.353509 | 43.5% | 29.1% | 84 | 9 |
| Cleaner + OpenAI atomic embedding | 25.4% | 44.8% | 0.279532 | 48.0% | 30.9% | n/a | n/a |
| Cleaner + OpenAI atomic embedding + verifier | 22.5% | 46.8% | 0.300877 | 39.8% | 29.1% | 78 | 7 |

Interpretation:

The verifier is doing useful work, but it is not enough to promote embeddings. The best safety improvement came from section lexical and parent-child lexical with the verifier: unsupported false support dropped from 27.3-29.1% to 21.8%, and unrelated evidence dropped to roughly 39%. That is a real improvement.

The recall tradeoff matters. Section lexical with verifier lost about 4.1 points of recall. The EDA shows why: several expected labels are broad section cards that the verifier correctly treats as too broad or generic for citation-level support. Parent-child lexical avoided rejecting expected candidates once they were found, but it still failed to retrieve the right expected evidence for many rows.

This is not clearly a model problem yet. It is partly a data/label granularity problem:

- Some expected labels point to broad project-section evidence, while the verifier is evaluating citation-level support.
- Some JD rows are broad company/team descriptions rather than concrete requirements.
- Embeddings retrieve plausible evidence, but plausible evidence still fails the support question.
- Parent-child evidence improves citation safety, but its lexical first stage still misses too many expected cards.

Decision:

Do not promote embeddings, hybrid retrieval, or the support verifier as a production path yet. Keep `cleaner + gated section-card lexical` as the recall baseline. Treat `parent-child lexical + verifier` as the best precision/safety diagnostic so far, not as the production candidate.

Next targeted experiment:

- Create a second label view that separates broad section relevance from citation-level support.
- Label or derive `expected_parent_evidence_ids` and `expected_citation_evidence_ids` separately.
- Re-run parent-child retrieval with parent recall and child citation precision measured separately.
- Only then decide whether a cross-encoder/reranker is justified.

Transformer gate:

Try a reranker only if the candidate pool contains the correct parent/card but the final rank/support decision is wrong. If the correct evidence is not in the candidate set, a reranker will not fix the root cause.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-support-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-parent-child-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-parent-child-support-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-openai-embedding-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-openai-embedding-support-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-openai-hybrid-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-openai-hybrid-support-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-openai-embedding-atomic-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-openai-embedding-atomic-support-gated/eda_report.md`

## D-014 Parent vs Citation Label Split

Question: were the previous recall/safety results mixing two different questions: broad project relevance and exact citation support?

Implementation:

- Added optional `expected_parent_evidence_ids` and `expected_citation_evidence_ids` to JD requirement cases.
- Kept `expected_evidence_ids` as the legacy parent-level field for backward compatibility.
- Added parent metrics and citation metrics to the eval artifact:
  - `parent_recall_at_k_mean`
  - `parent_precision_at_k_mean`
  - `citation_recall_at_k_mean`
  - `citation_precision_at_k_mean`
  - `requirements_with_expected_citation_evidence`
  - `parent_supported_without_citation_labels`
- Added `scripts/build_resume_parent_citation_labels.py`.
- Built a diagnostic split-label artifact from the reviewed parent labels plus the deterministic support verifier.

Label artifact summary:

| Item | Count |
| --- | ---: |
| JD cases | 25 |
| Requirements | 112 |
| Parent-labeled requirements | 57 |
| Machine-derived citation-labeled requirements | 39 |
| Parent-supported rows without citation labels | 18 |
| Accepted citation IDs | 145 |

Important limitation:

The citation labels are machine-derived from human-reviewed parent labels and the deterministic verifier. They are useful for offline diagnostics, but they are not final human-labeled truth. The point of this round is to make the eval target explicit, not to claim a solved citation-label dataset.

Split-label holdout results:

| Strategy | Parent recall@5 | Parent precision@5 | Citation recall@5 | Citation precision@5 | Unrelated rate | False-support |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Section lexical + verifier | 21.6% | 46.9% | 10.1% | 48.6% | 39.7% | 21.8% |
| Parent-child lexical | 20.5% | 45.0% | 40.2% | 53.6% | 49.6% | 29.1% |
| Parent-child lexical + verifier | 20.5% | 49.9% | 40.2% | 59.4% | 38.5% | 21.8% |
| OpenAI atomic embedding + verifier | 22.5% | 46.8% | 42.6% | 55.8% | 39.8% | 29.1% |

Interpretation:

This confirms the hypothesis. The system was mixing parent relevance and citation support into one metric. Once split apart, parent-child retrieval is clearly better at citation retrieval than section retrieval: citation recall jumps from 10.1% to 40.2%, and citation precision improves from 48.6% to 59.4% when paired with the verifier.

The tradeoff remains parent recall. Parent-child lexical has safer citations, but it still does not find enough of the right parent evidence. OpenAI atomic embeddings improve parent recall slightly and citation recall slightly, but they worsen false support back to 29.1%. That means embeddings alone are not the next production answer.

Decision:

Keep parent/citation split metrics. Do not tune against the old single-label metric anymore. The current best diagnostic candidate is `parent-child lexical + support verifier`, not because it has the highest recall, but because it best explains the architecture we likely want:

```text
find broad relevant project area
  -> expand to atomic evidence
  -> verify exact citation support
  -> generate only from verified citation evidence
```

Next targeted step:

- Human-review the 39 machine-derived citation-labeled rows and the 18 parent-supported/no-citation rows.
- Add citation labels manually where the verifier missed valid child evidence.
- Then rerun parent-child and embedding strategies.

Transformer/cross-encoder gate:

This split shows where a reranker could help, but it is not time yet. Try a cross-encoder only after human citation labels confirm that the right parent or child candidates are present in the candidate pool but ranked or filtered incorrectly. If the candidate pool is missing the right evidence, a reranker is the wrong fix.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation/jd_cases_parent_citation_labeled.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation/summary.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-section-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-section-support-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-parent-child-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-parent-child-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-parent-child-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-parent-child-support-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-openai-atomic-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-parent-citation-eval-openai-atomic-support-gated/eda_report.md`

## D-012 OpenAI Embedding Retrieval

Question: are the remaining retrieval failures semantic enough that embeddings beat cleaner + gated lexical?

Implementation:

- Added eval-only `openai_embedding` and `openai_hybrid` retrieval strategies.
- Embedded both sides:
  - query side: cleaned JD requirement text plus case title
  - corpus side: resume-safe project evidence text plus project title, section path, skills, and claim type
- Used `text-embedding-3-small`.
- Left production retrieval unchanged.
- Kept the requirement cleaner and acceptance gate in place.
- Made the acceptance gate embedding-aware: a strong embedding similarity can satisfy the non-generic-overlap check, but domain-anchor failures still block support.

Fixed v2 holdout results:

| Strategy | Cards | Recall@5 | Precision@5 | MRR | Unrelated rate | False-support |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cleaner + section lexical | 54 | 25.7% | 43.6% | 0.355556 | 51.0% | 27.3% |
| Cleaner + OpenAI section embedding | 54 | 25.9% | 42.0% | 0.356140 | 52.6% | 30.9% |
| Cleaner + OpenAI hybrid | 54 | 25.9% | 42.0% | 0.356140 | 52.6% | 30.9% |
| Cleaner + OpenAI atomic embedding | 108 | 25.4% | 44.8% | 0.279532 | 48.0% | 30.9% |

Interpretation:

Embeddings did not produce the expected recall lift on this holdout. Section embeddings were basically tied on recall but worse on precision and false support. Atomic embeddings improved precision and unrelated evidence rate, but still did not beat the section lexical baseline overall because false support increased and recall was slightly lower.

This suggests the remaining problem is not just "find semantically similar text." Resume tailoring needs **support verification**. Embeddings can find plausible-looking evidence, but plausible-looking is not the same as safe-to-cite.

Decision:

Do not promote embedding retrieval. Keep cleaner + gated section lexical as the current baseline.

Next targeted experiment:

- Add a pairwise support verifier over the candidate set.
- Compare verifier behavior on lexical candidates and embedding candidates.
- Only reconsider embeddings if the verifier can lower false support while preserving or improving recall.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-hybrid/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-hybrid/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding-atomic/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding-atomic/eda_report.md`

## Gates for Embeddings

Embeddings were justified for offline experimentation and have now been tested on the fixed v2 holdout. They are not justified for production promotion yet.

### Try Embeddings Offline When

- The holdout is fixed and labeled.
- Lexical EDA shows semantic misses.
- Requirement cleaning is in place or measured as a separate ablation.
- We compare against the current cleaner + gated lexical baseline.
- We do not relabel or tune the holdout after seeing the result.

That gate was met for offline experimentation after the JD cleaner was implemented and measured.

### Promote Embeddings Only When

Embeddings or hybrid retrieval must beat the current cleaner + gated lexical v2 baseline on the fixed holdout before promotion:

- recall@5: from 25.7% to at least 45-50%
- precision@5: from 43.6% to at least 50%
- accepted unsupported false-support: from 27.3% to under 20%
- evidence-grounded unsupported bullet rate remains 0.0%
- negative controls stay near-zero false support
- latency/cost remain acceptable for interactive resume tailoring

## Gates for Transformers / Cross-Encoders

Do not start with transformers. Use them only if the eval shows a second-stage support problem after embeddings.

Try a transformer reranker or cross-encoder when:

- hybrid retrieval improves recall but still admits too much weak evidence
- top-k contains the correct evidence somewhere but not ranked high enough
- pairwise support needs better semantic judgment than deterministic facets can provide

Promotion gate:

- material lift over hybrid retrieval on v2
- accepted unsupported false-support below 15%
- clear improvement on direct and partial rows
- no increase in unsupported generation
- latency budget still acceptable, or reranker is used only on a small candidate set

### D-013: Expand the JD Holdout Before More Retriever Tuning

Decision: add a fresh 25-role expansion pack before making another retrieval change.

Evidence:

- Holdout v2 gave useful signal, but it is still only 25 roles and 112 requirement rows.
- The current best offline path improves precision but still misses support and still over-accepts some broad semantic neighbors.
- The next failure analysis needs more role diversity, especially near-miss and no-match roles, before we can tell whether the issue is retrieval architecture or dataset narrowness.

What changed:

- Added `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3/`.
- Collected 25 public job postings on 2026-05-13.
- Stored paraphrased requirement rows only; full job descriptions were not copied into the repo.
- Generated 118 compact requirement rows.
- Kept `expected_parent_evidence_ids` and `expected_citation_evidence_ids` blank so this remains unlabeled until review.
- Mixed 13 saved-app / strong-fit roles, 9 near-miss controls, and 3 negative controls.

Rationale:

The next step should not be tuning rules to the current holdout. A senior DS approach is to first increase evaluation coverage, then rerun the same baselines unchanged. If performance drops, that drop is evidence about where the retriever is brittle. If performance holds, the same expansion set becomes the benchmark for hybrid retrieval and reranking.

Labeling update:

- Labeled all 118 requirement rows against the current 54 extracted project evidence cards.
- Support labels: 31 direct, 66 partial, 21 none.
- Rows with reviewed evidence IDs: 97.
- Unsupported rows left blank: 21.
- Because this expansion pack currently contains section-level evidence cards, the same reviewed IDs are used for `expected_parent_evidence_ids`, `expected_citation_evidence_ids`, and legacy `expected_evidence_ids`.

Status: labeled once. It is now usable as an eval expansion set, but labels should still be treated as reviewable because the evidence-card granularity is section-level rather than atomic.

### D-014: Embeddings Help, But Not Enough on Expansion v3

Decision: keep the resume-tailoring work offline. Do not promote embedding or hybrid retrieval from this run.

Expansion v3 model comparison:

| Run | Recall@3 | Precision@3 | MRR | Missing evidence | Unrelated evidence | Unsupported false support | Generated rows | Missed supported | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw lexical | 16.5% | 13.0% | 27.8% | 83.5% | 87.0% | 100.0% | 39 | 58 | 13 ms |
| Cleaner + support lexical | 17.0% | 29.1% | 31.3% | 83.0% | 47.2% | 28.6% | 39 | 58 | 26 ms |
| Parent-child + support | 12.2% | 27.0% | 22.9% | 87.8% | 43.4% | 23.8% | 29 | 68 | 43 ms |
| OpenAI embedding + support | 18.4% | 31.4% | 35.2% | 81.6% | 44.9% | 23.8% | 42 | 55 | 564 ms |
| OpenAI hybrid + support | 18.4% | 31.4% | 34.2% | 81.6% | 45.8% | 23.8% | 42 | 55 | 802 ms |

Read:

- Embeddings produced the best recall and precision, but the lift over cleaner + support lexical was small: +1.4 points recall@3 and +2.3 points precision@3.
- Hybrid retrieval did not improve over pure embedding and added latency.
- Parent-child retrieval underperformed because the expansion labels are still section-level. Atomic returned evidence is penalized when the reviewed citation IDs are broad section cards.
- Prompt-only generation stayed at 100.0% unsupported bullet rate.
- Evidence-grounded generation stayed at 0.0% unsupported bullet rate, but only because the system abstained on many supported rows when retrieval missed the reviewed evidence.

Interpretation:

This is not just a "lexical is bad, embeddings fix it" story. The expansion set shows a representation problem. Broad project cards like SPEC NYC product presentation and AppTrail product surfaces are semantically close to many requirements, but they are too broad to be reliable citations. The retriever needs narrower evidence cards and citation labels before a reranker or cross-encoder will have enough signal to work with.

Next step:

Generate atomic evidence cards and label citation IDs against the atomic card set. Then rerun lexical, embedding, and hybrid on the same 25-role expansion set. Only try a transformer/cross-encoder after top-k contains the right evidence but ranks it below weaker evidence.

Artifact sources:

- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3/model_eval_summary.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-eval-cleaner-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-eval-openai-embedding-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-eval-openai-hybrid-support-gated/metrics.json`

### D-015: Atomic Evidence and Split Labels Changed the Read

Decision: keep the parent/citation split and use atomic evidence for citation diagnostics, but do not move to transformers yet.

What changed:

- Rebuilt the six project reports as atomic evidence cards.
- Generated a parent/citation split label view for expansion v3 from reviewed parent labels plus the deterministic support verifier.
- Re-ran the same model family without changing the benchmark:
  - raw atomic lexical
  - atomic lexical + requirement cleaner + support verifier
  - parent-child lexical + requirement cleaner + support verifier
  - OpenAI atomic embedding + requirement cleaner + support verifier
  - OpenAI atomic hybrid + requirement cleaner + support verifier
- Added a miss EDA focused on citation misses, unsupported false returns, and parent-supported rows that still lack a citation label.

Label and evidence coverage:

| Item | Count |
| --- | ---: |
| JD cases | 25 |
| Requirement rows | 118 |
| Parent-supported rows | 97 |
| Machine-derived citation-labeled rows | 61 |
| Parent-supported rows without derived citation labels | 36 |
| Unsupported rows | 21 |
| Resume-safe atomic evidence cards | 108 |

Atomic parent/citation results:

| Run | Parent recall@3 | Parent precision@3 | Citation recall@3 | Citation precision@3 | Unsupported false support | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw atomic lexical | 10.7% | 9.0% | 10.8% | 6.1% | 100.0% | 13 ms |
| Atomic lexical + cleaner/support | 10.0% | 24.3% | 19.1% | 35.0% | 23.8% | 27 ms |
| Parent-child lexical + cleaner/support | 12.2% | 27.0% | 24.6% | 38.8% | 23.8% | 36 ms |
| OpenAI atomic embedding + cleaner/support | 10.8% | 26.6% | 21.2% | 38.2% | 23.8% | 646 ms |
| OpenAI atomic hybrid + cleaner/support | 10.5% | 25.3% | 21.1% | 36.4% | 23.8% | 669 ms |

Interpretation:

This rerun changed the read from "embeddings are slightly ahead" to "the deterministic parent-child path is the best current citation retriever." Once the target is exact atomic citation support, parent-child lexical beats OpenAI embedding and hybrid on citation recall and citation precision, while running far faster.

That does not make parent-child lexical production-ready. Parent recall is still low, citation recall is only 24.6%, and 36 parent-supported rows still have no derived citation labels. The misses are not just ranking misses. Some are representation and label-coverage misses: the right parent project may be known, but the atomic extractor or verifier did not produce a child citation that cleanly supports the requirement.

Decision:

Do not jump to a transformer/cross-encoder yet. The next fix should improve the data representation and labels:

- human-review the 61 machine-derived citation-labeled rows
- manually inspect the 36 parent-supported/no-citation rows
- improve atomic extraction for line-level skills, measurable outcomes, tooling, and evaluation claims
- rerun the same suite after label cleanup before changing the model family

Transformer/cross-encoder gate:

Try a reranker only after EDA shows the correct atomic citation is present in the candidate pool but ranked below weaker evidence. If the correct citation is missing from the corpus or missing from the candidate pool, a reranker is the wrong fix.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation/jd_cases_parent_citation_labeled.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation/evidence_cards_atomic_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation/atomic_miss_eda.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation-eval-raw-atomic/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation-eval-atomic-lexical-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation-eval-parent-child-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation-eval-openai-atomic-support-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation-eval-openai-hybrid-atomic-support-gated/metrics.json`

### D-016: Curated Evidence Cards Beat Model Hopping

Question: is the retrieval bottleneck really a model problem, or are the project evidence cards too broad/noisy?

Decision: build a curated evidence-card layer from the six markdown project reports before trying another retrieval model.

What changed:

- Added `docs/ai-artifacts/resume-tailoring-curated-evidence/`.
- Rewrote the project reports into 83 small, resume-safe evidence cards.
- Kept claims source-bound to the local project reports.
- Avoided unsupported production claims, especially for pre-pilot, benchmark-only, model-quality-warning, and static-site projects.
- Added `scripts/build_resume_curated_evidence_labels.py` to map the existing reviewed parent labels onto curated cards by project scope, then cap derived citations to the strongest four per requirement.

Important caveat:

The curated cards are manually written from source reports. The curated JD labels are still machine-derived from reviewed parent labels plus the deterministic verifier. This is enough for an offline diagnostic, but not enough to call the labels final human truth.

Diagnostic comparison:

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

This is the strongest evidence so far that the next bottleneck is evidence representation, not model class. Rewriting the cards improved the cheap lexical path more than switching to embeddings did. After splitting broad project tags from narrow card-level evidence skills, curated lexical + cleaner/support has the best precision, lowest false support, and lowest latency. OpenAI hybrid has slightly higher recall, but with materially higher latency and a higher false-support rate.

That does not mean the feature is solved. It means the product should invest in an evidence-card authoring/review layer before automatic resume generation:

```text
project reports / resume history
  -> curated or LLM-assisted evidence cards
  -> human-reviewable evidence IDs
  -> JD requirement extraction
  -> lexical retrieval + cleaner/support verifier
  -> bullet suggestions only from verified evidence
```

Next targeted step:

- Human-review the curated cards and the machine-derived curated citation labels.
- Use a compact CSV workflow for accept/reject/edit on evidence cards and citations.
- Then rerun the same lexical/embedding suite without changing the benchmark.

Artifacts:

- `docs/ai-artifacts/resume-tailoring-curated-evidence/README.md`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/apptrail.md`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/spec_nyc.md`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/shelfops.md`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/aibs.md`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/pulse_tracker.md`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/augusta_defended.md`
- `scripts/build_resume_curated_evidence_labels.py`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_evidence_cards.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_jd_cases_labeled.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-lexical-support/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-openai-embedding/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-openai-hybrid/metrics.json`

### D-017: Review the New Citation Layer, Do Not Restart the JD Labels

Question: now that the project cards changed, do the JD labels need to be redone from scratch?

Decision: no. Keep the existing JD requirement support labels as the seed truth, then review the new evidence-card layer and citation mappings.

Why:

- The JD requirements did not change.
- The `direct` / `partial` / `none` support labels are still useful as the business target for each requirement.
- What changed is the evidence ID universe: broad auto-extracted cards were replaced by 83 curated, resume-safe cards.
- That means the risky layer is not "what does the JD require?" but "which new card proves this requirement, and is that card itself valid?"

Review workflow created:

| File | Rows | Purpose |
| --- | ---: | --- |
| `curated_evidence_card_review_queue.csv` | 83 | Review each curated card as `keep`, `edit`, or `drop`. |
| `curated_citation_requirement_review_queue.csv` | 118 | Compact one-row-per-requirement queue; accept, edit, mark none, or flag missing evidence. |
| `curated_citation_candidate_review_queue.csv` | 776 | Detailed top-candidate queue for hard cases where the compact row is not enough. |

Suggested order:

1. Review the 83 evidence cards first. A bad card should not become truth just because retrieval can find it.
2. Review the 118 requirement rows next. Accept current citations where they are obviously right; edit citation IDs where the support label is right but the evidence card is wrong or incomplete.
3. Use the 776-row candidate queue only for ambiguous requirements. It is the audit trail, not the primary labeling surface.
4. Rerun the lexical, embedding, and hybrid suite on the reviewed labels without changing the benchmark.

Artifacts:

- `scripts/build_resume_curated_review_queues.py`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/README.md`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/summary.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_evidence_card_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_citation_requirement_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_citation_candidate_review_queue.csv`

### D-018: Split Project Tags From Evidence Skills

Question: should broad project-level skills stay attached to every evidence card?

Decision: no. Broad skills are useful context, but they should not enter retrieval/support as if every card proves every skill from the project.

Why this matters:

- A card that says "Built a PostgreSQL warehouse" should not carry unrelated skills like OpenAI or data visualization.
- Broad skill leakage can make a requirement look supported because the project used a skill somewhere else.
- This is especially risky for resume tailoring because the generated bullet might claim a skill the specific evidence card does not prove.

Implementation:

- Curated project files now use `project_tags` for broad project-level context.
- Each card now has narrow `evidence_skills`.
- `ProjectEvidenceRecord.skills` remains the eval/search skill field, but it now means evidence-level skills for curated cards.
- `ProjectEvidenceRecord.project_tags` is available for display/review metadata.
- Search document keywords, support verification, child scoring, embeddings, and bullet unsupported-skill checks continue to use `skills`, which now avoids broad project-tag leakage.

Rerun result after the split:

| Run | Citation labels | Citation recall@3 | Citation precision@3 | Unsupported false support | Unsupported rows with returns | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Curated raw lexical | 69 | 16.2% | 7.6% | 100.0% | 49 | 12 ms |
| Curated lexical + support | 69 | 38.3% | 63.4% | 6.1% | 3 | 24 ms |
| Curated OpenAI embedding + support | 69 | 37.9% | 61.3% | 10.2% | 5 | 589 ms |
| Curated OpenAI hybrid + support | 69 | 40.9% | 62.6% | 10.2% | 5 | 495 ms |

Interpretation:

This validates the concern. Narrowing skills did not hurt the strongest cheap path. It improved the precision/false-support profile and made the labels cleaner to review. The hybrid embedding path currently buys about 2.6 recall points over lexical, but it is slower and less conservative on unsupported requirements. That is not enough evidence to promote embeddings yet.

Artifacts:

- `backend/services/evals/resume_tailoring_eval.py`
- `docs/ai-artifacts/resume-tailoring-curated-evidence/`
- `scripts/build_resume_curated_review_queues.py`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence/curated_jd_cases_labeled.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_evidence_card_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-lexical-support/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-openai-embedding/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-eval-openai-hybrid/metrics.json`

### D-019: Manual Review of Curated Cards and Requirement Citations

Question: after cleaning the evidence-card schema, can the card and requirement citation queues be reviewed without restarting the whole JD labeling process?

Decision: yes. The review pass is complete for the two compact queues. The candidate-level queue remains an audit surface rather than the primary labeling surface.

Review basis:

- Six local project reports in `/Users/colbyreichenbach/Downloads/`.
- Curated evidence markdown under `docs/ai-artifacts/resume-tailoring-curated-evidence/`.
- Existing JD requirement support labels as the seed target.
- Conservative evidence policy: if a requirement asked for stakeholder behavior, A/B testing, domain-specific data, or business outcomes that the cards did not directly prove, the row was not forced.
- Second-pass policy for collaboration-heavy rows: evaluate the substantive capability after stripping phrases such as "partner with" or "work with," then label as `partial` only when the evidence supports the underlying work. The review note must still call out that stakeholder partnership, A/B testing, executive communication, or domain-specific ownership is not directly proven.

Results:

| Review surface | Rows | Result |
| --- | ---: | --- |
| Curated evidence cards | 83 | 83 `keep` |
| Requirement citation rows | 118 | 25 `accept_current`, 63 `edit_citations`, 30 `mark_none`, 0 unresolved |

Reviewed support label counts:

| Label | Count |
| --- | ---: |
| `direct` | 24 |
| `partial` | 64 |
| `none` | 30 |
| blank / unresolved | 0 |

The 9 formerly unresolved rows were reviewed again after separating the collaboration phrase from the rest of the requirement. All 9 are now `partial`: the cards support transferable capabilities such as turning ambiguous performance questions into modeling experiments, converting operational problems into measurable ML work, safety/model-risk governance, AI-product context routing, and evidence-backed quality improvement. The review notes explicitly preserve the caveat that the cards do not prove direct stakeholder partnership, A/B-test ownership, executive communication, or the exact business domain.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_evidence_card_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/curated_citation_requirement_review_queue.csv`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-review/manual_review_summary.json`

Next targeted step:

Convert the reviewed CSV columns into a reviewed eval-case JSON and rerun lexical, embedding, and hybrid retrieval against that reviewed label set. Do not tune the model before this rerun.

### D-020: Rerun Retrieval on Human-Reviewed Curated Citation Labels

Question: after the manual review pass converted the curated citation layer into reviewed labels, does the retrieval decision change?

Decision: no. The reviewed rerun is useful, but it does not justify moving to embeddings or hybrid retrieval yet.

What changed:

- Added `scripts/apply_resume_curated_review_labels.py`.
- Converted `curated_citation_requirement_review_queue.csv` into a reviewed eval-case JSON.
- Reviewed label set now has 25 JD cases, 118 requirement rows, 88 citation-labeled requirements, and 30 unsupported requirements.
- Reran raw lexical, lexical + cleaner/support, OpenAI embedding + cleaner/support, and OpenAI hybrid + cleaner/support without changing retrieval logic.

Results:

| Run | Citation labels | Citation recall@3 | Citation precision@3 | Unsupported false support | Unsupported rows with returns | p95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Reviewed raw lexical | 88 | 25.8% | 35.3% | 46.7% | 14 | 24 ms |
| Reviewed lexical + cleaner/support | 88 | 23.2% | 42.1% | 26.7% | 8 | 20 ms |
| Reviewed OpenAI embedding + cleaner/support | 88 | 23.3% | 42.2% | 26.7% | 8 | 761 ms |
| Reviewed OpenAI hybrid + cleaner/support | 88 | 24.7% | 43.8% | 26.7% | 8 | 721 ms |

Interpretation:

The reviewed label set is stricter and broader than the machine-derived set: citation-labeled rows increased from 69 to 88 after second-pass review. That makes the rerun a better benchmark, but also exposes that the current retrieval stack is still not reliable enough for automatic resume generation.

The important finding is that embeddings do not solve the current failure mode. OpenAI hybrid improves citation recall by about 1.5 points over lexical + support and citation precision by about 1.7 points, but it has roughly 700+ ms p95 latency and the same unsupported false-support rate. That is not enough lift to justify the extra cost/latency or complexity.

EDA read:

- Lexical + support hits at least one expected citation on 43 of 88 supported rows.
- Hybrid + support hits at least one expected citation on 50 of 88 supported rows.
- Both still return evidence on 8 of 30 unsupported rows.
- The cleaner skips 14 unsupported requirements, mostly sales/marketing-role context.
- Remaining false support comes from broad overlap terms such as `model`, `data`, `metrics`, `analytics`, `product`, and `quality`.
- False returns concentrate around broad surface cards such as AppTrail admin/audit, AiBS analytic/front-end surfaces, SPEC metrics/governance, and ShelfOps MLOps.

This points to a representation and decision-boundary problem, not a pure retrieval-model problem. The system needs a stronger support/abstention layer and possibly more atomic evidence cards for recurring misses before a transformer or reranker will have clean signal to use.

Next targeted step:

- Inspect the 8 unsupported false-return rows and decide whether they are label-policy mistakes, overly broad evidence cards, or support-verifier misses.
- Inspect the 38-45 supported misses from the lexical/hybrid EDA reports and bucket them into missing evidence, wrong wording, ranking miss, or verifier rejection.
- Only try a reranker/cross-encoder if the correct citation is present in the candidate pool but consistently ranked below weaker evidence.
- Do not promote embeddings yet; keep them as an offline comparison.

Artifacts:

- `scripts/apply_resume_curated_review_labels.py`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed/curated_jd_cases_reviewed.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed/summary.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-raw-lexical/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-lexical-support/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-openai-embedding/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-openai-hybrid/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-lexical-support/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-curated-evidence-reviewed-eval-openai-hybrid/eda_report.md`

### D-021: Prompt-Only Resume Tailoring Control Run

Question: before writing the resume-tailoring case study, can we show why a prompt-only resume rewrite is not enough for a product-facing resume tool?

Decision: yes. The control run is useful evidence, and it supports the pivot away from full automatic rewriting toward an evidence-guided resume assistant.

Experiment setup:

- Input resume: `/Users/colbyreichenbach/Desktop/work/ColbyReichenbach_Resume_1.pdf`
- Runner: `scripts/run_resume_prompt_tailoring_experiment.py`
- Model: `gpt-4o`
- Privacy behavior: resume text was redacted for email, phone, and URL values before the model call.
- Close-fit case: Ironclad Senior Staff Data Scientist, AI.
- Near-miss case: Anthropic Data Scientist, Marketing.
- Prompt modes:
  - `lazy`: generic "tailor my resume and make it ATS optimized" prompt.
  - `engineered`: factual-accuracy prompt that requires changed-bullet evidence, unsupported requirements, and risk notes.

Results:

| Case | Mode | Prompt tokens | Output tokens | Total tokens | Latency | Est. cost |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Ironclad Senior Staff Data Scientist, AI | lazy | 972 | 692 | 1,664 | 6.8s | $0.01 |
| Ironclad Senior Staff Data Scientist, AI | engineered | 1,151 | 1,143 | 2,294 | 10.0s | $0.02 |
| Anthropic Data Scientist, Marketing | lazy | 938 | 765 | 1,703 | 9.7s | $0.01 |
| Anthropic Data Scientist, Marketing | engineered | 1,117 | 912 | 2,029 | 8.2s | $0.02 |

The pricing uses `backend/services/ai_pricing.py` local pricing config and should be verified against provider pricing before publication.

Manual read:

- The lazy Ironclad run produced polished but unsupported exact-match claims such as dashboards tracking model accuracy/regression trends, partnering with AI engineers to run A/B tests, golden datasets, annotation guidelines, error taxonomies, and user intent classification.
- The engineered Ironclad run behaved better: it preserved more of the original resume and explicitly listed golden datasets, annotation guidelines, prompt clustering, and error taxonomies as weak or unsupported.
- The lazy Anthropic Marketing run added or implied unsupported marketing-specific experience, including causal inference studies, marketing campaign effectiveness, go-to-market strategy, acquisition/retention questions, and customer behavior/channel tradeoff recommendations.
- The engineered Anthropic Marketing run again behaved better, but still produced a tailored resume for a role where the reviewed evidence labels say the marketing-specific requirements are unsupported.

Evidence-grounded comparison:

- Reviewed lexical + support found one cited Ironclad bullet for `CUR-SPEC-MODEL-EVIDENCE`.
- Reviewed OpenAI hybrid + support found one cited Ironclad bullet for `CUR-APPTRAIL-ANALYTICS-AUDIT`.
- The Anthropic Marketing case had no verified evidence-grounded rows in the reviewed hybrid output; only prompt-only placeholders existed.

Interpretation:

The prompt-only model can make the resume sound strong, but it cannot prove that each tailored claim is true. A stricter prompt reduces the damage and makes unsupported requirements visible, but it still does not solve grounding. The product problem is therefore not "can an LLM write a better-looking resume?" The product problem is "can AppTrail retrieve verified project evidence, suggest honest bullets, and abstain when the evidence is weak?"

Product decision:

- Keep prompt-only rewriting as a negative/control condition for the article.
- Keep engineered prompting as a better baseline, not the final architecture.
- Continue toward an AI-guided resume assistant:

```text
resume + JD
  -> requirement extraction
  -> curated project evidence retrieval
  -> support verification
  -> suggested projects / suggested bullets / unsupported gaps
  -> optional LLM wording pass using only verified evidence
```

Artifacts:

- `scripts/run_resume_prompt_tailoring_experiment.py`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/prompt_experiment_summary.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030445Z/exp-v3-ironclad-senior-staff-ds-ai/lazy/output.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030445Z/exp-v3-ironclad-senior-staff-ds-ai/engineered/output.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030506Z/exp-v3-anthropic-ds-marketing/lazy/output.md`
- `docs/ai-artifacts/generated/resume-tailoring-prompt-experiment/20260514T030506Z/exp-v3-anthropic-ds-marketing/engineered/output.md`

## Current Recommendation

Stay offline.

Do not build user-facing resume tailoring from the current retriever. The right next step is not "try a better model" in isolation. The right next step is:

```text
fixed expansion benchmark
  -> human-review curated evidence cards and citation labels
  -> keep lexical + cleaner/support as the cheap baseline
  -> rerun embeddings only as a comparator
  -> only then consider reranking / cross-encoder support
```

The paper/story later should be framed around this sequence:

1. Prompt-only resume tailoring sounds good but creates unsupported claims.
2. Evidence grounding solves the hallucination problem only if retrieval is good.
3. Messy project reports need curated, resume-safe evidence cards.
4. Lexical retrieval is interpretable and cheap, and it gets much better when the evidence layer is clean.
5. EDA shows exactly why the earlier runs failed: generic overlap, missing citation coverage, and noisy cards.
6. Embeddings/transformers become justified only after the eval proves ranking is the bottleneck, not missing evidence or weak labels.

## Source Artifacts

- `backend/services/evals/resume_project_ingest.py`
- `backend/services/evals/resume_tailoring_eval.py`
- `backend/services/evals/resume_requirement_cleaner.py`
- `scripts/run_resume_tailoring_evidence_eval.py`
- `scripts/build_resume_tailoring_jd_label_pack.py`
- `scripts/convert_resume_jd_label_pack_to_eval_cases.py`
- `scripts/analyze_resume_retrieval_eval.py`
- `docs/ai-artifacts/resume-tailoring-real-project-ingest-goal2a-progress.md`
- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-cleaner-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-cleaner-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-label-pack/jd_requirement_label_queue_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/jd_requirement_label_queue_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3/README.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3/source_manifest.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3/jd_requirement_label_queue_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation/jd_cases_parent_citation_labeled.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation/evidence_cards_atomic_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation/atomic_miss_eda.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-expansion-v3-parent-citation-eval-parent-child-support-gated/metrics.json`
