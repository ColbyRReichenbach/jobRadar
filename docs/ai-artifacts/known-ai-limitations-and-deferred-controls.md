# Known AI Limitations And Deferred Controls

This page documents what AppTrail's AI platform is allowed to claim today, what is intentionally disabled, and what must exist before broader production rollout.

## Current Demo Posture

- Copilot backend APIs exist behind `COPILOT_ENABLED`; they should remain disabled by default until frontend, eval, red-team, and production rollout gates are implemented.
- Search should default to Postgres in local development and CI.
- OpenSearch is an enterprise-readiness adapter, not a required dependency for local or CI execution.
- Model calls in CI must use deterministic fixtures or mocked providers.
- Generated reports are evaluation and QA artifacts; runtime code must not depend on generated demo reports.
- Demo datasets must be sanitized and must not contain real personal email bodies, OAuth payloads, refresh tokens, API keys, or unrelated user data.

## Controls Required Before Public Demo

- Dashboard JWT-only Copilot access.
- Extension API keys denied from Copilot, eval, trace, report, and Admin AI Ops surfaces.
- User isolation tests for search and Copilot.
- Cited Copilot answers using only backend-retrieved user-owned records.
- No autonomous mutations by Copilot.
- Token and cost report for demonstrated AI surfaces.
- At least one classifier eval report generated from sanitized fixtures.
- Known limitations and deferred controls documented here.

## Controls Required Before Production Beta

- AI model call ledger.
- Artifact lineage.
- Per-user and global cost caps.
- Rate limits and abuse controls.
- Critical red-team pass for prompt injection, data leakage, secret leakage, unsupported claims, and PII leakage.
- Admin AI Ops telemetry dashboard.
- Trace access logs.
- Redacted trace views by default.
- Reason-gated full trace access.
- Retention and deletion policy.
- Rollback and reprocessing policy.
- Frontend/backend contract tests for AI surfaces.

## Controls Required Before Scale

- Statistical experiment governance.
- Confidence intervals for promotion reports.
- Task and query mix checks across variants.
- Shadow-test cost quotas.
- Drift monitoring.
- Queue and worker backpressure tests.
- Provider fallback plan.
- Product outcome metrics tied to AI features.
- Recurring promotion reports.

## Explicitly Deferred

These are intentionally not part of the first implementation wave:

- fine-tuning
- RLHF
- automated model promotion
- multi-annotator review system
- formal inter-annotator agreement tracking
- full causal product impact modeling
- million-user load simulation beyond projections

## What We Will Not Automate Yet

Copilot may suggest actions, but it must not directly perform high-impact actions without explicit confirmation and server-side validation.

Do not automate:

- sending emails
- submitting applications
- deleting user data
- changing account settings
- changing notification preferences
- promoting or demoting models
- exporting full traces
- granting admin access

Suggested actions must be typed, validated, and marked `requires_confirmation=true`.

## Claims We Can Make

- The system is designed around reproducible evals, model-call logging, token/cost accounting, artifact lineage, and admin review.
- The implementation plan separates demo, beta, scale, and deferred controls.
- CI/CD is part of the AI platform work, not an afterthought.
- Production Copilot and Admin AI Ops surfaces are planned to be API-backed and contract-tested.

## Claims We Cannot Make Yet

- We cannot claim Copilot quality until Copilot evals exist.
- We cannot claim search quality until Search evals exist.
- We cannot claim production-scale reliability until load, queue, and backpressure checks exist.
- We cannot claim model improvement from user feedback until feedback reward events and promotion reports are populated with real usage.
- We cannot claim enterprise model risk maturity until model cards, approval history, red-team reports, rollback evidence, and production incident runbooks exist.
