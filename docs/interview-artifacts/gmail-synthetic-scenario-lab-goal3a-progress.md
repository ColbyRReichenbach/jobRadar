# Goal 3A - Gmail Synthetic Scenario Lab and LR Augmentation Experiment

Date: 2026-05-12

## Objective

Build an offline experimentation path for Gmail route classification that can expand sparse classes with synthetic scenarios, compare TF-IDF + Logistic Regression on real-only versus real+synthetic training sets, and keep real human-labeled Gmail rows as the only promotion-quality evaluation data.

No production Gmail routing behavior was changed.

## Experiment Boundary

- `real_human` rows are truth data and remain the promotion gate.
- `real_llm_labeled` rows are assisted labels only. They are not ground truth unless a human reviews and promotes them.
- `synthetic_llm_generated` rows are training and stress-test expansion only. Synthetic-only performance is never production evidence.
- Dry-run template rows are examples for prompt/schema validation only. They are explicitly marked `training_eligible=false`.
- Real email body/subject text is not sent to an LLM. The generator prompt uses aggregate seed counts and a scenario matrix only.

## Architecture

The offline path is:

`real human-labeled seed rows -> aggregate seed summary -> scenario matrix -> LLM generator or dry-run templates -> schema validator -> diversity/dedupe filter -> synthetic scenario artifact -> LR augmentation eval -> real holdout gate`

Implemented scripts:

- `scripts/generate_gmail_synthetic_scenarios.py`
- `scripts/run_gmail_synthetic_lr_augmentation_eval.py`

The generator supports:

- `--dry-run-template`: writes deterministic prompt, schema, scenario matrix, example rows, and validation summary without calling an LLM.
- `--generate`: calls the configured OpenAI client only when `OPENAI_API_KEY` and the local package are available; otherwise falls back to dry-run examples.

## Provenance Rules

Every generated row includes:

- `source_type`
- `source_dataset`
- `synthetic_family_id`
- `generation_prompt_version`
- `label_policy_version`
- `human_reviewed`

The full synthetic row schema also includes:

- `subject`
- `sender`
- `sender_domain`
- `body`
- `expected_route`
- `expected_subtype`
- `expected_action_required`
- `expected_action_type`
- `rationale`
- `difficulty`
- `scenario_family`

Additional local safety fields are emitted:

- `generation_mode`
- `training_eligible`
- `synthetic_example_notice`

## Scenario Coverage

The scenario matrix covers sparse and high-risk Gmail classes:

- `application_inbox/application_received`
- `application_inbox/application_status_update`
- `conversation/recruiter_outreach`
- `conversation/reply_needed`
- `action_review/interview_scheduling`
- `filter/job_alert`
- `filter/job_board_promo`
- `filter/marketing_promo`
- hard negatives mentioning jobs that should stay filtered
- ambiguous platform notification wrappers

Current route/subtype labels stay within the existing policy vocabulary. For example, `conversation/reply_needed` uses route `conversation` with subtype `recruiter_outreach`, and `action_review/interview_scheduling` uses route `action_review` with subtype `interview_request`.

## Validation Checks

The generator validates:

- required schema and provenance fields
- expected route and subtype labels
- action-required boolean values
- action type values
- no `human_reviewed=true` for generated rows
- duplicate and near-duplicate subject/body pairs
- body length distribution
- counts by route/subtype
- counts by scenario family
- unique sender domains
- training-eligible row count

Dry-run artifact:

- `audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-dry-run/`
- Rows input: 10
- Rows accepted: 10
- Rows rejected: 0
- Training-eligible rows: 0
- Unique sender domains: 10
- Duplicate rate: 0.0

## LR Comparison Results

Augmentation eval artifact:

- `audit/runs/gmail_synthetic_lr_augmentation_eval/2026-05-12Tgoal3a-dry-run/`

Dataset:

- Real labeled rows: 178
- Real skipped rows: 2
- Synthetic rows total: 10
- Training-eligible synthetic rows: 0

Because the dry-run synthetic rows are examples, the augmentation strategies are intentionally reported as `n/a`:

- `lr_real_plus_synthetic`: blocked by no training-eligible synthetic rows
- `lr_synthetic_only`: blocked by no training-eligible synthetic rows

Real-only comparison still ran on the same local human-labeled data:

| split | strategy | route accuracy | route macro F1 | application recall | conversation recall | action_review recall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| random stratified | heuristic | 76.9% | 66.1% | 65.0% | 51.7% | 80.0% |
| random stratified | LR real-only | 94.2% | 91.6% | 75.0% | 88.3% | 90.0% |
| sender-domain grouped | heuristic | 71.0% | 49.9% | 86.7% | 10.8% | 20.0% |
| sender-domain grouped | LR real-only | 81.9% | 44.9% | 76.7% | 6.7% | 0.0% |
| source/account grouped | heuristic | 74.2% | 43.7% | 37.3% | 32.3% | 26.7% |
| source/account grouped | LR real-only | 55.9% | 22.0% | 0.0% | 40.0% | 0.0% |

These results match the prior LR shadow finding: random splits look strong, but grouped splits expose weak generalization and sparse-class fragility.

## What Improved

- The offline synthetic data architecture is now explicit and runnable.
- Synthetic examples are isolated under `audit/runs`.
- Dry-run generation produces prompt, schema, scenario matrix, CSV, JSONL, and validation summary artifacts.
- Augmentation eval cannot accidentally train on placeholder rows because it requires `training_eligible=true`.
- The LR comparison layer can evaluate real-only, real+synthetic, and synthetic-only strategies on the same real human-labeled folds once eligible synthetic rows exist.

## What Did Not Improve Yet

- No synthetic augmentation lift was measured because no LLM-generated, training-eligible synthetic rows were produced in this run.
- The current real-only LR still appears vulnerable to sender/domain and source/account grouping shifts.
- `action_review` and `application_inbox` remain underrepresented in real truth data.
- Synthetic rows have not been human reviewed and cannot support a promotion decision.

## Live Generation Follow-Up

After `.env` loading was fixed, two live generation attempts were run:

| prompt version | artifact | result | decision |
| --- | --- | --- | --- |
| `gmail-synthetic-scenario-generator-v1` | `audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-live-synthetic/` | 9 accepted rows. Earlier generator behavior marked 9 rows training-eligible. Augmentation eval artifact: `audit/runs/gmail_synthetic_lr_augmentation_eval/2026-05-12Tgoal3a-live-synthetic/`; finding: `synthetic_augmentation_insufficient_delta`. | Too small and generic; do not use as evidence. |
| `gmail-synthetic-scenario-generator-v1` | `audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-live-synthetic-v2/` | 78 accepted rows after switching live generation to one call per scenario family. Manual spot check found semantic quality failures, including application-received rows that looked like job alerts/promos and interview-scheduling rows without scheduling cues. | Do not use for LR augmentation until reviewed or passed through a stronger critic. |
| `gmail-synthetic-scenario-generator-v2` | `audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-prompt-v2-live/` | 78 accepted rows, 0 training-eligible rows, 10 semantic warnings. Added strict label vocabulary and route/subtype pair instructions, but positive scenarios still leaked job-alert/promo examples. | Not approved for training. |
| `gmail-synthetic-scenario-generator-v3` | `audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-prompt-v3-live/` | 79 generated rows, 73 accepted rows, 6 rejected rows, 0 training-eligible rows. Rejections were attached to semantic warnings. Validator-reported semantic warnings on accepted rows dropped to 0. Manual spot check still found subtler semantic drift, such as `application_received` examples with interview/newsletter/promo-like subjects. | Best prompt so far, but still not approved for training. Requires human or critic review before `--mark-training-eligible`. |
| `gmail-synthetic-scenario-generator-v4` | `audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-prompt-v4-live/` | Added sanitized few-shot good/near-miss examples derived from the human-labeled CSV. Output shape regressed: only 34 accepted rows because several family calls returned JSON without a top-level `rows` array. Semantic rejection increased to 12 rows. | Few-shots helped expose more failures, but this version is not usable. |
| `gmail-synthetic-scenario-generator-v5` | `audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-prompt-v5-live/` | Narrowed few-shots to the active scenario family. 62 generated rows, 52 accepted rows, 10 rejected rows, 0 training-eligible rows. Output shape improved versus v4, but manual spot check still found accepted conversation rows that looked like job alerts/events. | Not approved for training. Prompting alone is insufficient; needs critic/review gate. |

The generator has since been tightened:

- Standalone CLI runs load `.env` and `.env.local`, while preserving a real `.env` `OPENAI_API_KEY` when `.env.local` leaves it blank.
- Live generated rows are no longer marked `training_eligible=true` by default.
- `--mark-training-eligible` is now required to approve generated rows for training use.
- Validation now rejects obvious route/text mismatches instead of accepting them as training rows.
- Prompt v3 includes the strict production route vocabulary, subtype vocabulary, and allowed route/subtype pairings.
- Prompt v4 introduced sanitized few-shot examples and contrastive near-misses from the human-labeled dataset.
- Prompt v5 narrowed few-shots to the current scenario family, reducing cross-family contamination but still not enough to make rows trusted automatically.
- Validation now also flags conversation rows that look like bulk job alerts, career-fair events, or interview scheduling actions.

Strict production route labels used by the generator:

- `application_inbox`
- `conversation`
- `action_review`
- `filter`
- `opportunity_discovery`

Strict production subtype labels used by the generator:

- `application_received`
- `application_status_update`
- `interview_request`
- `rejection`
- `offer`
- `assessment_or_task`
- `document_request`
- `recruiter_outreach`
- `referral_or_networking`
- `job_alert`
- `job_board_promo`
- `career_fair_or_event`
- `company_newsletter`
- `marketing_promo`
- `system_notification`
- `finance_noise`
- `retail_noise`
- `school_or_alumni_update`
- `unknown_other`

## Limitations

- Dry-run templates are not training data.
- LLM generation can produce schema-valid but semantically wrong rows; schema validation is not enough.
- Synthetic examples are fictional and useful for stress/training coverage, not for production promotion evidence.
- The available real holdout remains small and class-imbalanced.
- Grouped split metrics indicate the LR classifier may still learn sender/source patterns rather than durable route semantics.

## Validation Commands

- `python3 scripts/generate_gmail_synthetic_scenarios.py --dry-run-template --timestamp 2026-05-12Tgoal3a-dry-run`
- `python3 scripts/run_gmail_synthetic_lr_augmentation_eval.py --synthetic-dir audit/runs/gmail_synthetic_scenarios/2026-05-12Tgoal3a-dry-run --timestamp 2026-05-12Tgoal3a-dry-run`
- `python3 -m py_compile scripts/generate_gmail_synthetic_scenarios.py scripts/run_gmail_synthetic_lr_augmentation_eval.py`
- `git diff --check`

The augmentation eval completed with sandbox-only Arrow CPU feature warnings from local dependencies; the command exited successfully.

## Changed Files

- `scripts/generate_gmail_synthetic_scenarios.py`
- `scripts/run_gmail_synthetic_lr_augmentation_eval.py`
- `docs/interview-artifacts/gmail-synthetic-scenario-lab-goal3a-progress.md`

## Next Gate

Goal 3A is architecturally complete, but augmentation evidence is insufficient. The next gate should produce a small LLM-generated synthetic batch, review or explicitly approve it for training use, then rerun augmentation evaluation against a fresh real human-labeled holdout. Do not promote LR, embeddings, or hybrid retrieval/classification behavior until real-human evaluation shows durable gains on grouped splits and sparse classes.
