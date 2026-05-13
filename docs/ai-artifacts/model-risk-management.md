# Model Risk Management

Date: 2026-05-02
System: AppTrail / Opportunity Radar AI platform
Evidence status: Describes implemented model cards, experiments, promotion reports, admin review, retention helpers, and reprocessing policy.

## Model Lifecycle

| Stage | Required Evidence |
| --- | --- |
| Draft | Model card with intended use, prohibited use, limitations, prompt version, dataset version |
| Evaluation | Deterministic eval metrics and red-team results |
| Shadow | Candidate runs with shadow outputs are not user-visible |
| A/B | Sticky assignment, feedback reward events, cost and latency tracking |
| Review | Promotion report with quality, cost, guardrails, and recommendation |
| Approval | Admin review before promotion |
| Rollback | Prior model card and prompt version remain available |

## Reprocessing Policy

Reprocessing must create a new model call. We do not overwrite the original run because that would destroy audit history.

Rules:

- create a new model call for every reprocess attempt
- preserve the original artifact and link the new artifact separately
- keep the original model, prompt version, and variant visible
- mark failed reprocess attempts as failures, not silent retries
- require admin review before promotion
- rollback must restore a previous model card or prompt version
- shadow outputs are not user-visible

## Retention Policy

The model-call row is retained for aggregate analysis, but raw trace metadata can be redacted after the retention window. This preserves cost, latency, status, token usage, and lineage without keeping sensitive payloads indefinitely.

## Promotion Policy

Promotion reports can recommend a candidate, but they cannot promote it automatically. A reviewer must confirm that the quality lift or cost savings is worth the risk. If the candidate is cheaper but meaningfully worse on critical cases, it should stay shadow-only or be rejected.

## What Would Improve This Further

- independent labeled eval sets
- reviewer agreement metrics
- queue backpressure tests
- model drift monitoring
- formal change tickets for model-card approval
- provider failover exercises
