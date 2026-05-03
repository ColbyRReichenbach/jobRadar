# Opportunity Radar — Ruthless Functionality & Logic Audit

Date: 2026-04-22
Scope: Opportunity Radar backend + frontend + AI layer integration quality.

## Executive summary

The Opportunity Radar MVP is now operational, but it was not production-grade in several critical areas.
This audit identified and prioritized gaps in run reliability, duplicate signal behavior, frontend interaction correctness,
and operational observability readiness.

## Findings by area

## 1) Backend run pipeline

### Gap 1.1 — Run failure state handling was fragile
- Previous behavior could leave ambiguous state when run logic raised exceptions.
- Production impact: poor operability/debugging and unreliable run status tracking.

### Fix implemented
- Added guarded run execution path with explicit `failed` status, `error_message`, and completion timestamp updates on exception.

### Remaining TODO
- Add structured error classes and retry policies (transient adapter/network vs permanent validation failures).

---

### Gap 1.2 — Signal duplication across repeated runs
- Previous behavior could regenerate identical signals from unchanged source items.
- Production impact: noisy feeds, duplicate actions, inflated analytics.

### Fix implemented
- Added duplicate-signal guard keyed by `(user_id, source_item_id, event_type)` before creating new `OpportunitySignal`.

### Fix implemented (follow-up)
- Added DB-level dedupe constraint migration for `opportunity_signals` uniqueness on `(user_id, source_item_id, event_type)`.

---

### Gap 1.3 — Action status update accepted arbitrary strings
- Previous behavior allowed unrestricted action status values.
- Production impact: invalid state transitions and bad downstream analytics.

### Fix implemented
- Constrained action status updates to strict literal enum: `open | accepted | dismissed | completed`.

### Remaining TODO
- Add state machine rules (e.g., no transition from `completed` back to `open` without explicit admin override).

### Fix implemented (follow-up)
- Added transition guards: invalid transitions now return `400` instead of silently mutating invalid states.

---

### Gap 1.4 — Source collection scope was too broad for company-tech source
- Previous behavior could ingest all tech profiles without user relevance filtering.
- Production impact: cross-user noise and weaker personalization.

### Fix implemented
- Tech source collection now prioritizes user-relevant company scope (applications / visit domains / selected companies).

### Remaining TODO
- Expand profile-aware filtering using role/domain keyword constraints and source-type toggles.

### Fix implemented (follow-up)
- Added `source_types`-aware collection so profiles can limit ingestion to enabled internal adapters.

## 2) Frontend Radar UX and logic

### Gap 2.1 — Selected brief logic was incorrect
- Previous behavior selected brief using a truthy check, not a signal association.
- Production impact: user could see unrelated brief content.

### Fix implemented
- Added selected-signal state and deterministic brief matching fallback.

---

### Gap 2.2 — Placeholder components shipped in production path
- Several Radar components were no-op placeholders (`return null`).
- Production impact: architecture drift and low maintainability.

### Fix implemented
- Implemented and wired real components:
  - `RadarProfileForm`
  - `SignalFeed`
  - `SignalCard`
  - `OpportunityScoreBreakdown`
  - `RecommendedActions`
  - `BriefPanel`
  - `ResearchRunHistory`

### Remaining TODO
- Add loading/error states per component and skeletons.
- Add keyboard navigation and accessibility semantics for cards/actions.

## 3) Testing quality

### Gap 3.1 — Missing coverage for key correctness edge cases
- No tests for invalid action status and duplicate signal suppression.

### Fix implemented
- Added tests for:
  - invalid action status rejection (`422`)
  - repeated-run duplicate signal prevention

### Remaining TODO
- Add tests for failed run state and `error_message` persistence.
- Add tests for profile-selected company filtering behavior.

## 4) AI architecture and production readiness

### Current status
- Core deterministic MVP pipeline is working.
- AI governance/observability still requires implementation work from architecture doc.

### High-priority TODO (not yet implemented)
1. LLM invocation telemetry tables + instrumentation wrapper.
2. Prompt version registry and experiment tracking.
3. Admin analytics endpoints (quality/cost/latency/drift).
4. Offline + online eval harness with release gating.
5. Run-orchestrator checkpoints for sensitive action-generation steps.

## Production-grade TODO list

## P0 (next sprint)
1. Add retry classification and backoff policy for failed runs.
2. Add frontend error boundaries/toasts for run/action failures.
3. Add pagination + filtering controls on Radar feed/actions.
4. Add DB migration smoke test in CI for new Radar constraints.

## P1
1. Add prompt/model invocation tracking schema and metrics API.
2. Add weekly eval report job and dashboards.
3. Add action lifecycle state machine rules.

## P2
1. Add durable orchestration/checkpointing for long-running runs.
2. Add score calibration monitoring and drift alarms.

## Validation runbook

- `pytest -q tests/test_opportunity_radar.py`
- `pytest -q tests/backend`
- `cd dashboardv2 && npm run build`

All checks are currently green after the fixes in this pass.
