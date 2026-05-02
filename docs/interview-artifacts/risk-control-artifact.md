# Risk Control Artifact

Date: 2026-05-02
System: AppTrail / Opportunity Radar AI platform
Evidence status: Maps implemented controls and known limitations. This document does not claim bank-grade certification.

## Primary Risks

| Risk | Control |
| --- | --- |
| Cross-user data leakage | Backend user-scoped search index and authenticated Copilot data access |
| Secret leakage in traces | Metadata sanitization before persistence and redacted admin drilldowns |
| Overexposed admin traces | Reason-gated full trace endpoint and access log |
| Prompt injection | Retrieval and response validation patterns; critical red-team tests are required before public demo |
| Unsupported claims | Copilot answers must be grounded in retrieved records and cite source artifacts |
| Cost explosion | Per-call token and cost tracking plus budget/rate-limit controls |
| Unsafe autonomous action | Copilot suggestions require explicit user confirmation for high-impact actions |

## User Isolation

Production AI surfaces must never trust client-side filtering. The backend must scope retrieved records by authenticated user before they reach a model. Admin telemetry can aggregate across users, but drilldowns must redact sensitive metadata unless full trace access is explicitly logged.

## Admin Access

Admin AI Ops is protected by:

- admin authorization
- feature flag
- redacted default views
- reason-gated full trace access
- access-log visibility in the dashboard

## Prompt Injection

The expected control is layered:

1. limit retrieval to user-owned records
2. separate instructions from retrieved content
3. validate structured outputs
4. refuse requests that ask for secrets or unrelated user data
5. record failures in the model-call ledger
6. keep red-team cases in CI before broader rollout

## Data Leakage

Sensitive keys are sanitized before metadata persistence. Admin views also redact known sensitive fields such as raw prompts, email bodies, OAuth tokens, access tokens, refresh tokens, and API keys.

## Known Limitations

- The current artifact set uses deterministic fixtures and projections, not live enterprise traffic.
- Formal model-risk signoff is represented as an internal workflow, not a regulated bank approval process.
- Load and queue backpressure tests are still required before enterprise-scale claims.
- Automated model promotion is intentionally deferred.

## Interview Story

The risk posture is not "the model is smart." The risk posture is "the model is boxed in by backend data access, logged every time it runs, redacted by default, and reviewed before variants are promoted."
