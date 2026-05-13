# AI Governance Artifact

Date: 2026-05-02
System: AppTrail / Opportunity Radar AI platform
Evidence status: Describes implemented ledger, artifact lineage, model cards, experiments, promotion reports, and Admin AI Ops routes. Future controls are labeled as deferred.

## Governance Goal

Every AI output should be reproducible enough to debug, auditable enough to review, and bounded enough to roll back.

## Governed Workflow

1. A user action or scheduled job calls a typed backend AI surface.
2. The backend creates an `ai_model_calls` row with model, prompt version, variant, token usage, cost estimate, latency, status, validation result, fallback state, and sanitized request/response metadata.
3. Generated user-facing outputs are linked through `ai_artifacts`.
4. Model cards define intended use, prohibited use, limitations, eval dataset version, primary metrics, guardrail metrics, approval status, rollback plan, and review cadence.
5. Experiments assign users to sticky variants or queue shadow runs.
6. Feedback reward events and model-call metrics feed promotion reports.
7. Admin AI Ops exposes telemetry, runs, redacted drilldowns, artifacts, experiments, model cards, access logs, and promotion reports.
8. Full trace access requires a reason and writes an admin access log.

## Reproducibility Contract

Each production AI run must capture:

- task name and surface
- provider and model
- prompt version
- variant or experiment key
- release version
- token breakdown
- estimated cost
- validation result
- linked artifacts
- redacted metadata by default

This enables a reviewer to answer: what ran, for whom, with which prompt/model, at what cost, producing which artifact, under which release?

## Auditability Contract

Admin views are redacted by default. Full trace access is allowed only when:

- the user is an admin
- the AI Ops feature is enabled
- the admin provides a specific reason
- the access is written to `ai_admin_access_logs`

The dashboard shows the audit log so sensitive trace access does not disappear into backend-only records.

## Promotion And Rollback

Promotion is not automatic. Candidate variants can win a report, but promotion still requires admin review. Model cards must include rollback language so a production issue can be handled by disabling the feature flag, restoring the previous prompt/model card, or rejecting the promotion.

## Retention

Trace metadata is retained only for the configured window. After `AI_TRACE_RETENTION_DAYS`, raw request/response metadata can be redacted while preserving aggregate ledger rows for cost, reliability, and model-risk reporting.

## Deferred Controls

The following are intentionally not claimed as complete:

- multi-annotator review workflow
- formal inter-annotator agreement
- automated model promotion
- million-user load validation
- provider-level disaster recovery tests

## Product Evidence

The product is a job-search intelligence platform, but the engineering story is production AI governance: every model call is measured, every generated artifact has lineage, and every model or prompt change has a review path.
