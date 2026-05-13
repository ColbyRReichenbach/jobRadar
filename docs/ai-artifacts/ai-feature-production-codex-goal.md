# Codex Goal: AI Production Foundation

Date: 2026-05-11
Source plan: `docs/ai-artifacts/ai-feature-production-spec-final.md`
Supporting review: `docs/ai-artifacts/ai-feature-production-spec-gap-review.md`

Status: this file is retained as goal-planning history. Goal 1 and the retrieval foundation/eval/shadow work that followed it are now implemented; use the progress logs in this folder for completed scope and validation.

## Purpose

This file turns the finalized AI production plan into a realistic Codex `/goal` command.

Do not use one `/goal` run to implement the entire six-phase roadmap. The final plan spans classifier tracing, action dedupe, retrieval, Radar source intelligence, resume grounding, Copilot grounding, and governance loops. That is too broad for one durable objective because each later phase depends on data, evals, schema decisions, and product-risk checks from earlier phases.

The right first goal is the production foundation slice: trace what the existing AI surfaces are doing, centralize action candidates and dedupe policy, preserve current UX behavior, and create enough artifacts that later retrieval/Radar/Copilot goals can be evaluated honestly.

## Enable `/goal`

In Codex CLI, enable goals through `/experimental`, or add this to Codex `config.toml`:

```toml
[features]
goals = true
```

Then paste the command below into Codex.

## Historical Goal 1 `/goal` Command

```text
/goal Implement the first production-foundation slice from docs/ai-artifacts/ai-feature-production-codex-goal.md. Read docs/ai-artifacts/ai-feature-production-spec-final.md and docs/ai-artifacts/ai-feature-production-spec-gap-review.md first. Complete only Goal 1: classifier traces, action-candidate and dedupe scaffolding, alert/recommendation dedupe metadata where safe, and validation artifacts. Preserve existing user-facing behavior unless a change is required for duplicate suppression. Stop when the checkpoints in this goal file are complete, relevant tests pass, and a short progress log records changed files, validation commands, and remaining limitations. Pause before any irreversible migration, broad scraping/RAG implementation, autonomous state mutation, or decision that needs production data not available locally.
```

## Goal 1 Objective

Implement a narrow foundation that makes the current AI system observable and safer without pretending the full production architecture exists.

Target outcome:

```text
existing signals
  -> classifier/action traces
  -> ActionCandidate scaffold
  -> shared DedupeGate scaffold
  -> Alert/RecommendedAction dedupe linkage where safe
  -> tests and artifacts proving behavior
```

## Required Context To Read First

- `docs/ai-artifacts/ai-feature-production-spec-final.md`
- `docs/ai-artifacts/ai-feature-production-spec-gap-review.md`
- `backend/services/email_classifier.py`
- `backend/services/gmail_intelligence/orchestrator.py`
- `backend/services/gmail_intelligence/feature_extractor.py`
- `backend/services/gmail_intelligence/scorer.py`
- `backend/services/search/documents.py`
- `backend/services/copilot/orchestrator.py`
- `backend/services/research_radar/graph.py`
- `backend/services/job_sources/`
- `backend/services/source_intelligence/`
- `backend/models.py`
- Existing duplicate, alert, Gmail, and Radar tests under `tests/`

## Scope

Allowed:

- Add or extend trace models only after checking current migrations and model conventions.
- Add an `ActionCandidate` model/service if it fits the current data layer.
- Add a shared `DedupeGate` service that wraps existing deterministic duplicate behavior before replacing endpoint-specific code.
- Add dedupe keys and source/action linkage to alerts or recommendations when schema risk is low.
- Persist Gmail classifier route/subtype/decision metadata through a trace or equivalent fields.
- Pass existing extracted URL signals into trace/action extraction if the data is already available.
- Add focused tests for dedupe keys, candidate creation, trace persistence, and no-regression behavior.
- Add a generated artifact or script that records local runtime table availability/counts with git SHA and timestamp if it is small and low risk.

Not allowed in this goal:

- Do not replace the Gmail classifier with a trained model.
- Do not enable LLM classification by default.
- Do not build full chunked RAG, embeddings, reranking, or OpenSearch integration.
- Do not convert Radar into broad autonomous web scraping.
- Do not ingest arbitrary GitHub repos or repo ZIPs for resume evidence.
- Do not auto-mutate application state from AI output without explicit user confirmation.
- Do not cite unverifiable local runtime counts as production facts.

## Checkpoints

### 1. Current-State Verification

Before editing, inspect the current files and summarize:

- Where Gmail classification results are produced and persisted.
- Where job/contact/interview/Radar duplicate checks currently live.
- How alerts and recommended actions are modeled today.
- Which migration framework and test patterns are already used.

Output expected:

- A short implementation plan.
- A decision on whether schema changes are safe in this run.
- The exact tests that should prove the change.

### 2. Action Candidate Scaffold

Create the smallest useful shared action-candidate layer.

Required fields or equivalent:

- `user_id`
- `source_type`
- `source_id`
- `action_type`
- `target_entity_type`
- `target_entity_id`
- `target_fingerprint`
- `dedupe_key`
- `duplicate_type`
- `duplicate_matches_json`
- `policy_decision`
- `status`
- `confidence`
- `requires_confirmation`
- `evidence_json`

Required statuses:

- `proposed`
- `suppressed_duplicate`
- `linked_existing`
- `pending_review`
- `accepted`
- `dismissed`
- `expired`
- `failed_validation`

Acceptance criteria:

- Existing endpoints can continue without needing to adopt the model immediately.
- Candidate creation is deterministic for the same source/action/entity.
- Tests cover stable dedupe-key generation.

### 3. Shared Dedupe Gate

Introduce a service that computes fingerprints and duplicate decisions for the first set of action types.

Minimum supported action types:

- `add_job_to_pipeline`
- `add_network_contact`
- `schedule_interview`
- `review_radar_opportunity`

Acceptance criteria:

- The service can call or mirror existing duplicate logic without changing user-visible behavior.
- Duplicate decisions include a reason and candidate matches.
- Tests cover hard duplicate, soft duplicate, and no duplicate cases where existing fixtures support them.

### 4. Gmail Classification Trace

Persist enough classifier metadata to separate classification confidence from action confidence.

Minimum trace data:

- classifier mode
- route
- subtype
- route confidence
- subtype confidence if available
- decision path
- threshold or policy version when available
- matched signals or feature summary
- preflight/adjudication status when available
- candidate/source URL count when available

Acceptance criteria:

- Current `EmailEvent` behavior is preserved.
- Trace creation does not store sensitive raw content beyond existing persistence policy.
- Tests cover trace creation for deterministic mode and dry-run behavior.

### 5. Alert And Recommendation Dedupe Metadata

Add dedupe metadata where safe.

Minimum target:

- A stable dedupe key for generated alerts/recommendations.
- Linkage to an action candidate where implementation is low risk.
- Suppression status or duplicate reason where the current schema supports it.

Acceptance criteria:

- Existing alert creation tests still pass.
- Duplicate-prone paths can suppress or mark duplicates deterministically.
- No existing notification behavior changes without explicit test coverage.

### 6. Runtime And Eval Artifacts

Create or update a lightweight artifact path that prevents future specs from citing unverifiable runtime counts.

Minimum artifact requirements:

- database source label without secrets
- git SHA
- migration version if available
- query timestamp
- table counts
- missing-table warnings

Acceptance criteria:

- The artifact can be generated locally without production secrets.
- The command is documented.
- The generated output clearly distinguishes missing tables from zero rows.

### 7. Validation

Run the smallest reliable test set that covers changed surfaces.

Start with relevant tests such as:

```bash
pytest tests/test_duplicates.py tests/test_alerts.py tests/test_email_suggestions.py tests/test_gmail_intelligence.py tests/test_gmail_sync.py
pytest tests/test_ai_artifacts.py tests/test_ai_promotion_reports.py
```

If schema or model changes touch broader code, expand to:

```bash
pytest tests/test_notifications.py tests/test_research_radar_graph.py tests/test_opportunity_radar.py tests/test_source_discovery.py
```

Acceptance criteria:

- All directly relevant tests pass.
- If a test cannot run because of missing local services or secrets, record the exact blocker.
- Add or update tests for every new service/model behavior.

## Pause Conditions

Pause and ask for direction if:

- A migration could destroy or rewrite existing user data.
- Current schemas contradict the proposed `ActionCandidate` model.
- The implementation would require production-only credentials or unavailable runtime data.
- A test failure appears unrelated to the changes and could reflect existing dirty worktree state.
- The next step would require autonomous browsing, scraping, or provider access beyond verified source adapters.
- The goal starts expanding into retrieval, embeddings, Radar web research, or resume repo ingestion.

## Done Criteria

Goal 1 is done when:

- The current-state verification is recorded in the progress log.
- Action-candidate and dedupe scaffolding exists or a code-verified reason explains why it was deferred.
- Gmail classification traces or equivalent persisted metadata exist.
- Alert/recommendation dedupe metadata is added where safe or explicitly deferred with reasons.
- A runtime/eval artifact path exists for reproducible counts and missing-table warnings.
- Relevant tests pass or blockers are documented.
- The final progress log lists changed files, commands run, limitations, and the next recommended goal.

## Later `/goal` Commands

Goal 1 and the retrieval foundation/eval/shadow goals are complete. The Goal 2 command below is retained for traceability, not as the next recommended command.

### Goal 2: Retrieval Foundation - Completed

```text
/goal Implement Phase 2 from docs/ai-artifacts/ai-feature-production-spec-final.md: add user knowledge documents, document chunks, retrieval traces, and a local lexical fallback eval harness. Do not add embeddings or reranking until chunking and trace tests pass. Stop when source-level search behavior is preserved, chunk indexing is tested, retrieval traces are persisted, and recall/citation eval artifacts can be generated locally.
```

### Goal 3: Source-Registry Radar

```text
/goal Implement Phase 3 from docs/ai-artifacts/ai-feature-production-spec-final.md: make Radar prefer verified CompanyJobSource and JobPosting records before broad web fallback, add source trust/freshness scoring, and route Radar alerts through the shared action/dedupe layer. Stop when tests prove verified sources are selected first, broad search fallback is explicitly marked lower confidence, and duplicate Radar alerts are suppressed or linked.
```

### Goal 4: Evidence-Grounded Resume Tailoring

```text
/goal Implement Phase 4 from docs/ai-artifacts/ai-feature-production-spec-final.md: add manual project facts, convert them into searchable evidence, and require evidence IDs for new resume bullets. Do not ingest arbitrary repos. Stop when unsupported resume claims are rejected, evidence-backed bullets are tested, and resume eval artifacts report unsupported-claim rate.
```

### Goal 5: Production Copilot Grounding

```text
/goal Implement Phase 5 from docs/ai-artifacts/ai-feature-production-spec-final.md: add Copilot intent routing, source-specific retrieval planning, claim extraction, and citation-support validation. Keep Copilot read-only except for explicit ActionCandidate proposals. Stop when unsupported factual claims are detected, citation support is measured, and leakage/prompt-injection tests pass.
```

### Goal 6: Continuous Improvement Loop

```text
/goal Implement Phase 6 from docs/ai-artifacts/ai-feature-production-spec-final.md: connect feedback, eval datasets, shadow runs, promotion reports, prompt registry entries, and model cards into a reproducible governance loop. Stop when AI-relevant changes can generate comparable artifacts with git SHA, dataset versions, model/prompt/retriever versions, metrics, costs, safety summaries, and promote/reject decisions.
```
