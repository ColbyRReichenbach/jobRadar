# Gmail LR Shadow Eval Progress

## Status

Completed a local-only TF-IDF + Logistic Regression route-classifier shadow eval against the newly labeled policy-corrected Gmail CSV. No production routing code was changed and no ML path was promoted.

## Inputs

- New policy-corrected labels: `audit/runs/gmail_labeling_sample/2026-05-12T20-40-container/label_queue_priority_policy_corrected.csv`

Note: an earlier cumulative run also included the prior 2026-05-07 label file, which contained stale `predicted_route=inbox` values from the older classifier surface. The current artifact below is the source-correct new-only run.

## Output Artifacts

Latest artifact directory:

- `audit/runs/gmail_lr_shadow_eval/2026-05-12Tnew-only-policy-corrected/`

Files written:

- `cumulative_labeled_dataset.csv`
- `metrics.json`
- `predictions.csv`
- `report.md`

## Dataset Summary

- Source rows: 180
- Labeled eval rows: 178
- Skipped rows: 2 missing expected route/subtype
- Unique sender domains: 38
- Source/account groups: 3

Expected route counts:

- `filter`: 107
- `conversation`: 48
- `application_inbox`: 17
- `action_review`: 6

Underrepresented route:

- `action_review`: 6 rows
- `application_inbox`: 17 rows

Underrepresented subtypes below 10 examples:

- `assessment_or_task`, `company_newsletter`, `finance_noise`, `interview_request`, `marketing_promo`, `referral_or_networking`, `retail_noise`, `school_or_alumni_update`, `unknown_other`

## Key Metrics

Full heuristic baseline:

- Route accuracy: 74.7%
- Macro F1: 64.4%
- Filter -> non-filter rate: 12.1%
- Non-filter -> filter rate: 31.0%
- `application_inbox` recall: 82.4%
- `conversation` recall: 43.8%

Random stratified split, mean across five folds:

- Heuristic route accuracy / macro F1: 76.9% / 66.1%
- TF-IDF/LR text route accuracy / macro F1: 94.2% / 91.6%
- TF-IDF/LR text+domain route accuracy / macro F1: 94.2% / 91.6%

Sender-domain grouped split, mean across five folds:

- Heuristic route accuracy / macro F1: 71.0% / 49.9%
- TF-IDF/LR text route accuracy / macro F1: 81.9% / 44.9%
- TF-IDF/LR text+domain route accuracy / macro F1: 81.9% / 44.9%

Source/account grouped split, mean across five folds:

- Heuristic route accuracy / macro F1: 74.2% / 43.7%
- TF-IDF/LR text route accuracy / macro F1: 55.9% / 22.0%
- TF-IDF/LR text+domain route accuracy / macro F1: 55.9% / 22.0%

## Interpretation

TF-IDF/LR is useful to keep studying, but the new-only artifact is not strong enough for promotion. Random split performance is high, but source/account grouped performance is worse than the heuristic, and sender-domain grouped LR has poor macro F1 and very weak conversation recall despite higher route accuracy. This suggests the model is over-filtering some non-filter classes when source/account context shifts.

Adding sender-domain tokens did not change the new-only result.

Recommendation: do not promote LR. Continue shadow evaluation, collect a fresh holdout batch, and keep the current heuristic path as the baseline until LR improves grouped macro F1 and non-filter recall.

## Product-Policy Cleanup

One small heuristic cleanup pass is reasonable: review the filter/conversation/application boundary for high-volume notification or job-board style senders, without tuning to individual rows from this labeled batch.

## Validation

- `python3 scripts/run_gmail_lr_shadow_eval.py --dataset new-only --timestamp 2026-05-12Tnew-only-policy-corrected`
  - Passed; wrote the audit artifacts listed above.
- `python3 -m py_compile scripts/run_gmail_lr_shadow_eval.py`
  - Passed.

The sklearn run emitted local Arrow CPU feature warnings from the environment, but the eval completed and artifacts were written.

## Next Step

Collect a fresh labeled holdout batch with more `action_review`, `application_inbox`, `interview_request`, `assessment_or_task`, `document_request`, finance/retail noise, and account/source diversity. Re-run this shadow eval on that holdout before deciding whether to add guarded LR shadow scoring to Gmail sync telemetry.
