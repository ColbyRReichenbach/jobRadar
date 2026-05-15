# Resume Tailoring Goal 2A - Real Project Evidence Ingest + Privacy Preflight

Date: 2026-05-13

## Scope

Implemented the next offline foundation for evidence-grounded resume tailoring. This adds deterministic ingest and privacy preflight for messy project markdown docs, such as broad codebase reports with mixed implementation notes, raw inventories, verification dumps, and unsafe appendix material.

Production resume tailoring behavior is unchanged. No embeddings, reranker, LLM extraction, external API call, or production UX path was added.

## What Changed

- Added `backend/services/evals/resume_project_ingest.py`.
- Extended `backend/services/evals/resume_tailoring_eval.py` to ingest extracted project-doc evidence cards.
- Extended `scripts/run_resume_tailoring_evidence_eval.py` with `--project-doc-dir`.
- Added sanitized messy markdown fixture: `tests/fixtures/resume_tailoring/project_docs/messy_codebase_report.md`.
- Expanded `tests/test_resume_tailoring_eval.py` for project-doc preflight, extraction, noise exclusion, retrieval, atomic-card aliases, and abstention behavior.

## Preflight

The project-doc preflight is deterministic and local-only. It reports:

- raw email addresses
- phone numbers
- URLs
- secret-like assignments
- likely API keys
- long IDs
- file paths
- suspicious prompt-injection text

The result has `pass`, `warn`, or `block` status plus structured findings and redacted samples. The committed messy fixture intentionally produces `warn` because the unsafe examples are sanitized placeholders. Unredacted key-shaped strings produce `block`.

## Evidence Extraction

The markdown extractor:

- parses heading paths and sections
- excludes low-value inventory/noise sections
- extracts implementation-heavy bullets into resume-safe evidence cards
- assigns stable evidence IDs
- tags skills deterministically
- infers claim type and evidence strength
- marks card-level `resume_safe`
- preserves source file, source section, preflight status, and preflight reasons

The eval indexes only `resume_safe=true` cards through `UserKnowledgeDocument` and `DocumentChunk`.

## Local Private Docs

Private project docs can be evaluated locally with:

```bash
python3 scripts/run_resume_tailoring_evidence_eval.py --project-doc-dir /path/to/ignored/private/project-docs
```

Those files are not required for committed tests and should remain in ignored local paths unless sanitized.

## Local JD Label Pack

Added `scripts/build_resume_tailoring_jd_label_pack.py` to turn saved local app jobs plus private project markdown reports into a human-labeling pack for the next retrieval eval. The pack is generated under the ignored path:

- `docs/ai-artifacts/generated/resume-tailoring-jd-label-pack/`

Latest local run used five saved jobs with usable JD text from the local Docker Postgres export:

- Visa: Product Analyst - Generative AI Platform
- Visa / 110 Visa U.S.A. Inc.: Data Scientist
- Wd5 saved row with Target JD text: Applied Data Scientist - Search Ranking (Applied ML, LLMs, NLP)
- DraftKings: Analyst I, Customer Forecasting
- DraftKings: Analyst II, Customer Experience Analytics

It also added five curated external control roles:

- BlueConic: Customer Account Executive
- Dorsia: Brand Marketing Manager
- Maven Robotics: Machine Learning Engineer - Robot Perception
- MVP Robotics: Robotics Software Engineer
- AstraZeneca / Bioinformatics Control: Data Scientist - Single-Cell Bioinformatics

It also used six private project reports from the local Downloads folder:

- AppTrail / jobRadar
- AiBS / ABS Observatory
- Augusta Defended
- Pulse Tracker
- ShelfOps
- SPEC NYC

Generated counts:

- saved/app JDs with usable text: 5
- curated external control JDs: 5
- project docs scanned: 6
- resume-safe evidence cards: 54
- candidate JD requirement rows: 45
- evidence-card preflight status: all generated cards were `pass`

Use `jd_requirement_label_queue_compact.csv` for manual labeling. It keeps the row compact:

- one job + requirement per row
- `expected_evidence_ids` field for reviewed supporting evidence
- optional `support_label` field (`direct`, `partial`, `none`, `unsure`)
- top suggested evidence IDs
- top evidence options in one wrapped cell

Use `evidence_cards_compact.csv` as the compact lookup table. The full `jd_requirement_label_queue.csv` and `evidence_cards.csv` remain available for scripts.

The compact and full queues have lexical evidence suggestions, but those suggestions are not truth. Manual labeling filled the current local queue with:

- direct support rows: 12
- partial support rows: 15
- unsupported rows: 18
- rows with reviewed evidence IDs: 25
- total reviewed evidence ID references: 77

Use `direct` when the evidence supports the requirement cleanly. Use `partial` when the evidence supports the transferable skill but not the exact business domain or every qualifier in the requirement. The unsupported rows are intentionally blank in `expected_evidence_ids` so later generation tests can check abstention behavior.

Converted labeled cases:

- `docs/ai-artifacts/generated/resume-tailoring-jd-label-pack/jd_cases_labeled.json`

First real-project retrieval eval artifact:

- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval/report.md`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval/metrics.json`

Latest real-project eval used `--skip-manual-project-fixtures`, so the committed toy project evidence did not contaminate the result. It indexed only the 54 resume-safe cards extracted from the six private project reports.

Real JD retrieval summary at `k=5`:

- cases: 10
- requirements: 45
- requirements with expected evidence: 25
- overall recall@5: 16.7%
- overall precision@5: 5.3%
- overall MRR: 0.197333
- unrelated evidence rate: 94.7%
- direct rows recall@5: 16.7%
- partial rows recall@5: 16.7%
- near-miss control recall@5 on supported transferable rows: 25.0%
- true negative control unsupported false-support rate: 100.0%
- evidence-grounded deterministic bullet unsupported rate: 0.0%
- evidence-grounded generated requirements: 9
- evidence-grounded correct abstentions: 20
- evidence-grounded missed supported requirements: 16

Interpretation: raw lexical retrieval is too noisy and misses too much direct support on this real project/JD set. The deterministic generation gate avoids unsupported bullets because it only generates when retrieved evidence intersects reviewed expected evidence, but the retriever itself still returns unrelated evidence for unsupported and negative-control rows.

Acceptance-gated eval artifact:

- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/report.md`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-gated/eda_report.md`

The gate is eval-only. Production retrieval behavior is unchanged. It fetches a wider lexical candidate set, rejects candidates that only match generic terms, rejects candidates missing domain anchors for controls like robotics, sales, marketing, hospitality, and bioinformatics, reranks accepted evidence by non-generic overlap, and allows `no acceptable evidence`.

Acceptance-gated retrieval summary at `k=5`:

- overall recall@5: 37.7% vs 16.7% raw lexical
- overall precision@5: 52.1% vs 5.3% raw lexical
- MRR: 0.524667 vs 0.197333 raw lexical
- unrelated evidence rate: 39.0% vs 94.7% raw lexical
- missing evidence rate: 62.3% vs 83.3% raw lexical
- rows without expected evidence that still returned evidence: 3 vs 20 raw lexical
- accepted unsupported false-support rate: 15.0% vs 100.0% raw lexical
- negative-control false-support rate: 0.0%
- near-miss-control unsupported false-support rate: 0.0%
- evidence-grounded generated requirements: 18 vs 9 raw lexical
- evidence-grounded unsupported requirement generations: 0

What it fixed: the sales, marketing, hospitality, robotics, and bioinformatics negative/near-miss controls mostly abstain now instead of accepting generic `data`, `model`, `pipeline`, `product`, `field`, `path`, `support`, or `value` overlap. It also recovered more direct saved-app evidence because accepted candidates are reranked after the gate instead of preserving raw lexical order.

What remains weak: saved-app partial rows still produce some unrelated evidence, especially broad analytics/dashboard/product claims. Seven supported rows still miss reviewed evidence. This means the next retrieval experiment should compare this gate against a hybrid retriever, not move directly to user-facing generation.

## Artifact Results

Generated artifact:

- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/report.md`
- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-evidence-eval/evidence_cards.csv`

Latest local run used:

```bash
python3 scripts/run_resume_tailoring_evidence_eval.py --project-doc-dir tests/fixtures/resume_tailoring/project_docs
```

Project-doc ingest summary:

- project docs scanned: 1
- preflight statuses: `{"warn": 1}`
- preflight reasons: `file_path`, `likely_api_key`, `long_id`, `prompt_injection`, `raw_email`, `raw_phone`, `raw_url`, `secret_assignment`
- extracted evidence cards: 7
- resume-safe evidence cards: 6
- excluded/noise sections: 5
- excluded reasons: `noise_heading`, `not_implementation_heavy`

Eval summary:

- Recall@3: 100.0%
- Precision@3: 30.6%
- MRR: 1.0
- Missing evidence rate: 0.0%
- Unrelated evidence rate: 69.4%
- Evidence-grounded abstentions: 1
- Evidence-grounded correct abstentions: 1
- Evidence-grounded unsupported requirement generations: 0
- Prompt-only unsupported bullet rate: 100.0%
- Evidence-grounded unsupported bullet rate: 0.0%
- Model calls: 0

## What Improved

- Broad project reports can now be preflighted before they become resume evidence.
- Unsafe/private material is detected and summarized without model calls.
- Messy markdown docs are split into evidence cards instead of one broad retrieval blob.
- Low-value inventory and verification sections are excluded from evidence indexing.
- Retrieval can target specific extracted evidence cards.
- Unsupported requirements abstain instead of generating evidence-grounded bullets.

## Limitations

- Extraction is heuristic and deterministic; it will miss nuanced evidence and can over-extract implementation-like bullets.
- Card-level `resume_safe` does not mean the whole source document is safe to share.
- Precision improved with the acceptance gate, but saved-app partial rows still return unrelated evidence in top-k.
- The fixture is sanitized and small; real private docs need local review before claims about production quality.
- No LLM generation quality is measured in this goal.
- The generated JD label pack is now labeled, but it still needs conversion into `jd_cases.json` before it becomes a runnable retrieval eval artifact.
- Two saved rows still expose app-data hygiene issues: `Wd5` stores a Target JD, and `110 Visa U.S.A. Inc.` should be normalized to Visa for presentation.

## Next Recommendation

Stay offline. The acceptance gate materially improved lexical retrieval, but the remaining misses show that lexical matching is still not enough. Next, compare this gated lexical baseline against hybrid/embedding retrieval using the same 45-row labeled set. Do not move to user-facing generation until retrieval can recover direct support without flooding negative and near-miss rows with unrelated evidence.

## Holdout v2

Added a fresh local holdout pack for validation, not tuning:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/curated_holdout_jds_v2.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/source_manifest.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/jd_requirement_label_queue_compact.csv`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/evidence_cards_compact.csv`

The 25 roles were collected from current public Ashby/Greenhouse job-board APIs on 2026-05-13. The mix is:

- 15 likely-fit / strong-fit data, AI, retrieval, eval, analytics, or product data roles
- 6 near-miss technical controls: risk intelligence, integrity, ads ML, genomics, AI biology, and robotics
- 4 true-negative controls: sales, account executive, integrated marketing, and brand marketing

The generated compact queue has 112 candidate requirement rows. Leave the current tuned 45-row diagnostic set alone. Label this v2 holdout independently, then run the gated lexical baseline unchanged. If performance holds up, use this same v2 holdout to compare hybrid retrieval. If it drops, treat the drop as evidence of where the retrieval architecture is brittle rather than hand-tuning rules to this set.

Manual v2 labels were added on 2026-05-13 after reviewing the requirement rows against the 54 extracted project evidence cards:

- direct support rows: 6
- partial/transferable support rows: 51
- unsupported rows: 55
- rows with reviewed evidence IDs: 57
- converted cases: `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2/jd_cases_labeled.json`

Labeling policy was intentionally conservative. Boilerplate, compensation, EEO text, founder bios, sales-only requirements, marketing requirements, company funding blurbs, and broad mission statements were labeled `none`. Product-context rows were labeled `partial` only when the project evidence would be reasonable to cite as transferable context. Domain-specific biology, hospitality, sales, and marketing rows were left unsupported unless a real transferable system skill was present.

First unchanged gated lexical baseline on the v2 holdout:

- requirements: 112
- supported requirements: 57
- unsupported requirements: 55
- recall@5: 25.7%
- precision@5: 20.4%
- MRR: 0.355556
- unrelated evidence rate: 74.2%
- missing evidence rate: 74.3%
- unsupported rows that still returned accepted evidence: 41 of 55
- accepted unsupported false-support rate: 74.5%
- evidence-grounded unsupported bullet rate: 0.0%
- prompt-only unsupported bullet rate: 100.0%
- model calls: 0

Interpretation: this holdout is much harder than the tuned 45-row diagnostic set. The lexical gate still protects generation from unsupported bullets because generation only uses accepted evidence with reviewed labels, but retrieval itself over-matches broad terms like `product`, `data`, `metrics`, `evaluation`, `model`, and `analytics`. It also misses reviewed evidence for domain-shifted near-miss rows such as genomics, AppOmni security/risk intelligence, and Cresta AI evaluation language.

The result is useful because it prevents overfitting the next change to the first small diagnostic set. The next experiment should be a retrieval architecture comparison on this fixed v2 holdout, not another round of handcrafted lexical rules.

## JD Requirement Cleaner

Added an eval-only JD requirement cleaner before retrieval:

- `backend/services/evals/resume_requirement_cleaner.py`
- `scripts/run_resume_tailoring_evidence_eval.py --enable-requirement-cleaner`

The cleaner strips HTML and classifies each JD row as one of:

- `actual_requirement`
- `product_context`
- `company_boilerplate`
- `legal_compensation`
- `sales_marketing_role`
- `domain_only`

Rows classified as obvious boilerplate, legal/compensation, sales/marketing, or domain-only are skipped before retrieval. The cleaner decision is stored in every requirement result and summarized under `requirement_cleaner` in the artifact.

Cleaner + gated lexical artifact:

- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-cleaner-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-real-jd-eval-cleaner-gated/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-gated/eda_report.md`

Diagnostic 45-row comparison:

- recall@5: 37.7% unchanged
- precision@5: 52.1% unchanged
- accepted unsupported false-support: 15.0% unchanged
- skipped requirements: 11
- skipped supported requirements: 0
- skipped unsupported requirements: 11

Holdout v2 comparison:

- recall@5: 25.7% unchanged
- precision@5: 43.6% vs 20.4% gated lexical
- unrelated evidence rate: 51.0% vs 74.2% gated lexical
- accepted unsupported false-support: 27.3% vs 74.5% gated lexical
- unsupported rows with accepted evidence: 15 vs 41 gated lexical
- skipped requirements: 34
- skipped supported requirements: 0
- skipped unsupported requirements: 34
- evidence-grounded unsupported bullet rate: 0.0%

Implementation note: the first cleaner pass was too aggressive because it missed general AI/retrieval terms such as `RAG`, `LLM`, `AI`, `pipelines`, `experimentation`, `semantic`, `heuristics`, `testing`, and connector terms like `GitHub` and `Slack`. It also treated `Salesforce` as sales-role evidence when it appeared as an enterprise connector. Those issues were corrected before the final cleaner artifacts above.

Decision: cleaner + gated lexical is now the baseline for the next retrieval experiment. After the atomic-card test below, the next targeted step is multi-granularity retrieval, then a fixed-holdout comparison against hybrid/embedding retrieval.

## Atomic Evidence Card Experiment

Tested whether narrower evidence cards would fix broad lexical false positives.

Implementation:

- Added `--project-doc-granularity atomic_claim` to `scripts/run_resume_tailoring_evidence_eval.py`.
- Default extraction remains `section_claim`.
- Atomic child cards carry `parent_evidence_id` aliases so the existing labels do not need to be rewritten.
- Eval rows now include child-parent match metadata: `returned_evidence_aliases`, `returned_evidence_matches`, and `matched_expected_evidence_ids`.

Holdout v2, cleaner + gated comparison:

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

Atomic cards slightly reduced false support, but recall dropped. That suggests the broad cards are not only noise; they also provide useful project-level context for lexical retrieval. The issue is representation granularity, not simply a need for smaller cards.

Decision:

Do not switch fully to atomic cards. The next targeted experiment should retrieve at multiple granularities: use broader project/section cards for recall, then child evidence cards for citation-level grounding and support checks. This keeps the useful context while reducing unsupported evidence at the final citation layer.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/eda_report.md`

## Parent-Child Lexical Retrieval

Tested the multi-granularity idea as an eval-only two-stage retrieval strategy:

```text
rank broad parent cards
  -> expand top parents into child evidence cards
  -> rerank child cards with lexical/support features
  -> cite accepted child evidence only
```

This is a coarse-to-fine retrieval pipeline. In ML/product-search language, it is also a rank-then-rerank setup.

Implementation:

- Added `--retrieval-strategy parent_child_lexical`.
- Indexed section-level parent cards for recall.
- Expanded retrieved parents into atomic child cards for final support/citation.
- Preserved parent aliases so existing v2 labels still score against the original reviewed evidence IDs.
- Widened parent and child candidate pools after the first run showed premature truncation.

Holdout v2, cleaner + gated comparison:

| Metric | Section cards | Atomic only | Parent-child lexical |
| --- | ---: | ---: | ---: |
| recall@5 | 25.7% | 18.6% | 20.5% |
| precision@5 | 43.6% | 43.1% | 45.0% |
| MRR | 0.355556 | 0.251170 | 0.287719 |
| unrelated evidence rate | 51.0% | 49.7% | 49.6% |
| accepted unsupported false-support | 27.3% | 25.5% | 29.1% |
| unsupported rows with accepted evidence | 15 | 14 | 16 |

Interpretation:

The approach improved precision and unrelated evidence rate slightly, but it still lost too much recall and slightly worsened unsupported false-support. That is useful negative evidence. It means the current bottleneck is not just card granularity; lexical matching still fails on semantic phrasing and transferable-skill requirements.

Decision:

Keep cleaner + gated section-card lexical as the baseline. Parent-child representation remains useful for later citation control, but lexical-only parent-child retrieval is not enough. The next experiment should compare hybrid/embedding retrieval against the fixed cleaner + gated section baseline, then optionally use parent-child expansion after the retriever has found the right project/section.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/eda_report.md`

## OpenAI Embedding Retrieval

Tested eval-only embedding retrieval using `text-embedding-3-small`.

Both sides were embedded:

- JD side: cleaned requirement text plus the case title
- project side: resume-safe evidence text plus project title, section path, skill tags, and claim type

Strategies tested:

- `openai_embedding` over section cards
- `openai_hybrid` over section cards
- `openai_embedding` over atomic cards

The acceptance gate was made embedding-aware for these runs: a strong embedding similarity can satisfy the non-generic-overlap check, but missing domain anchors still block support.

Holdout v2 comparison:

| Metric | Section lexical | OpenAI section embedding | OpenAI hybrid | OpenAI atomic embedding |
| --- | ---: | ---: | ---: | ---: |
| recall@5 | 25.7% | 25.9% | 25.9% | 25.4% |
| precision@5 | 43.6% | 42.0% | 42.0% | 44.8% |
| MRR | 0.355556 | 0.356140 | 0.356140 | 0.279532 |
| unrelated evidence rate | 51.0% | 52.6% | 52.6% | 48.0% |
| accepted unsupported false-support | 27.3% | 30.9% | 30.9% | 30.9% |
| unsupported rows with accepted evidence | 15 | 17 | 17 | 17 |

Interpretation:

Embeddings did not unlock a recall jump on this holdout. Section embeddings tied recall but increased false support. Atomic embeddings improved precision and unrelated evidence rate, but still worsened false support. This means the next bottleneck is support verification: the system can find plausible evidence, but it still needs a better way to decide whether that evidence is actually safe to cite.

Decision:

Do not promote embeddings. Keep cleaner + gated section-card lexical as the baseline. The next targeted experiment should be a pairwise support verifier over candidate requirement/evidence pairs, then rerun lexical and embedding candidates through that verifier.

Artifacts:

- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-hybrid/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-hybrid/eda_report.md`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding-atomic/metrics.json`
- `docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-openai-embedding-atomic/eda_report.md`

## Validation

- `pytest -q tests/test_resume_tailoring_eval.py`
- `python3 scripts/run_resume_tailoring_evidence_eval.py --project-doc-dir tests/fixtures/resume_tailoring/project_docs`

Final validation also ran:

- `pytest -q tests/test_resume_tailoring_eval.py tests/test_resume_tailor.py tests/test_retrieval_foundation.py`
- `python3 -m py_compile backend/services/evals/resume_project_ingest.py backend/services/evals/resume_tailoring_eval.py scripts/run_resume_tailoring_evidence_eval.py scripts/build_resume_tailoring_jd_label_pack.py scripts/convert_resume_jd_label_pack_to_eval_cases.py`
- `python3 scripts/run_resume_tailoring_evidence_eval.py --enable-requirement-cleaner --project-doc-granularity atomic_claim ...`
- `python3 scripts/analyze_resume_retrieval_eval.py --metrics docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/metrics.json --evidence docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-atomic-gated/evidence_cards.csv`
- `python3 scripts/run_resume_tailoring_evidence_eval.py --enable-requirement-cleaner --retrieval-strategy parent_child_lexical ...`
- `python3 scripts/analyze_resume_retrieval_eval.py --metrics docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/metrics.json --evidence docs/ai-artifacts/generated/resume-tailoring-jd-holdout-v2-eval-cleaner-parent-child-gated/evidence_cards.csv`
- `python3 scripts/run_resume_tailoring_evidence_eval.py --enable-requirement-cleaner --retrieval-strategy openai_embedding ...`
- `python3 scripts/run_resume_tailoring_evidence_eval.py --enable-requirement-cleaner --retrieval-strategy openai_hybrid ...`
- `python3 scripts/run_resume_tailoring_evidence_eval.py --enable-requirement-cleaner --retrieval-strategy openai_embedding --project-doc-granularity atomic_claim ...`
- `git diff --check`

## Pairwise Support Verifier Follow-Up

Implemented an eval-only deterministic support verifier after the embedding runs showed that semantic similarity was finding plausible evidence but not reliably safe-to-cite evidence.

What changed:

- Added `backend/services/evals/resume_support_verifier.py`.
- Added `--enable-support-verifier` to `scripts/run_resume_tailoring_evidence_eval.py`.
- Added support-verifier metrics to eval artifacts and EDA reports.
- Added focused tests for the verifier and harness integration.

Fixed v2 holdout results:

| Strategy | Recall@5 | Precision@5 | Unrelated rate | False-support |
| --- | ---: | ---: | ---: | ---: |
| Cleaner + section lexical | 25.7% | 43.6% | 51.0% | 27.3% |
| Cleaner + section lexical + verifier | 21.6% | 46.9% | 39.7% | 21.8% |
| Cleaner + parent-child lexical | 20.5% | 45.0% | 49.6% | 29.1% |
| Cleaner + parent-child lexical + verifier | 20.5% | 49.9% | 38.5% | 21.8% |
| Cleaner + OpenAI section embedding + verifier | 20.6% | 43.1% | 43.5% | 29.1% |
| Cleaner + OpenAI hybrid + verifier | 20.6% | 43.1% | 43.5% | 29.1% |
| Cleaner + OpenAI atomic embedding + verifier | 22.5% | 46.8% | 39.8% | 29.1% |

Read:

The verifier improved safety metrics for lexical retrieval, especially unrelated evidence and unsupported false support. The recall loss is the important warning. Some current expected labels are broad section cards, while the verifier is asking a stricter citation-level support question. That means the next fix should not be another model tweak. The next fix should separate parent-level relevance labels from child-level citation support labels, then measure each stage independently.

New artifacts:

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

## Parent vs Citation Label Split

Added a split-label eval path because the verifier results showed that the old labels were doing two jobs at once:

- broad parent relevance: does this project/section support the requirement at all?
- exact citation support: is this specific evidence card safe to cite in a generated resume bullet?

What changed:

- `RequirementCase` now supports optional `expected_parent_evidence_ids` and `expected_citation_evidence_ids`.
- Eval rows now report parent and citation metrics separately.
- Added `scripts/build_resume_parent_citation_labels.py` to create a diagnostic split-label artifact.

Derived label artifact:

- parent-labeled requirements: 57
- citation-labeled requirements: 39
- parent-supported rows without citation labels: 18
- accepted citation IDs: 145

The citation labels are machine-derived from the support verifier, so they are diagnostic, not final truth.

Split-label eval results:

| Strategy | Parent recall@5 | Parent precision@5 | Citation recall@5 | Citation precision@5 | False-support |
| --- | ---: | ---: | ---: | ---: | ---: |
| Section lexical + verifier | 21.6% | 46.9% | 10.1% | 48.6% | 21.8% |
| Parent-child lexical | 20.5% | 45.0% | 40.2% | 53.6% | 29.1% |
| Parent-child lexical + verifier | 20.5% | 49.9% | 40.2% | 59.4% | 21.8% |
| OpenAI atomic embedding + verifier | 22.5% | 46.8% | 42.6% | 55.8% | 29.1% |

Read:

Parent-child retrieval is doing what we hoped at the citation layer. It is much better than section retrieval at finding exact citation cards. The remaining weakness is parent recall: it still misses too many broad relevant project areas. OpenAI atomic embeddings improve citation recall slightly but bring false support back up, so they are not a clean promotion candidate.

Next work:

- Human-review the 39 derived citation-labeled rows.
- Review the 18 parent-supported rows where the verifier found no citation labels.
- Rerun parent-child + verifier after that review.
- Consider a reranker only if the right evidence appears in candidates but ranks too low or gets filtered incorrectly.
