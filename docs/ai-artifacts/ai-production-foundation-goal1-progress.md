# AI Production Foundation Goal 1 Progress

Date: 2026-05-11

## Current-State Verification

- Gmail classification is produced by `backend/services/email_classifier.py` and the hybrid lane under `backend/services/gmail_intelligence/`. `EmailEvent` persistence happens in Gmail sync paths in `backend/main.py` and `backend/tasks/poll_gmail.py`; before this slice, route/subtype/decision metadata was returned but not persisted on the primary event.
- Duplicate checks were endpoint-specific: job URL/company-role checks in `backend/main.py`, contact email/name checks in `backend/main.py`, interview suggestion duplicate checks during accept, Radar action/recommendation creation in `backend/services/research_radar/nodes/persist.py`, and alert volume/admin dedupe in `backend/services/alerts.py`.
- `Alert` and `RecommendedAction` previously had no shared action-candidate linkage. Alerts had only type/title/body/action URL/read fields; recommended actions were Radar-oriented product rows.
- Migrations use Alembic revision files under `backend/alembic/versions/`. Tests use `pytest`/`pytest-asyncio` with in-memory SQLite via `Base.metadata.create_all`.

Schema decision: additive changes were safe for this run. The migration only adds new tables and nullable metadata columns, plus indexes/FKs; it does not rewrite or delete existing rows.

Plan used:

1. Add additive trace/candidate schema and services first.
2. Wire only low-risk paths: Gmail trace persistence, optional alert dedupe keys, and Radar recommendation candidate linkage.
3. Keep existing endpoint behavior intact except deterministic duplicate suppression where a dedupe key is explicitly supplied.
4. Add focused tests, generate the runtime-count artifact, then run the goal-specified regression subset.

## Implemented

- Added `ActionCandidate` and `EmailClassificationTrace` models plus Alembic migration `051_action_candidates_traces`.
- Added `backend/services/action_candidates.py` for stable action dedupe keys and deterministic candidate upsert.
- Added `backend/services/dedupe_gate.py` covering `add_job_to_pipeline`, `add_network_contact`, `schedule_interview`, and `review_radar_opportunity`.
- Added Gmail classifier trace persistence for stored, filtered, and quarantined classified messages, including classifier mode, route/subtype confidence, decision path, threshold version, matched features, preflight status, and source URL count.
- Added nullable alert/recommendation dedupe metadata. User alerts can suppress duplicate dedupe keys; Gmail, calendar, and Radar report alerts now provide stable keys. Radar recommended actions now link to action candidates and suppress exact duplicate recommendation keys.
- Added `backend/services/runtime_count_artifacts.py` and `scripts/collect_runtime_counts_artifact.py`.
- Generated `docs/ai-artifacts/generated/local-runtime-counts.json` from `apptrail-local.db`; missing tables are `null`, existing empty tables are `0`.

## Changed Files

- `backend/models.py`
- `backend/alembic/versions/051_action_candidates_traces.py`
- `backend/services/action_candidates.py`
- `backend/services/dedupe_gate.py`
- `backend/services/email_classification_traces.py`
- `backend/services/runtime_count_artifacts.py`
- `backend/services/email_classifier.py`
- `backend/services/alerts.py`
- `backend/services/research_radar/nodes/notify.py`
- `backend/services/research_radar/nodes/persist.py`
- `backend/main.py` (trace/alert-dedupe wiring; unrelated pre-existing env/OAuth edits were left intact)
- `backend/tasks/poll_gmail.py`
- `scripts/collect_runtime_counts_artifact.py`
- `tests/conftest.py`
- `tests/test_alerts.py`
- `tests/test_action_foundation.py`
- `tests/test_email_classification_traces.py`
- `tests/test_runtime_count_artifacts.py`
- `docs/ai-artifacts/generated/local-runtime-counts.json`

## Validation

- `pytest -q tests/test_action_foundation.py tests/test_email_classification_traces.py tests/test_runtime_count_artifacts.py tests/test_alerts.py` -> 15 passed.
- `python3 scripts/collect_runtime_counts_artifact.py --database-url sqlite+aiosqlite:///apptrail-local.db --database-label sqlite:apptrail-local.db --output docs/ai-artifacts/generated/local-runtime-counts.json` -> wrote the local runtime count artifact.
- `pytest -q tests/test_duplicates.py tests/test_alerts.py tests/test_email_suggestions.py tests/test_gmail_intelligence.py tests/test_gmail_sync.py tests/test_ai_artifacts.py tests/test_ai_promotion_reports.py tests/test_action_foundation.py tests/test_email_classification_traces.py tests/test_runtime_count_artifacts.py` -> 55 passed, 1 Python-version warning from `google.api_core`.
- `pytest -q tests/test_notifications.py tests/test_research_radar_graph.py tests/test_opportunity_radar.py tests/test_source_discovery.py` -> failed because local `.env` has `RADAR_ENABLED=false` and `RADAR_RESEARCH_ENABLED=false`, so `/api/research/*` returned 404 before the changed paths ran.
- `env RADAR_ENABLED=true RADAR_RESEARCH_ENABLED=true pytest -q tests/test_notifications.py tests/test_research_radar_graph.py tests/test_opportunity_radar.py tests/test_source_discovery.py` -> 51 passed, 1 dev Redis warning.
- `pytest -q tests/test_copilot_schema.py` -> 1 passed.
- `git diff --check -- <changed Goal 1 files>` -> no whitespace errors.

## Follow-Up Review Fixes

After review, four production-readiness issues were fixed:

- `EmailClassificationTrace.user_id` now cascades on user deletion and is non-nullable, so skipped/quarantined Gmail trace rows cannot survive as userless telemetry.
- Email classification traces now upsert by `user_id + gmail_message_id + classifier_mode`, preventing repeated skipped/quarantined Gmail messages from generating duplicate trace rows on later syncs.
- `create_or_update_action_candidate` now preserves terminal/user-decision statuses such as `accepted`, `dismissed`, `expired`, `failed_validation`, and `linked_existing` unless the caller explicitly allows terminal overwrite.
- Alert dedupe now has a unique database index on `user_id + dedupe_key + suppression_status`, and keyed alert creation uses a nested transaction so concurrent duplicate inserts return `None` instead of creating duplicate active alerts.
- Calendar interview alert dedupe keys now include interview status and scheduled time, so exact replays suppress while real calendar updates still notify the user.

Follow-up validation:

- `pytest -q tests/test_action_foundation.py tests/test_email_classification_traces.py tests/test_runtime_count_artifacts.py tests/test_duplicates.py tests/test_email_suggestions.py tests/test_gmail_intelligence.py tests/test_gmail_sync.py tests/test_ai_artifacts.py tests/test_ai_promotion_reports.py tests/test_interviews.py tests/test_alerts.py` -> 72 passed, 1 Python-version warning from `google.api_core`.
- `env RADAR_ENABLED=true RADAR_RESEARCH_ENABLED=true pytest -q tests/test_notifications.py tests/test_research_radar_graph.py tests/test_opportunity_radar.py tests/test_source_discovery.py` -> 51 passed, 1 dev Redis warning.
- `pytest -q tests/test_copilot_schema.py` -> 1 passed.
- `python3 -m py_compile` on changed model/service/migration files -> passed.
- `git diff --check -- <review-fix files>` -> no whitespace errors.

## Phase 1 Adoption Progress

Date: 2026-05-12

Implemented after the Goal 1 foundation pass:

- Refactored `/api/jobs`, `/api/jobs/duplicates/check`, and `/api/contacts/duplicates/check` to call the shared `DedupeGate` for duplicate decisions while preserving the existing response shapes and messages.
- Refactored Gmail-derived application, network-contact, and interview acceptance paths to evaluate shared duplicate decisions and persist `ActionCandidate` rows with accepted or linked-existing terminal status.
- Refactored `POST /api/interviews/from-email/{email_id}` to use the shared interview duplicate gate and candidate service.
- Linked Gmail `network_contact` alerts to proposed `ActionCandidate` rows, including duplicate reason/matches metadata, and suppress hard duplicate contact alerts when the shared gate finds an existing contact.
- Updated Gmail sync reset to delete email-event action candidates along with Gmail-synced email rows, alerts, source links, and search documents.
- Refactored Google Calendar interview sync to evaluate `schedule_interview` duplicate decisions, link same-time/same-interviewer calendar events to existing interviews, and create calendar-event action candidates.
- Added a calendar sync guard for soft interview duplicates: same-application/same-time events now write a `pending_review` action candidate and do not create or mutate an interview until reviewed.
- Linked calendar interview alerts to the calendar sync action candidate and carried duplicate metadata through the alert row.
- Preserved soft-duplicate policy metadata on accepted Gmail/network/interview candidates instead of overwriting every accepted non-link path as a plain proposal.
- Left Radar recommendation persistence on the existing Goal 1 shared `ActionCandidate`/`DedupeGate` path; Radar recommendation rows remain linked to `action_candidate_id`.

Phase 1 adoption changed files:

- `backend/main.py`
- `backend/services/calendar_sync.py`
- `backend/services/dedupe_gate.py`
- `tests/test_email_suggestions.py`
- `tests/test_gmail_sync.py`
- `tests/test_interviews.py`
- `tests/test_network.py`
- `docs/ai-artifacts/ai-production-foundation-goal1-progress.md`

Phase 1 validation:

- `pytest -q tests/test_email_suggestions.py tests/test_network.py tests/test_interviews.py tests/test_gmail_sync.py tests/test_duplicates.py tests/test_action_foundation.py tests/test_alerts.py` -> 68 passed, 1 Python-version warning from `google.api_core`.
- `RADAR_ENABLED=true RADAR_RESEARCH_ENABLED=true pytest -q tests/test_notifications.py tests/test_research_radar_graph.py tests/test_opportunity_radar.py tests/test_source_discovery.py tests/test_copilot_schema.py` -> 52 passed, 1 dev Redis warning.
- `git diff --check` -> no whitespace errors.
- `python3 -m compileall backend/main.py backend/services/calendar_sync.py backend/services/dedupe_gate.py` -> passed.

## Remaining Limitations

- Manual user-created jobs, contacts, and interviews remain normal CRUD rows. Job create and duplicate-check endpoints now use shared duplicate decisions, but shared candidate tracking is applied to AI/Gmail/calendar/Radar action-producing flows, not every direct user edit.
- `Alert.action_candidate_id` remains nullable. Gmail network-contact alerts and calendar interview alerts now link to candidates; ordinary email-update alerts and Radar report-ready alerts still use stable dedupe keys without a single candidate link.
- Calendar sync candidates use the target fingerprint from the schedule-interview decision. If the same calendar event materially changes time/interviewer/application, it can create a new candidate for the new target state while preserving the old terminal candidate row.
- The generated runtime-count artifact is a local SQLite snapshot, not production evidence. It shows the new tables as missing until migration `051` is applied to that database.
- No production migration was run during these local passes. Apply Alembic migration `051_action_candidates_traces` before relying on the new tables/columns outside local tests.
