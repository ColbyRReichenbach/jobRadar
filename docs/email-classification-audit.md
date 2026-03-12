# Email Classification Audit

Use this workflow to review how AppTrail classifies synced email into:

- `filter`
- `inbox`
- `conversation`

And, for inbox items, whether the tag is right:

- `interview_request`
- `rejection`
- `offer`
- `action_item`
- `job_update`

## 1. Export Audit CSV

Export the latest synced emails for a user:

```bash
python3 scripts/export_email_audit.py --user-email YOUR_EMAIL --limit 250 --output audit/email_audit.csv
```

Useful options:

```bash
python3 scripts/export_email_audit.py --user-email YOUR_EMAIL --use-stored-only --output audit/email_audit.csv
python3 scripts/export_email_audit.py --user-email YOUR_EMAIL --include-hidden --output audit/email_audit.csv
```

Notes:

- default behavior re-runs the classifier so you can compare current predictions against stored values
- `--use-stored-only` exports what is already in the database without re-calling the LLM
- `--include-hidden` includes locally hidden/dismissed email

## 2. Review The CSV

Open the CSV in Sheets or Excel and fill these columns:

- `review_correct`
  - use `yes` or `no`
- `review_expected_decision`
  - use `filter`, `inbox`, or `conversation`
- `review_expected_classification`
  - use the expected tag if classification was wrong
- `review_expected_network_contact`
  - use `true` or `false`
- `review_reason`
  - short note describing why it was wrong

Key exported columns:

- `existing_classification`
- `existing_decision`
- `predicted_classification`
- `predicted_decision`
- `predicted_inbox_tag`
- `predicted_network_contact`
- `predicted_summary`
- `predicted_key_sentence`

## 3. Analyze Results

Summarize review accuracy and confusion:

```bash
python3 scripts/analyze_email_audit.py audit/email_audit.csv
```

This reports:

- reviewed count
- accuracy
- decision confusion
- classification confusion
- false positives / false negatives / misbucket counts
- top bad domains and senders
- top review reasons

## 4. Generate Rule Suggestions

Suggest likely allow/deny candidates and repeated phrases:

```bash
python3 scripts/suggest_email_classifier_rules.py audit/email_audit.csv
```

Tune sensitivity:

```bash
python3 scripts/suggest_email_classifier_rules.py audit/email_audit.csv --min-hits 3
```

This reports:

- candidate denylist domains
- candidate denylist senders
- candidate allowlist domains/senders
- repeated promotional/system phrases
- repeated class-confusion phrases

## 5. Draft Patch Material

Generate code-shaped draft constants:

```bash
python3 scripts/draft_email_classifier_patch.py audit/email_audit.csv --output audit/draft_classifier_patch.txt
```

This creates draft Python snippets for:

- non-job notification domains
- non-job senders
- human allowlist domains/senders
- promotional/system phrase hints
- repeated phrase-driven reclassification buckets

## Recommended Review Policy

For AppTrail, optimize for **recall** over precision:

- it is worse to hide a real job email than to let a little noise through
- only suppress email automatically when confidence is high that it is irrelevant
- if uncertain, keep it visible

Operationally:

- `false_negative` is higher severity than `false_positive`
- real recruiter mail should be favored over aggressive filtering
- no-reply/tooling/product/promo/alumni noise should be suppressed conservatively but consistently
