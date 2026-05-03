# Radar Research Sprint Backlog

## Execution Rules

This backlog is the operational companion to `docs/radar-research-spec.md`.

Every sprint follows the same loop:

1. Implement the sprint scope only.
2. Run the sprint test set.
3. If a test fails:
   - identify the exact failure cause
   - make the smallest targeted fix that resolves it
   - rerun the affected tests
   - rerun the full sprint test set
4. Commit the sprint only after the sprint test set is green.
5. Move immediately to the next sprint.

### Commit rule

No sprint is committed unless its required tests pass.

### Branch rule

All sprint work lands on the current integration branch:

- `integration/radar-reconcile`

### Naming rule

Use commit messages in this format:

- `Sprint 0: stabilize integration baseline`
- `Sprint 1: add Radar Research schema and models`
- `Sprint 2: add queued run infrastructure and APIs`
- `Sprint 3: add research graph core`
- `Sprint 4: add report persistence and retrieval`
- `Sprint 5: add Radar reports UI`
- `Sprint 6: add auditing, metrics, and evaluation harness`
- `Sprint 7: enable scheduled research runs and final polish`

## Sprint 0: Stabilize Integration Baseline

### Goal

Create a clean, tested checkpoint of the current integration branch so the Radar Research work can be delivered as real sprint commits instead of being mixed into unrelated uncommitted changes.

### Scope

- verify the current branch compiles and the existing focused suites pass
- fix any failing baseline tests that block forward work
- commit the existing integrated state as the baseline checkpoint

### Deliverables

- a baseline green backend suite for the current integrated branch
- a passing frontend production build
- a baseline checkpoint commit

### Required tests

- `pytest -q tests/test_ai_orchestrator.py tests/test_metrics.py tests/test_draft_writer.py tests/test_resume_tailor.py tests/test_opportunity_radar.py tests/test_auth_redirect_origins.py tests/test_notifications.py tests/test_extraction_reports.py tests/test_feedback_stats.py tests/test_duplicates.py`
- `npm run build` in `dashboardv2`

### Exit criteria

- all required tests pass
- baseline commit created

## Sprint 1: Add Radar Research Schema And Models

### Goal

Add the database and ORM structures required for research-mode Radar while keeping current internal Radar behavior intact.

### Scope

- create Alembic migrations `036` through `039` from the spec
- extend `ResearchProfile`
- extend `ResearchRun`
- add `ResearchRunStep`
- add `ResearchReport`
- add `ResearchReportSection`
- add `ResearchEvidenceItem`
- extend `ResearchFeedback`
- add `web_research` consent support
- add `radar_updates_enabled` notification preference support

### Deliverables

- migrations applied cleanly
- ORM models updated
- serialization helpers updated where needed

### Required tests

- `pytest -q tests/test_opportunity_radar.py tests/test_notifications.py`
- add new migration/model tests if needed

### Exit criteria

- migrations upgrade and downgrade cleanly in test flow
- current Radar tests still pass
- sprint commit created

## Sprint 2: Add Queued Run Infrastructure And APIs

### Goal

Move Radar runs out of the request cycle and add the API surface for queued runs, reports, and trace inspection.

### Scope

- add `backend/tasks/run_research_radar.py`
- register new Celery tasks in `backend/celery_app.py`
- add beat dispatcher for due research profiles
- convert `POST /api/research/profiles/{profile_id}/run` to queued execution
- add:
  - `GET /api/research/runs/{run_id}`
  - `GET /api/research/runs/{run_id}/steps`
  - `GET /api/research/runs/{run_id}/trace`
  - `GET /api/research/reports`
  - `GET /api/research/reports/{report_id}`
  - `GET /api/research/reports/{report_id}/diff`
  - `POST /api/research/reports/{report_id}/feedback`

### Deliverables

- queued run path works for the existing internal Radar mode
- trace and report endpoints exist even if report generation is not implemented yet

### Required tests

- existing Radar tests updated for `202 Accepted` enqueue behavior
- new API tests for queued run status and trace retrieval
- `pytest -q tests/test_opportunity_radar.py`

### Exit criteria

- internal Radar can be queued and completed through task execution
- sprint commit created

## Sprint 3: Add Research Graph Core

### Goal

Build the LangGraph-based research workflow and the storage helpers that audit every node.

### Scope

- create `backend/services/research_radar/`
- add:
  - `state.py`
  - `schemas.py`
  - `config.py`
  - `prompts.py`
  - `llm.py`
  - `graph.py`
  - `storage.py`
- implement nodes:
  - `context`
  - `normalize`
  - `plan`
  - `search`
  - `fetch`
  - `extract`
  - `dedupe`
  - `diff`
  - `report`
  - `verify`
  - `actions`
  - `persist`
  - `notify`
- add new AI task configs to `ai_orchestrator.py`
- regenerate `backend/PROMPT_REGISTRY.md`

### Deliverables

- graph compiles
- graph can execute a research-mode run end to end
- every node writes a `ResearchRunStep`

### Required tests

- unit tests for each node family
- graph happy-path integration test
- graph failure persistence test
- `pytest -q tests/test_ai_orchestrator.py tests/test_opportunity_radar.py`

### Exit criteria

- research-mode run produces a saved report in the database
- step audits are persisted
- sprint commit created

## Sprint 4: Add Report Persistence And Retrieval

### Goal

Make saved reports, sections, evidence, actions, and diffs first-class product artifacts.

### Scope

- wire graph persistence to:
  - `ResearchReport`
  - `ResearchReportSection`
  - `ResearchEvidenceItem`
  - `RecommendedAction`
- implement report diff generation
- implement report feedback persistence
- ensure alerts link into report context

### Deliverables

- report records are complete and queryable
- diffs work against the previous report
- report actions are persisted and status-updatable

### Required tests

- report retrieval tests
- report diff tests
- report feedback tests
- action linkage tests
- `pytest -q tests/test_opportunity_radar.py`

### Exit criteria

- reports can be retrieved by tracker and by report id
- diffs are persisted and rendered by API
- sprint commit created

## Sprint 5: Add Radar Reports UI

### Goal

Extend the current Radar UI to expose research trackers, report history, report detail, report diffing, and debugging surfaces.

### Scope

- add:
  - `RadarModeSwitch.tsx`
  - `ResearchReportList.tsx`
  - `ResearchReportDetail.tsx`
  - `ResearchReportDiff.tsx`
  - `ResearchRunTracePanel.tsx`
  - `ResearchTrackerForm.tsx`
- update `Radar.tsx`
- update `RadarProfileForm.tsx`
- update `types.ts`
- update `api.ts`
- update settings and consent surfaces for research-mode controls

### Deliverables

- users can create `internal`, `research`, and `hybrid` trackers
- users can inspect saved reports and diffs
- local-dev debugging view can inspect run steps

### Required tests

- `npm run build`
- frontend component tests if available
- browser-based Radar report smoke QA

### Exit criteria

- report UI is usable end to end
- sprint commit created

## Sprint 6: Add Auditing, Metrics, And Evaluation Harness

### Goal

Make the system diagnosable and measurable without reproducing failures manually.

### Scope

- extend `backend/metrics.py` for research metrics
- add AppTrail-native trace payloads
- add optional LangSmith instrumentation behind config
- add evaluation harness under `tests/evals/research_radar/`
- add curated fixtures for:
  - brief normalization
  - plan quality
  - evidence extraction
  - grounding
  - report usefulness

### Deliverables

- metrics exposed
- traces optionally emitted
- eval harness runnable locally

### Required tests

- metrics tests
- trace persistence tests
- eval harness smoke test
- `pytest -q tests/test_metrics.py tests/test_ai_orchestrator.py`

### Exit criteria

- broken runs are diagnosable through stored steps and metrics
- sprint commit created

## Sprint 7: Enable Scheduled Research Runs And Final Polish

### Goal

Turn the feature into a production-ready recurring workflow.

### Scope

- schedule due-profile dispatch
- set and advance `next_run_at`
- support `daily`, `weekly`, `biweekly`, `monthly`
- finish alert and notification mapping
- harden consent gating
- final UX polish and copy
- end-to-end live QA

### Deliverables

- scheduled research runs execute automatically
- alerts and report links land in the right UI state
- final acceptance pass completed

### Required tests

- dispatcher tests
- cadence tests
- alert and consent tests
- browser QA for:
  - tracker creation
  - manual run
  - report history
  - scheduled run visibility

### Exit criteria

- scheduled and manual report generation both work
- feature is merge-ready
- sprint commit created

## Autonomous Execution Notes

The implementation should proceed in sprint order with no manual handoff between sprints.

If a sprint exposes a missing prerequisite, resolve it inside the current sprint if it is small and local. If it changes the architecture, update `docs/radar-research-spec.md` and this backlog before continuing.

If a test fails:

- fix the actual root cause
- do not weaken assertions to force green
- rerun until green

If a sprint reveals that a later sprint should be split, add the extra sprint here and continue in order.
