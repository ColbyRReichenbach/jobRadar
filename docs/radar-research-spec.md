# Radar Research Implementation Spec

## Purpose

This document defines the full implementation for the next version of Radar in AppTrail. It is written as a build specification, not a product memo. An engineer should be able to use this document to implement the feature without needing unwritten context.

The goal is to turn Radar from an internal signal surface into a dual-track system:

- `Internal Radar`: the current deterministic pipeline based on AppTrail data
- `Research Radar`: scheduled and on-demand external research that produces saved reports, evidence, and actions

This spec is based on:

- the current AppTrail codebase and data model
- the current Radar implementation
- current workflow and agent guidance from LangGraph and LangSmith
- current model and evaluation guidance from OpenAI
- open-model evaluation considerations from Hugging Face model cards

References are listed at the end of this document.

## Product Decision

### What AppTrail should build

AppTrail should not replace the current Radar implementation with a single autonomous agent.

AppTrail should build a bounded research workflow with graph orchestration, typed state, explicit persistence, and saved reports.

### Why this is the right choice for this product

This codebase already has four important traits:

- FastAPI + SQLAlchemy for a typed backend
- Celery + beat for recurring and retryable work
- PostgreSQL as the canonical product store
- an existing AI orchestration layer in `backend/services/ai_orchestrator.py`

That makes AppTrail a better fit for a checkpointed workflow than for a loose chat-agent loop.

The current Radar stack already has useful persistence primitives:

- `ResearchProfile`
- `ResearchRun`
- `ResearchSourceItem`
- `OpportunitySignal`
- `OpportunityScore`
- `OpportunityBrief`
- `RecommendedAction`
- `ResearchFeedback`

Those should not be thrown away. They should be extended.

The correct product architecture is:

- keep the current internal Radar path as a deterministic source adapter
- add a new research-report path for external web research
- orchestrate the research path with LangGraph
- keep first-class audit records in AppTrail's own database
- optionally send traces to LangSmith when configured

## Product Scope

### In scope

- user-configured Radar research trackers
- scheduled runs with daily, weekly, biweekly, and monthly cadence
- manual runs
- profile-aware research brief generation
- bounded web research using search + fetch
- saved dated reports
- saved evidence and citations
- report diffing against the previous report
- recommended actions derived from the report
- per-step audit records
- per-step failure localization
- user feedback on reports
- internal debugging support for failed runs

### Out of scope for the first implementation

- outbound autonomous actions such as sending email, applying, or editing applications automatically
- authenticated crawling of LinkedIn, Crunchbase, or other protected sites
- a general-purpose browser agent
- local open-model serving in production
- reinforcement loops that rewrite prompts automatically

## Current State In This Repo

### Existing Radar behavior

The current Radar implementation lives in two places:

- API and persistence orchestration in `backend/main.py`
- deterministic helper modules in `backend/services/opportunity_radar/`

Today, a Radar run does this:

1. Loads a `ResearchProfile`
2. Collects internal source candidates from:
   - applications
   - career-page visits
   - company tech profiles
3. Stores source items
4. Extracts rule-based signals
5. Scores those signals deterministically
6. Generates template-based briefs
7. Generates rule-based actions
8. Creates in-app alerts for high-score signals

This behavior should remain intact as the `internal` mode.

### Existing reusable product context

The research implementation must reuse existing AppTrail context instead of rebuilding it:

- `UserProfile` for resume text, skills, tools, experience, certifications
- `/api/profile/preferences` data for preferred locations, remote type, salary targets, and role interests
- `knowledge_graph.py` for company context assembly
- `match_scorer.py` for job-to-profile fit signals
- `NotificationPreference` and `Alert` for delivery and in-app notifications
- `ai_orchestrator.py` for prompt registry, model config, retries, and AI task telemetry

## Final Product Behavior

### Radar modes

Add a mode field to each tracker:

- `internal`
- `research`
- `hybrid`

Mode behavior:

- `internal`: current Radar only
- `research`: report-only research run
- `hybrid`: run internal Radar and research Radar in the same scheduled job

### User-facing Radar structure

Radar becomes a two-tab workspace:

1. `Signals`
   - current signal feed
   - current score breakdown
   - current actions
   - current brief

2. `Reports`
   - tracker list
   - saved reports by date
   - report detail
   - report diff against the previous report
   - report evidence appendix
   - report-derived actions

### Tracker form fields

Keep the existing fields and add:

- `mode`
- `Cadence` UI label backed by the existing `frequency` field with allowed values `manual | daily | weekly | biweekly | monthly`
- `depth`: `quick | standard | deep`
- `use_profile_context`: boolean
- `target_locations`: string[]
- `remote_types`: string[]
- `seniority_levels`: string[]
- `research_source_scopes`: string[]
- `include_public_web_research`: boolean
- `max_sources_per_run`: integer
- `max_search_queries`: integer
- `report_prompt_notes`: text

Keep `source_types` for internal adapters only:

- `application`
- `company_visit`
- `company_tech`

Use `research_source_scopes` for external research adapters.

### Report contents

Each completed research run must produce one saved report with these sections:

- `Executive summary`
- `What changed since the last run`
- `Best-fit opportunities`
- `Company signals`
- `Why these fit the user`
- `Recommended actions`
- `Evidence appendix`

Each report must include:

- `report_date`
- `tracker_id`
- `run_id`
- `confidence`
- `finding_count`
- `source_count`
- `new_findings_count`
- `changed_findings_count`

## Architecture Decision

### Orchestration layer

Use LangGraph for the research-report path.

Do not use LangChain chains as the primary runtime abstraction.

Do not implement this as one giant prompt.

Do not implement prompt-generation agents that hand off prose to other agents unless the handoff is backed by a typed schema.

### Execution model

Use a checkpointed graph with typed state.

Use LangGraph only for the research-report path.

Do not port the current deterministic internal Radar path into LangGraph in the first implementation. Instead, wrap it as a reusable internal source adapter for `hybrid` mode.

### Persistence model

Persist three levels of data:

1. Product artifacts in AppTrail tables
2. Step-level audit rows in AppTrail tables
3. Optional external traces in LangSmith

AppTrail's own database is the source of truth. LangSmith is optional observability, not required persistence.

## Model Strategy

### Production default

For this repo, the first production implementation should stay OpenAI-only.

Reason:

- AppTrail is already standardized on OpenAI in `ai_orchestrator.py`
- there is no current inference infrastructure for local or self-hosted models
- the feature needs reliable structured outputs before it needs provider diversity

### Model routing

Use the following routing table:

- `research_brief_normalizer`
  - model: `gpt-5.1`
  - reason: structured planning and schema fidelity
- `research_planner`
  - model: `gpt-5.1`
  - reason: plan quality matters more than raw speed here
- `research_search_worker`
  - model: `gpt-4o-search-preview`
  - reason: web-grounded retrieval with acceptable cost for recurring runs
- `research_evidence_extractor`
  - model: `gpt-5.1`
  - reason: strict JSON extraction from fetched documents
- `research_report_writer`
  - model: `gpt-5.4`
  - reason: strongest report synthesis in the existing product stack
- `research_report_verifier`
  - model: `gpt-5.1`
  - reason: cheaper than using `gpt-5.4` twice while still strong enough for critique

### Optional later path

Support an offline evaluation lane for:

- `gpt-oss-20b`
- `Qwen3-235B-A22B-Instruct-2507`

Do not use them in v1 production. Evaluate them only after the OpenAI baseline is working and measured.

## Graph Design

### Graph state

Create `backend/services/research_radar/state.py` with a single typed state object.

Required state keys:

- `run_id`
- `profile_id`
- `user_id`
- `mode`
- `trigger`
- `tracker`
- `user_context`
- `normalized_brief`
- `research_plan`
- `search_tasks`
- `source_items`
- `evidence_items`
- `diff_summary`
- `report_sections`
- `report_actions`
- `verification_result`
- `final_report`
- `step_metrics`
- `errors`

### Node order

Implement the graph in this order:

1. `load_tracker_context`
2. `normalize_research_brief`
3. `validate_brief`
4. `plan_research_tasks`
5. `run_search_tasks` using bounded worker fan-out
6. `fetch_documents`
7. `extract_evidence`
8. `dedupe_and_rank_evidence`
9. `build_report_diff`
10. `write_report`
11. `derive_report_actions`
12. `verify_report`
13. `persist_report`
14. `emit_alerts`
15. `schedule_next_run`

### Node details

#### 1. `load_tracker_context`

Inputs:

- `ResearchProfile`
- current user profile
- current profile preferences
- role interests
- recent applications
- company visits
- saved company context where available
- previous report for this tracker

Outputs:

- `tracker`
- `user_context`

Rules:

- do not call an LLM here
- normalize arrays and strings
- compute derived fields such as salary band and role-interest labels

#### 2. `normalize_research_brief`

Purpose:

- convert tracker config + user context into a strict research brief JSON

Output schema:

- `search_objective`
- `ideal_role_titles`
- `target_domains`
- `target_companies`
- `target_locations`
- `remote_preferences`
- `seniority`
- `must_have_signals`
- `avoid_signals`
- `fit_summary`
- `search_constraints`

Rules:

- use structured output only
- fail the step if schema validation fails twice
- save both raw and validated outputs to `research_run_steps`

#### 3. `validate_brief`

Purpose:

- deterministic sanity checks

Checks:

- at least one search target exists
- empty arrays are replaced with safe defaults from profile/preferences
- role titles and domains are deduped
- max fan-out thresholds are enforced

#### 4. `plan_research_tasks`

Purpose:

- convert the normalized brief into bounded research tasks

Each task must have:

- `task_id`
- `task_type`
- `query`
- `company_hint`
- `role_hint`
- `expected_signal_type`
- `max_results`
- `priority`

Task types:

- `role_openings`
- `company_hiring_signal`
- `team_growth_signal`
- `tech_stack_signal`
- `company_strategy_signal`

Hard limits:

- `quick`: max 4 search tasks
- `standard`: max 8 search tasks
- `deep`: max 12 search tasks

#### 5. `run_search_tasks`

Purpose:

- run search tasks in parallel

Implementation:

- one bounded LangGraph worker per search task
- no recursive agents
- no worker may generate new workers

Each worker may do:

- one search request
- one reranked search request if the first result set is poor

Each worker must return structured candidates:

- `url`
- `title`
- `snippet`
- `source_type`
- `domain`
- `published_at`
- `why_selected`

#### 6. `fetch_documents`

Purpose:

- fetch the top selected documents and store them as `ResearchSourceItem`

Rules:

- cap fetched documents per run by tracker limit
- normalize and hash content
- keep raw HTML or text out of step tables
- store raw payload in `ResearchSourceItem.raw_text` or `raw_json`

Allowed source classes in v1:

- company career pages
- company blog or newsroom
- press release pages
- public job board pages
- public engineering blog pages
- public GitHub organization pages if directly relevant

Do not include:

- authenticated sources
- LinkedIn scraping
- Reddit
- rate-limited sources without an approved adapter

#### 7. `extract_evidence`

Purpose:

- turn fetched documents into typed evidence records

Output schema per evidence item:

- `evidence_type`
- `title`
- `claim`
- `snippet`
- `url`
- `domain`
- `company_name`
- `role_title`
- `published_at`
- `confidence`
- `relevance_score`
- `novelty_score`
- `supports_objective`

Rules:

- use structured output
- every evidence item must cite one `ResearchSourceItem`
- no evidence item may exist without a source URL or internal source reference

#### 8. `dedupe_and_rank_evidence`

Purpose:

- remove duplicate evidence
- score evidence quality
- suppress stale results

Deterministic ranking inputs:

- source recency
- domain trust class
- explicit company/role match
- evidence novelty versus previous report
- repeated confirmation across sources

#### 9. `build_report_diff`

Purpose:

- compare current evidence to the last saved report for this tracker

Output:

- `new_findings`
- `changed_findings`
- `dropped_findings`
- `unchanged_findings`
- `diff_summary`

Matching key:

- normalized `company_name + role_title + evidence_type + canonical_url`

#### 10. `write_report`

Purpose:

- synthesize report sections from evidence and diff data

Rules:

- the writer only sees validated evidence, not raw fetched pages
- every claim in the report must map back to at least one evidence id
- report output is markdown plus a typed structured payload

#### 11. `derive_report_actions`

Purpose:

- generate product actions from the report

Action types in v1:

- `review_role`
- `save_job`
- `research_company`
- `find_contact`
- `draft_outreach`
- `build_project`

Actions must be tied to:

- `report_id`
- `source_evidence_ids`
- `company_id` when possible

#### 12. `verify_report`

Purpose:

- check that the report is grounded and useful

Verification checks:

- unsupported claim count
- section completeness
- tracker-fit score
- citation coverage
- hallucination risk

Failure rule:

- if unsupported claim count > 0 in `Executive summary` or `Recommended actions`, the run is marked `needs_review` and the report is not surfaced as ready

#### 13. `persist_report`

Purpose:

- save the report, sections, evidence, and actions

#### 14. `emit_alerts`

Purpose:

- create an alert when a report is ready or a high-priority finding appears

Alert types to add:

- `research_report_ready`
- `research_run_failed`

#### 15. `schedule_next_run`

Purpose:

- compute the next `next_run_at` for the tracker

Cadence rules:

- daily: `+1 day`
- weekly: `+7 days`
- biweekly: `+14 days`
- monthly: `+1 month`

## Data Model Changes

### Extend `ResearchProfile`

Do not add a second scheduling field.

Keep the existing `frequency` column and expand its allowed values to:

- `manual`
- `daily`
- `weekly`
- `biweekly`
- `monthly`

Add columns:

- `mode` text, default `internal`
- `depth` text, default `standard`
- `target_locations` JSON nullable
- `remote_types` JSON nullable
- `seniority_levels` JSON nullable
- `research_source_scopes` JSON nullable
- `use_profile_context` boolean default `true`
- `include_public_web_research` boolean default `false`
- `report_prompt_notes` text nullable
- `max_search_queries` integer default `8`
- `max_sources_per_run` integer default `20`
- `next_run_at` timestamp nullable
- `last_successful_run_at` timestamp nullable

### Extend `ResearchRun`

Add columns:

- `run_type` text default `manual`
- `mode` text nullable
- `trigger_reason` text nullable
- `orchestrator_version` text nullable
- `graph_thread_id` text nullable
- `current_step` text nullable
- `report_id` UUID nullable
- `tokens_in` integer nullable
- `tokens_out` integer nullable
- `llm_call_count` integer nullable
- `status_detail` JSON nullable

### Migration filenames

Create migrations in this order:

- `036_expand_research_profiles_for_research_mode.py`
- `037_add_research_reports_and_run_steps.py`
- `038_add_research_evidence_items.py`
- `039_add_web_research_consent_and_radar_notification_pref.py`

### Add `ResearchRunStep`

Create table `research_run_steps`:

- `id`
- `run_id`
- `user_id`
- `profile_id`
- `step_name`
- `step_order`
- `status`
- `model_name`
- `prompt_version`
- `tool_name`
- `input_json`
- `output_json`
- `error_message`
- `tokens_in`
- `tokens_out`
- `cost_estimate_cents`
- `started_at`
- `completed_at`
- `created_at`

Use this as the primary AppTrail audit table for node execution.

### Add `ResearchReport`

Create table `research_reports`:

- `id`
- `user_id`
- `profile_id`
- `run_id`
- `report_date`
- `title`
- `summary_markdown`
- `structured_json`
- `diff_summary`
- `status`
- `overall_confidence`
- `finding_count`
- `source_count`
- `new_findings_count`
- `changed_findings_count`
- `created_at`

### Add `ResearchReportSection`

Create table `research_report_sections`:

- `id`
- `report_id`
- `section_key`
- `title`
- `display_order`
- `markdown`
- `structured_json`

### Add `ResearchEvidenceItem`

Create table `research_evidence_items`:

- `id`
- `run_id`
- `report_id`
- `user_id`
- `profile_id`
- `source_item_id`
- `evidence_type`
- `title`
- `claim`
- `snippet`
- `url`
- `domain`
- `company_name`
- `role_title`
- `published_at`
- `confidence`
- `relevance_score`
- `novelty_score`
- `structured_json`
- `created_at`

### Extend `ResearchFeedback`

Add columns:

- `report_id` UUID nullable
- `run_step_id` UUID nullable
- `feedback_scope` text default `signal`

Valid values:

- `signal`
- `report`
- `step`

### Extend consent and notification models

Add consent type:

- `web_research`

Add notification preference field:

- `radar_updates_enabled` boolean default `true`

Map alert types:

- `opportunity_signal` -> `radar_updates_enabled`
- `research_report_ready` -> `radar_updates_enabled`
- `research_run_failed` -> `radar_updates_enabled`

## API Contract

### Existing endpoints to keep

- `GET /api/research/profiles`
- `POST /api/research/profiles`
- `PATCH /api/research/profiles/{profile_id}`
- `DELETE /api/research/profiles/{profile_id}`

### Change existing run endpoint

`POST /api/research/profiles/{profile_id}/run`

New behavior:

- do not execute the run inline
- enqueue a Celery task
- return `202 Accepted`

Response:

- `run_id`
- `status`
- `queued_at`

### New endpoints

- `GET /api/research/runs/{run_id}`
- `GET /api/research/runs/{run_id}/steps`
- `GET /api/research/runs/{run_id}/trace`
- `GET /api/research/reports?profile_id=...`
- `GET /api/research/reports/{report_id}`
- `GET /api/research/reports/{report_id}/diff`
- `POST /api/research/reports/{report_id}/feedback`
- `POST /api/research/reports/{report_id}/actions/{action_id}/accept`

### Example tracker payload

`POST /api/research/profiles`

```json
{
  "name": "Healthcare AI staff roles",
  "objective": "Find high-fit backend, platform, and applied AI roles at healthcare or health-infrastructure companies.",
  "mode": "hybrid",
  "selected_domains": ["healthcare_ai", "health_infra"],
  "selected_roles": ["Staff Backend Engineer", "Platform Engineer", "Applied AI Engineer"],
  "selected_companies": ["Abridge", "Commure", "Neko Health"],
  "keywords": ["llm infrastructure", "clinical workflow", "platform"],
  "excluded_keywords": ["intern", "contract", "onsite only"],
  "source_types": ["application", "company_visit", "company_tech"],
  "frequency": "weekly",
  "depth": "standard",
  "notification_mode": "in_app",
  "minimum_score": 72,
  "use_profile_context": true,
  "include_public_web_research": true,
  "target_locations": ["New York", "Remote", "San Francisco"],
  "remote_types": ["remote", "hybrid"],
  "seniority_levels": ["senior", "staff"],
  "research_source_scopes": ["company_careers", "company_blog", "press", "job_board"],
  "max_search_queries": 8,
  "max_sources_per_run": 20,
  "report_prompt_notes": "Bias toward engineering roles with clear technical ownership and public evidence of hiring."
}
```

### Example run enqueue response

`POST /api/research/profiles/{profile_id}/run`

```json
{
  "run_id": "d1d7f0c7-7bd7-4b64-a75a-0d58bfa8e7e5",
  "status": "queued",
  "queued_at": "2026-04-22T18:30:12.000000+00:00"
}
```

### Example report response

`GET /api/research/reports/{report_id}`

```json
{
  "id": "5d63f0e8-a0d6-4a4f-9d53-07c5f4f0d0a1",
  "profile_id": "9bc89d77-2a43-4f0d-a0dd-b740a3d7cfd1",
  "run_id": "d1d7f0c7-7bd7-4b64-a75a-0d58bfa8e7e5",
  "report_date": "2026-04-22",
  "title": "Weekly research report: Healthcare AI staff roles",
  "status": "ready",
  "overall_confidence": 0.86,
  "finding_count": 9,
  "source_count": 14,
  "new_findings_count": 5,
  "changed_findings_count": 2,
  "diff_summary": "Two previously watched companies posted new platform roles. One company signal cooled off.",
  "sections": [
    {
      "section_key": "executive_summary",
      "title": "Executive summary",
      "markdown": "..."
    },
    {
      "section_key": "best_fit_opportunities",
      "title": "Best-fit opportunities",
      "markdown": "..."
    }
  ],
  "evidence": [
    {
      "id": "9f876ef4-4251-4123-9741-b56141680c95",
      "evidence_type": "role_opening",
      "title": "Staff Platform Engineer",
      "claim": "Company X opened a new platform role aligned with the tracker.",
      "url": "https://company.example/jobs/123",
      "domain": "company.example",
      "confidence": 0.92,
      "relevance_score": 0.88,
      "novelty_score": 0.71
    }
  ],
  "actions": [
    {
      "id": "4ebfbc8f-bd5d-4308-a750-4e9f3f805ce1",
      "action_type": "review_role",
      "title": "Review Staff Platform Engineer role",
      "status": "open"
    }
  ]
}
```

### Trace endpoint shape

`GET /api/research/runs/{run_id}/trace` returns:

- `run`
- `steps`
- `langgraph_thread_id`
- `report`
- `errors`

This endpoint exists for product debugging and internal QA. It is not a marketing feature.

## Backend File Plan

### New package

Create `backend/services/research_radar/` with:

- `__init__.py`
- `state.py`
- `schemas.py`
- `config.py`
- `prompts.py`
- `llm.py`
- `graph.py`
- `storage.py`
- `nodes/context.py`
- `nodes/normalize.py`
- `nodes/plan.py`
- `nodes/search.py`
- `nodes/fetch.py`
- `nodes/extract.py`
- `nodes/dedupe.py`
- `nodes/diff.py`
- `nodes/report.py`
- `nodes/verify.py`
- `nodes/actions.py`
- `nodes/persist.py`
- `nodes/notify.py`

### Existing files to modify

- `backend/models.py`
- `backend/main.py`
- `backend/celery_app.py`
- `backend/services/ai_orchestrator.py`
- `backend/services/notification_preferences.py`
- `backend/tasks/__init__.py`

### New task module

Create `backend/tasks/run_research_radar.py` with two Celery tasks:

- `dispatch_due_research_profiles`
- `run_research_profile_task`

Beat schedule additions:

- `dispatch-due-research-profiles-every-30-min`

Behavior:

- the dispatcher finds active profiles with `next_run_at <= now`
- it enqueues `run_research_profile_task(profile_id, trigger="scheduled")`

## Frontend File Plan

### Existing files to modify

- `dashboardv2/src/components/Radar.tsx`
- `dashboardv2/src/components/RadarProfileForm.tsx`
- `dashboardv2/src/lib/api.ts`
- `dashboardv2/src/types.ts`
- `dashboardv2/src/components/Settings.tsx`
- `dashboardv2/src/components/ConsentModal.tsx`

### New components

- `dashboardv2/src/components/RadarModeSwitch.tsx`
- `dashboardv2/src/components/ResearchReportList.tsx`
- `dashboardv2/src/components/ResearchReportDetail.tsx`
- `dashboardv2/src/components/ResearchReportDiff.tsx`
- `dashboardv2/src/components/ResearchRunTracePanel.tsx`
- `dashboardv2/src/components/ResearchTrackerForm.tsx`

### Frontend behavior

- keep the current Signals workspace intact
- add a Reports workspace beside it
- show report history under the selected tracker
- show run status badges: `queued`, `running`, `succeeded`, `needs_review`, `failed`
- show a developer-only trace drawer in local development

## AI Task Registry Changes

Add the following task configs to `ai_orchestrator.py`:

- `research_brief_normalizer`
- `research_planner`
- `research_evidence_extractor`
- `research_report_writer`
- `research_report_verifier`

These must follow the same conventions already used in AppTrail:

- named task configs
- versioned prompts
- model selection in code
- generated prompt registry documentation
- fallback tracking
- task metrics

## Auditing And Observability

### Required AppTrail-native audit data

Every run must save:

- tracker snapshot at run start
- normalized brief
- plan output
- search task list
- fetched source references
- extracted evidence
- final report
- verifier result
- per-step timing and model data

### Optional external tracing

If `LANGSMITH_API_KEY` is configured:

- send LangGraph traces to LangSmith
- include `run_id`, `profile_id`, `user_id`, and `environment` as metadata

If it is not configured:

- the feature still works using only AppTrail database audits

### Metrics

Extend `backend/metrics.py` with:

- `research_runs_total`
- `research_run_duration_seconds`
- `research_run_step_duration_seconds`
- `research_run_failures_total`
- `research_reports_generated_total`
- `research_sources_fetched_total`
- `research_evidence_items_total`

## Security And Consent

### Consent rules

`research` and `hybrid` modes require:

- `core = true`
- `ai_processing = true`
- `web_research = true`

If the user does not grant `web_research`, the UI must disable research mode and explain why.

### Data handling rules

- do not store raw page HTML in run-step audit rows
- store raw fetched content in `ResearchSourceItem`
- redact secrets and tokens from any persisted input or output JSON
- keep raw user resume text out of trace payloads unless explicitly needed
- use content hashes to suppress duplicate fetches

## Testing Plan

### Unit tests

Add:

- node-level tests for each graph node
- schema validation tests
- evidence dedupe tests
- report diff tests
- alert preference tests

### Integration tests

Add:

- profile create/update with research mode fields
- queue run endpoint
- successful research run persistence
- failed step persistence
- report retrieval
- report feedback persistence
- trace endpoint output

### Evals

Create a small eval set under `tests/evals/research_radar/` with curated examples that measure:

- brief normalization quality
- search-plan relevance
- evidence extraction accuracy
- report grounding
- report usefulness

Use app-specific eval data, not generic benchmarks, for go/no-go decisions.

## Rollout Plan

### Phase 1

- schema changes
- queue-based runs
- LangGraph report pipeline
- saved reports
- audit tables
- report UI

### Phase 2

- hybrid mode
- report diff UI
- report-based actions
- trace panel

### Phase 3

- online evaluators
- optional LangSmith dashboards
- open-model eval lane

## Definition Of Done

This project is complete when all of the following are true:

- a user can create a `research` or `hybrid` tracker
- a tracker can run manually or on schedule
- a run produces a saved report with dated history
- every report has evidence, citations, and actions
- every graph step is saved with status, input, output, and error state
- failed runs can be debugged from persisted records without reproducing the run
- the feature respects consent and notification settings
- the feature has focused API tests, graph tests, and evals

## Implementation Order

Build in this exact order:

1. Add migrations for profile/run/report/step/evidence changes
2. Update SQLAlchemy models
3. Add new AI task configs and prompt registry generation
4. Build `research_radar` schemas and graph state
5. Build storage and audit helpers
6. Build nodes in order from context to persist
7. Add Celery task module and beat schedule
8. Convert run endpoint to queue-based execution
9. Add report and trace APIs
10. Add frontend tracker form changes
11. Add report list and detail UI
12. Add report feedback and trace panel
13. Add metrics and optional LangSmith instrumentation
14. Add tests and evals

## External References

- LangGraph workflows and agents: https://docs.langchain.com/oss/python/langgraph/workflows-agents
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangSmith observability concepts: https://docs.langchain.com/langsmith/observability-concepts
- OpenAI GPT-5.4 model docs: https://developers.openai.com/api/docs/models/gpt-5.4
- OpenAI GPT-5.1 model docs: https://developers.openai.com/api/docs/models/gpt-5.1
- OpenAI GPT-4o Search Preview docs: https://developers.openai.com/api/docs/models/gpt-4o-search-preview
- OpenAI evaluation best practices: https://developers.openai.com/api/docs/guides/evaluation-best-practices
- OpenAI external model evaluation guide: https://developers.openai.com/api/docs/guides/external-models
- OpenAI gpt-oss-20b model docs: https://developers.openai.com/api/docs/models/gpt-oss-20b
- Qwen3-235B-A22B-Instruct-2507 model card: https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507
