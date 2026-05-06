# Eval Dataset Governance

## Dataset Types

- Golden datasets are stable, versioned, and used for release comparison.
- Rolling datasets are recent reviewed examples used for monitoring drift.
- Red-team datasets target known failure modes and must not be optimized away without review.
- Synthetic coverage datasets exercise route bins, source-quality states, and privacy edge cases before enough DB-backed product data exists. They should be generated deterministically and treated as regression inputs, not production distribution evidence.

## Versioning

Dataset filenames include a version, for example `email_classifier_v1.jsonl`.

Synthetic generated datasets use the suffix `_synthetic_v1`, for example
`copilot_router_synthetic_v1.jsonl`.

Bump the version when:

- labels change
- examples are added or removed
- labeling guidelines change in a way that affects expected outputs
- failure taxonomy changes

## Sanitization

Committed eval data must use synthetic or sanitized examples only.

Do not commit:

- personal email addresses
- OAuth payloads
- API keys
- refresh tokens
- raw Gmail ids
- private company communication
- user-owned production data

## Review Expectations

Every dataset version should document:

- label taxonomy
- stage taxonomy
- edge-case rules
- intended use
- known blind spots

The classifier eval intentionally weights recall highly because a missed job email is more harmful than a non-job email entering the AppTrail inbox.

## Synthetic Generation

Run:

```bash
python3 scripts/generate_synthetic_eval_inputs.py
```

The generator writes deterministic sanitized fixtures for:

- Copilot route intent
- Copilot grounded answers
- Gmail classifier
- Radar evidence quality
- Search/source retrieval
- Red-team safety

Use `scripts/run_feature_artifact_suite.py --dataset-profile synthetic` to run
artifact generation against these broader synthetic inputs. Use the default
seed profile for small CI checks and hand-reviewed release comparisons.
