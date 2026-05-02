# Architecture Walkthrough

Date: 2026-05-02
System: AppTrail / Opportunity Radar AI platform
Evidence status: Describes current implementation shape and explicitly labels future scale work.

## System Layers

| Layer | Responsibility |
| --- | --- |
| Dashboard | User workflows, Admin AI Ops, typed API clients |
| FastAPI backend | Auth, data contracts, AI orchestration, search, telemetry |
| Postgres-compatible database | Application data, search documents, AI ledger, artifacts, model cards |
| AI provider | Model inference behind backend-controlled prompts and retrieval |
| CI checks | Backend tests, dashboard build, Playwright smoke tests, AI feature gates |

## AI Call Path

1. Frontend calls an authenticated backend endpoint.
2. Backend validates user identity and request shape.
3. Backend retrieves only user-authorized context.
4. AI orchestration chooses task config, model, prompt version, and variant.
5. The AI provider returns output and token usage.
6. Backend validates and persists a model-call ledger row.
7. User-visible outputs are saved as artifacts linked to the model call.
8. Admin AI Ops exposes redacted telemetry and lineage.

## Data Contracts

The frontend uses typed API clients for Admin AI Ops. The backend returns structured objects for telemetry, runs, artifacts, experiments, model cards, promotion reports, and access logs. Hardcoded values are limited to tests and static interview artifacts.

## Search And Retrieval

The search index is user-scoped. Copilot and Radar should retrieve through backend services instead of trusting client-side filters. This prevents one user's records from becoming another user's model context.

## Observability

The AI ledger captures:

- surface and task
- provider and model
- prompt version and variant
- latency and status
- token breakdown
- estimated cost
- fallback and validation state
- sanitized metadata

Admin AI Ops aggregates these into cost, latency, reliability, freshness, queue, and experiment guardrail views.

## Scale Posture

Ready now:

- deterministic tests for the core ledger and admin telemetry
- feature-flagged Admin AI Ops
- token and cost accounting
- promotion reports requiring admin review

Required before enterprise-scale claims:

- load and queue backpressure tests
- production observability drains
- provider failover exercises
- formal incident runbooks
- larger labeled eval datasets
- privacy review of full trace retention windows
