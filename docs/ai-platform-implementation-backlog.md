# AI Platform Implementation Backlog

This backlog turns `docs/ai-copilot-search-eval-plan.md` into stacked, reviewable implementation work.

Use this as the execution checklist for the AI platform initiative. Each vertical should be implemented on its own branch, tested independently, reviewed independently, and merged only when its scoped checks are green.

## Working Rules

- Integration branch: `ai-platform`.
- Each vertical branch targets the branch it depends on.
- Each vertical PR must include feature code, tests, docs updates, rollout notes, rollback notes, and acceptance evidence.
- Keep branches vertical and reviewable. Do not merge unrelated refactors into feature branches.
- Shared foundations such as migrations, `backend/models.py`, auth dependencies, API clients, and common test fixtures should be changed as early in the stack as possible.
- If a later branch finds a foundation gap, open a focused fix against the earliest affected layer and rebase dependent branches.
- Generated demo reports belong under `docs/interview-artifacts/generated`; runtime code must not depend on generated demo artifacts.
- Production UI must call authenticated backend APIs through typed clients. Hardcoded demo data belongs only in fixtures, seed scripts, tests, or clearly labeled static reports.

## Shared Quality Gate

Run before merging each vertical:

```bash
pytest -q
python3 -m compileall -q backend
cd dashboardv2 && npm run lint
cd dashboardv2 && npm run build
cd dashboardv2 && npm run test:smoke
git diff --check
```

After CI helper scripts exist, use:

```bash
scripts/ci/run_backend_checks.sh
scripts/ci/run_dashboard_checks.sh
scripts/ci/run_ai_feature_checks.sh
```

Failure loop:

1. Read failing job logs and artifacts.
2. Reproduce the narrow failure locally.
3. Make the smallest targeted fix.
4. Rerun the failing command.
5. Rerun the vertical-specific test group.
6. Rerun the shared quality gate.
7. Do not merge red tests.

## Stack Overview

| Order | Branch | Depends on | Main outcome |
| --- | --- | --- | --- |
| 1 | `ai/ci-baseline` | current main | CI/CD gates, env docs, deployment checklist, known limitations |
| 2 | `ai/foundation-ledger` | `ai/ci-baseline` | AI ledger schema, token/cost accounting, model pricing, lineage base |
| 3 | `ai/report-generation` | `ai/foundation-ledger` | deterministic report generation and progress index |
| 4 | `ai/classifier-evals` | `ai/report-generation` | classifier eval datasets, metrics, report |
| 5 | `ai/radar-lineage` | `ai/report-generation` | Radar quality and lineage artifacts |
| 6 | `ai/search-index` | `ai/foundation-ledger` | user-scoped search index and adapters |
| 7 | `ai/copilot-backend` | `ai/search-index` | Copilot APIs, retrieval, citations, fallback, safety controls |
| 8 | `ai/copilot-frontend` | `ai/copilot-backend` | native dashboard Copilot UI and frontend contract tests |
| 9 | `ai/search-evals` | `ai/search-index` | search eval datasets and ranking report |
| 10 | `ai/copilot-evals-redteam` | `ai/copilot-backend` | assistant evals and red-team gates |
| 11 | `ai/experiments-feedback` | `ai/copilot-backend` | feedback rewards, A/B, shadow tests, promotion reports |
| 12 | `ai/admin-ai-ops` | `ai/experiments-feedback` | admin telemetry, trace review, model cards, promotion review UI |
| 13 | `ai/governance-scale-artifacts` | `ai/admin-ai-ops` | cost scaling memo, governance artifact, risk controls, demo script |

## Vertical 1: CI Baseline

Branch: `ai/ci-baseline`

Depends on: current repository baseline

Goal: establish the automated quality gate before feature work starts.

Likely files:

- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- `.env.example`
- `docs/deployment-checklist.md`
- `docs/production-readiness-audit.md`
- `docs/interview-artifacts/known-ai-limitations-and-deferred-controls.md`
- `scripts/ci/run_backend_checks.sh`
- `scripts/ci/run_dashboard_checks.sh`
- `scripts/ci/run_ai_feature_checks.sh`

Tasks:

- [x] Create `ai-platform` integration branch.
- [x] Create `ai/ci-baseline` from the current repository baseline.
- [x] Add CI workflow for backend tests, compile checks, dashboard type-check, dashboard build, Playwright smoke tests, targeted AI feature tests, security tests, contract tests, and `git diff --check`.
- [x] Add deploy workflow with production promotion gates, environment validation, post-deploy smoke checks, and rollback or feature-flag disablement path.
- [x] Add CI helper scripts that run the same commands locally and in CI.
- [x] Add documented AI feature flags and budget variables to `.env.example`.
- [x] Add deployment checklist items for Copilot, Search, evals, AI budgets, telemetry retention, auth mode, and CORS origins.
- [x] Add known limitations and deferred controls page.
- [x] Document that Copilot is dashboard-JWT-only and unavailable to extension API keys.
- [x] Document demo data sanitization policy.
- [x] Document "what we will not automate" policy for Copilot suggested actions.

Required tests/checks:

```bash
pytest -q
python3 -m compileall -q backend
cd dashboardv2 && npm run lint
cd dashboardv2 && npm run build
cd dashboardv2 && npm run test:smoke
git diff --check
```

Acceptance criteria:

- [x] CI workflow fails on backend test failure.
- [x] CI workflow fails on frontend type/build failure.
- [x] CI workflow fails on Playwright smoke failure.
- [x] CI workflow fails on diff whitespace errors.
- [x] CI helper scripts can run locally.
- [x] Deploy workflow requires green CI before production promotion.
- [x] Post-deploy smoke requirements are documented.
- [x] Known limitations page exists and clearly separates demo, beta, scale, and deferred controls.

Rollout:

- Safe to merge first. It changes process and docs, not runtime product behavior.

Rollback:

- Revert workflow/scripts if CI blocks unrelated emergency work, then re-add with a targeted fix.

## Vertical 2: Foundation Ledger

Branch: `ai/foundation-ledger`

Depends on: `ai/ci-baseline`

Goal: create the durable audit, cost, model, and lineage foundation all later AI features use.

Likely files:

- `backend/models.py`
- new Alembic migration
- `backend/services/ai_runner.py`
- `backend/services/ai_usage.py`
- `backend/services/ai_pricing.py`
- `backend/services/ai_artifacts.py`
- `backend/services/model_cards.py`
- `backend/config.py`
- `.env.example`
- `tests/test_copilot_schema.py`
- `tests/test_ai_usage.py`
- `tests/test_ai_token_accounting.py`
- `tests/test_ai_artifacts.py`
- `tests/test_model_cards.py`

Data tasks:

- [x] Add `ai_model_calls`.
- [x] Add `ai_artifacts`.
- [x] Add `ai_model_pricing`.
- [x] Add `ai_model_cards`.
- [x] Add `ai_admin_access_logs` if trace access auditing is part of the base schema.
- [x] Add indexes for user, surface, task, model, prompt version, variant, status, created date, and artifact references.
- [x] Add migration defaults that do not break existing rows.
- [x] Add rollback-safe nullable columns where production backfill would be needed later.

Backend tasks:

- [x] Add model pricing config with conservative defaults and environment override support.
- [x] Add `run_ai_task` wrapper or extend existing AI call path to log model calls.
- [x] Record surface, task, model, prompt version, variant, release version, status, latency, validation result, fallback state, and error class.
- [x] Track prompt, retrieval-context, tool-output, cached-input, reasoning, output, billable input, and billable output tokens when provider data is available.
- [x] Estimate cost from versioned pricing records.
- [x] Add artifact lineage helper that links generated outputs back to model calls.
- [x] Add model card lookup and missing-card warning for production AI tasks.
- [x] Ensure raw API keys, OAuth payloads, refresh tokens, encrypted Gmail tokens, and unrelated user data are never stored in trace tables.
- [x] Add retention/deletion hooks or placeholders for later governance branch.

Security tasks:

- [x] Ensure AI ledger rows are scoped by user when tied to user data.
- [x] Ensure admin views are aggregated/redacted by default.
- [x] Ensure extension API keys cannot access ledger admin routes.
- [x] Ensure full trace access is disabled by default.

Required tests/checks:

```bash
pytest -q tests/test_copilot_schema.py
pytest -q tests/test_ai_usage.py
pytest -q tests/test_ai_token_accounting.py
pytest -q tests/test_ai_artifacts.py
pytest -q tests/test_model_cards.py
pytest -q
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Model calls create usage rows.
- [x] Usage rows include token breakdown and billable token counts.
- [x] Cost estimates use versioned pricing.
- [x] Generated artifacts can be linked to source model calls.
- [x] Production AI task without a model card produces an explicit warning.
- [x] No sensitive token or secret payload is persisted.
- [x] Existing AI behavior continues to work with deterministic fallback paths.

Rollout:

- Ship behind logging-only behavior first.
- Keep new admin-facing routes disabled or absent until Admin AI Ops vertical.

Rollback:

- Disable AI call logging through config if a production issue appears.
- Preserve migration rollback steps for local/dev; for production, prefer forward fix if data has been written.

## Vertical 3: Report Generation

Branch: `ai/report-generation`

Depends on: `ai/foundation-ledger`

Goal: make eval and governance artifacts reproducible, dated, immutable, and linkable.

Likely files:

- `backend/services/reports/report_templates.py`
- `backend/services/reports/report_writer.py`
- `backend/services/reports/progress_index.py`
- `backend/services/reports/summary_writer.py`
- `scripts/generate_ai_report.py`
- `scripts/regenerate_ai_progress_index.py`
- `docs/interview-artifacts/ai-system-progress-over-time.md`
- `docs/interview-artifacts/generated/.gitkeep`
- `tests/test_report_generation.py`
- `tests/test_progress_index.py`

Backend/script tasks:

- [x] Add deterministic report metadata schema.
- [x] Add Markdown report template renderer.
- [x] Add metric table renderer.
- [x] Add token/cost table renderer.
- [x] Add supporting artifact link renderer.
- [x] Add optional AI summary writer constrained to computed metrics only.
- [x] Add overwrite protection for dated generated reports.
- [x] Add progress index generator that links to all generated reports.
- [x] Add report metadata validation for git SHA, release, dataset version, model, prompt version, token breakdown, cost, latency, metrics, recommendation, and decision.
- [x] Add JSON fixture inputs for report tests.

Documentation tasks:

- [x] Create `docs/interview-artifacts/ai-system-progress-over-time.md`.
- [x] Document report naming convention.
- [x] Document how to regenerate reports from structured inputs.
- [x] Document that deterministic metric tables do not depend on AI.

Required tests/checks:

```bash
pytest -q tests/test_report_generation.py
pytest -q tests/test_progress_index.py
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Report can be regenerated from structured JSON input.
- [x] Generated reports are immutable by default.
- [x] Progress index links to every generated report.
- [x] AI summary is optional and cannot introduce unsupported claims.
- [x] Report includes metadata needed for reproducibility.
- [x] Report tests use deterministic fixtures and no live model calls.

Rollout:

- Safe to merge once deterministic tests pass. This branch is mostly scripts/docs.

Rollback:

- Revert generated report scripts if they write incorrect output. Keep generated artifacts out of runtime code paths.

## Vertical 4: Classifier Evals

Branch: `ai/classifier-evals`

Depends on: `ai/report-generation`

Goal: produce credible, reproducible classifier evidence for email/job-stage extraction.

Likely files:

- `evals/email_classifier/email_classifier_v1.jsonl`
- `evals/labeling-guidelines.md`
- `evals/dataset-governance.md`
- `backend/services/evals/classifier_eval.py`
- `scripts/run_email_classifier_eval.py`
- `docs/interview-artifacts/email-classifier-eval.md`
- `tests/test_classifier_eval.py`

Tasks:

- [x] Add sanitized JSONL dataset.
- [x] Add stable label taxonomy for job-related vs non-job-related messages.
- [x] Add stage labels for applied, interview, assessment, offer, rejection, follow-up, and unknown.
- [x] Add labeling guidelines with examples and edge cases.
- [x] Add dataset governance doc covering golden, rolling, and red-team sets.
- [x] Add deterministic evaluator.
- [x] Compute precision, recall, F1, confusion matrix, stage accuracy, latency, and cost.
- [x] Compare current production prompt/model against at least one alternate.
- [x] Generate Markdown report through report generation framework.
- [x] Explain recall-over-precision tradeoff for job email filtering.

Required tests/checks:

```bash
pytest -q tests/test_classifier_eval.py
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Eval script produces metrics JSON.
- [x] Eval script produces Markdown report.
- [x] Report includes confusion matrix.
- [x] Report explains missed-job-email risk and chosen threshold/tradeoff.
- [x] Golden dataset changes require explicit version bump.
- [x] No eval fixture contains real personal email data.

Rollout:

- Keep eval datasets sanitized and committed only when safe.

Rollback:

- Revert dataset or evaluator changes if metrics are invalid. Do not alter production classifier behavior in this branch unless explicitly scoped.

## Vertical 5: Radar Lineage

Branch: `ai/radar-lineage`

Depends on: `ai/report-generation`

Goal: make Radar outputs traceable, measurable, and interview-ready.

Likely files:

- `backend/services/radar/*`
- `backend/services/ai_artifacts.py`
- `backend/services/reports/*`
- `scripts/run_radar_lineage_report.py`
- `docs/interview-artifacts/radar-lineage-report.md`
- `tests/test_radar_lineage.py`
- `tests/test_radar_quality_metrics.py`

Tasks:

- [x] Link Radar reports to source model calls through `AiArtifact.model_call_id`.
- [x] Record source URLs or source ids using existing Radar source/evidence rows without storing raw source text in reports.
- [x] Add Radar artifact metadata for company, role area, topic, generated date, model, prompt version, and cost.
- [x] Add Radar quality metrics: source freshness, duplicate rate, source coverage, unsupported-claim rate, and cost per report.
- [x] Add report generator for Radar lineage.
- [x] Keep cross-user aggregate company data anonymized; no aggregate company-data contract changes in this vertical.
- [x] Ensure user-specific Radar outputs remain user-scoped.

Required tests/checks:

```bash
pytest -q tests/test_radar_lineage.py
pytest -q tests/test_radar_quality_metrics.py
pytest -q
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Radar artifact links back to model calls and sources.
- [x] Radar lineage report can be generated from deterministic fixtures.
- [x] Radar report does not expose another user's private data.
- [x] Radar quality metrics are computed and documented.
- [x] Existing Radar feature flags still work.

Rollout:

- Enable lineage logging first; keep new report generation manual or admin-only.

Rollback:

- Disable Radar lineage report generation without disabling core Radar if needed.

## Vertical 6: Search Index

Branch: `ai/search-index`

Depends on: `ai/foundation-ledger`

Goal: create a user-scoped search layer that Copilot and evals can rely on.

Likely files:

- `backend/services/search/indexer.py`
- `backend/services/search/documents.py`
- `backend/services/search/backends/base.py`
- `backend/services/search/backends/postgres.py`
- `backend/services/search/backends/opensearch.py`
- `backend/tasks/index_search_documents.py`
- `backend/config.py`
- `tests/test_search_indexing.py`
- `tests/test_search_user_isolation.py`

Tasks:

- [x] Add search document builder for applications, emails, Radar reports, and contacts.
- [x] Add Postgres search backend as default for local and CI.
- [x] Add OpenSearch adapter behind `SEARCH_BACKEND=opensearch`.
- [x] Add indexing task after application/email/Radar/contact write paths.
- [x] Add full reindex task.
- [x] Add search backend health check.
- [x] Add stale-index metrics.
- [x] Add graceful degradation when OpenSearch is unavailable.
- [x] Ensure search result ids are always scoped to authenticated user.

Required tests/checks:

```bash
pytest -q tests/test_search_indexing.py
pytest -q tests/test_search_user_isolation.py
pytest -q
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Search documents are indexed for target objects.
- [x] Search results never include another user's records.
- [x] CI does not require OpenSearch.
- [x] OpenSearch failure falls back or degrades gracefully.
- [x] Indexing failures are observable through metrics/logging hooks.

Rollout:

- Default to Postgres backend.
- Keep OpenSearch optional until infrastructure exists.

Rollback:

- Disable search indexing task or fall back to Postgres backend.

## Vertical 7: Copilot Backend

Branch: `ai/copilot-backend`

Depends on: `ai/search-index`

Goal: create secure, cited, budgeted Copilot backend APIs.

Likely files:

- `backend/routes/copilot.py`
- `backend/services/copilot/orchestrator.py`
- `backend/services/copilot/retrieval.py`
- `backend/services/copilot/citations.py`
- `backend/services/copilot/schemas.py`
- `backend/services/copilot/tools.py`
- `backend/services/copilot/guardrails.py`
- `backend/main.py`
- `tests/test_copilot_api.py`
- `tests/test_copilot_security.py`
- `tests/test_copilot_abuse_controls.py`

Tasks:

- [x] Add dashboard JWT-only Copilot router.
- [x] Add conversation create/list/read endpoints.
- [x] Add message endpoint.
- [x] Add feedback endpoint if minimal feedback is needed before experiments branch.
- [x] Add search endpoint or reuse search API with strict user scoping.
- [x] Add `copilot_answer` AI task.
- [x] Add retrieval flow using user-scoped search results.
- [x] Add citation validation that rejects model-produced ids not retrieved by backend.
- [x] Add structured response schema validation.
- [x] Add search-only fallback when model calls fail or are disabled.
- [x] Add rate limits.
- [x] Add per-user and global daily budget caps.
- [x] Add max context length and max conversation length controls.
- [x] Add prompt-abuse controls.
- [x] Add typed backend contracts for frontend.

Security tasks:

- [x] Return 403 for extension API keys.
- [x] Verify every accepted id server-side.
- [x] Refuse cross-user citation ids.
- [x] Redact sensitive trace data.
- [x] Ensure suggested actions are read-only or `requires_confirmation=true`.

Required tests/checks:

```bash
pytest -q tests/test_copilot_api.py
pytest -q tests/test_copilot_security.py
pytest -q tests/test_copilot_abuse_controls.py
pytest -q tests/test_search_user_isolation.py
pytest -q
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Authenticated dashboard user can ask a question and receive a cited answer.
- [x] Extension API key receives 403.
- [x] User cannot retrieve or cite another user's data.
- [x] Copilot returns graceful fallback if model call fails.
- [x] Copilot enforces rate and budget caps.
- [x] Copilot refuses or degrades gracefully when input/context limits are exceeded.

Rollout:

- Ship behind `COPILOT_ENABLED=false` by default until frontend and evals are ready.

Rollback:

- Disable `COPILOT_ENABLED`.
- Keep search backend available for non-Copilot use if safe.

## Vertical 8: Copilot Frontend

Branch: `ai/copilot-frontend`

Depends on: `ai/copilot-backend`

Goal: add Copilot UI that feels native to the current dashboard and is fully API-backed.

Likely files:

- `dashboardv2/src/components/copilot/CopilotLauncher.tsx`
- `dashboardv2/src/components/copilot/CopilotPanel.tsx`
- `dashboardv2/src/components/copilot/CopilotMessage.tsx`
- `dashboardv2/src/components/copilot/CopilotCitations.tsx`
- `dashboardv2/src/components/copilot/CopilotFeedback.tsx`
- `dashboardv2/src/components/copilot/CopilotSuggestedActions.tsx`
- `dashboardv2/src/lib/copilotApi.ts`
- `dashboardv2/tests/smoke.spec.ts`
- `dashboardv2/tests/copilot-a11y.spec.ts`
- `dashboardv2/tests/copilot-contract.spec.ts`

Tasks:

- [x] Inspect existing dashboard layout, sidebar, cards, tables, buttons, tabs, empty states, loading states, typography, colors, border radius, and spacing.
- [x] Add fixed bottom-right launcher.
- [x] Expand launcher on hover from icon-only to icon plus `Ask AppTrail`.
- [x] Add docked desktop panel.
- [x] Add mobile bottom sheet.
- [x] Add starter prompts.
- [x] Add message rendering.
- [x] Add citation rendering.
- [x] Add feedback controls.
- [x] Add loading, empty, error, unauthorized, disabled, budget-exceeded, and degraded-backend states.
- [x] Hide launcher when `VITE_COPILOT_ENABLED=false`.
- [x] Add keyboard navigation, focus management, and screen-reader labels.
- [x] Add typed `copilotApi.ts` methods.
- [x] Ensure production UI has no hardcoded answers, citations, costs, or metrics.

Required tests/checks:

```bash
cd dashboardv2 && npm run lint
cd dashboardv2 && npm run build
cd dashboardv2 && npm run test:smoke
cd dashboardv2 && npx playwright test tests/copilot-contract.spec.ts
cd dashboardv2 && npx playwright test tests/copilot-a11y.spec.ts
git diff --check
```

Acceptance criteria:

- [x] Desktop smoke test opens Copilot and sends a mocked message.
- [x] Mobile viewport shows bottom-sheet behavior.
- [x] Text does not overflow buttons, cards, or panels.
- [x] Non-authenticated users do not see Copilot.
- [x] Copilot launcher and panel pass accessibility checks.
- [x] Copilot UI matches current AppTrail dashboard aesthetic.
- [x] Frontend request/response types match backend contracts.

Rollout:

- Keep hidden behind `VITE_COPILOT_ENABLED=false` until backend and security tests are green.

Rollback:

- Disable frontend flag. Backend remains protected by server-side auth and feature flag.

## Vertical 9: Search Evals

Branch: `ai/search-evals`

Depends on: `ai/search-index`

Goal: prove search quality and cost/latency tradeoffs instead of assuming retrieval works.

Likely files:

- `evals/search/search_queries_v1.jsonl`
- `evals/search/search_baselines_v1.json`
- `backend/services/evals/search_eval.py`
- `scripts/run_search_eval.py`
- `docs/interview-artifacts/search-eval.md`
- `tests/test_search_eval.py`

Tasks:

- [x] Add sanitized search query dataset.
- [x] Add expected relevant document ids for seeded user fixtures.
- [x] Evaluate keyword-only baseline.
- [x] Evaluate vector-only if embeddings are available.
- [x] Evaluate hybrid strategy.
- [x] Evaluate hybrid-plus-boost strategy.
- [x] Compute Recall@3, Recall@5, MRR, nDCG@10, zero-result rate, and latency.
- [x] Add stale-index and indexing-failure metrics.
- [x] Generate Markdown report.
- [x] Include user-isolation guardrail result.

Required tests/checks:

```bash
pytest -q tests/test_search_eval.py
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Report shows which search strategy wins and why.
- [x] Report compares semantic retrieval against keyword baseline.
- [x] Report includes latency and zero-result rate.
- [x] Report includes user-isolation guardrail result.
- [x] No live OpenSearch or live model provider is required in CI.

Rollout:

- Eval only. No production ranking change unless explicitly added and tested.

Rollback:

- Revert eval data/report generator if flawed; do not alter search runtime in this branch unless scoped.

## Vertical 10: Copilot Evals And Red Team

Branch: `ai/copilot-evals-redteam`

Depends on: `ai/copilot-backend`

Goal: measure Copilot groundedness, citation quality, refusal behavior, and critical safety failures.

Likely files:

- `evals/copilot/copilot_questions_v1.jsonl`
- `evals/copilot/failure-taxonomy.md`
- `evals/red_team/prompt_injection_v1.jsonl`
- `evals/red_team/data_leakage_v1.jsonl`
- `evals/red_team/secret_leakage_v1.jsonl`
- `evals/red_team/unsupported_claims_v1.jsonl`
- `evals/red_team/pii_leakage_v1.jsonl`
- `evals/red_team/unsafe_advice_v1.jsonl`
- `backend/services/evals/assistant_eval.py`
- `backend/services/red_team.py`
- `scripts/run_copilot_eval.py`
- `scripts/run_red_team_eval.py`
- `docs/interview-artifacts/copilot-eval.md`
- `docs/interview-artifacts/red-team-eval.md`
- `tests/test_copilot_eval.py`
- `tests/test_red_team_eval.py`

Tasks:

- [x] Add seeded-data Copilot question dataset.
- [x] Add expected citation coverage for answerable questions.
- [x] Add impossible/ambiguous questions.
- [x] Score answer relevance.
- [x] Score citation coverage.
- [x] Score unsupported claims.
- [x] Score refusal correctness.
- [x] Add failure taxonomy: retrieval, missing data, prompt ambiguity, hallucination, schema failure, stale index, ambiguous ground truth, impossible question.
- [x] Add prompt-injection red-team cases.
- [x] Add data-leakage red-team cases.
- [x] Add secret-leakage red-team cases.
- [x] Add unsupported-claim red-team cases.
- [x] Add PII-leakage red-team cases.
- [x] Add fail-closed gate for critical cases.
- [x] Generate Copilot eval report.
- [x] Generate red-team eval report.

Required tests/checks:

```bash
pytest -q tests/test_copilot_eval.py
pytest -q tests/test_red_team_eval.py
pytest -q tests/test_copilot_security.py
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Copilot eval report includes good and bad examples.
- [x] Copilot eval report includes groundedness, citation coverage, latency, and cost.
- [x] Unsupported user-data claim is counted.
- [x] Critical prompt-injection, data-leakage, and secret-leakage cases fail closed.
- [x] Promotion reports can consume red-team pass/fail metrics later.

Rollout:

- Eval-only branch unless red-team failures reveal required backend fixes.

Rollback:

- Revert flawed eval fixtures or scoring. Preserve safety fixes if they address real vulnerabilities.

## Vertical 11: Experiments And Feedback

Branch: `ai/experiments-feedback`

Depends on: `ai/copilot-backend`

Goal: turn feedback into governed reward signals and enable safe A/B and shadow testing.

Likely files:

- `backend/services/experiments.py`
- `backend/services/promotion_reports.py`
- `backend/services/statistics.py`
- `backend/tasks/run_eval_suite.py`
- `backend/tasks/generate_ai_promotion_reports.py`
- `backend/routes/admin_ai.py`
- `tests/test_ai_experiments.py`
- `tests/test_ai_promotion_reports.py`
- `tests/test_experiment_statistics.py`

Tasks:

- [x] Add feedback reward events.
- [x] Add sticky variant assignment.
- [x] Add shadow testing queue.
- [x] Add A/B selection only when `COPILOT_EXPERIMENTS_ENABLED=true`.
- [x] Link production outputs to hidden candidate outputs.
- [x] Generate promotion reports after configured sample and feedback thresholds.
- [x] Add confidence intervals.
- [x] Add minimum detectable effect and underpowered-test warnings.
- [x] Add task/query mix checks by variant.
- [x] Add cost, latency, quality, feedback, and guardrail comparison tables.
- [x] Add scale projections for 1,000, 10,000, and 1,000,000 users.
- [x] Add admin approval/rejection backend workflow.
- [x] Add experiment pause and kill switch.
- [x] Add guardrail auto-pause rules.

Required tests/checks:

```bash
pytest -q tests/test_ai_experiments.py
pytest -q tests/test_ai_promotion_reports.py
pytest -q tests/test_experiment_statistics.py
python3 -m compileall -q backend
git diff --check
```

Acceptance criteria:

- [x] Users are sticky-assigned to variants.
- [x] Shadow variants are never shown to users.
- [x] Feedback creates reward scores.
- [x] Promotion report is generated after threshold.
- [x] Admin approval is required before traffic changes.
- [x] Experiments can be paused.
- [x] Guardrail breach disables or pauses experiment.

Rollout:

- Keep `COPILOT_EXPERIMENTS_ENABLED=false` until Admin AI Ops review UI exists.

Rollback:

- Disable experiments flag.
- Keep production default variant stable.

## Vertical 12: Admin AI Ops

Branch: `ai/admin-ai-ops`

Depends on: `ai/experiments-feedback`

Goal: make AI telemetry, lineage, experiments, model cards, and trace review visible to an admin without querying the database.

Likely files:

- `backend/routes/admin_ai.py`
- `backend/services/admin_ai.py`
- `dashboardv2/src/components/admin/AiOps.tsx`
- `dashboardv2/src/components/admin/AiRunsTable.tsx`
- `dashboardv2/src/components/admin/AiTelemetryDashboard.tsx`
- `dashboardv2/src/components/admin/AiArtifactLineage.tsx`
- `dashboardv2/src/components/admin/AiExperimentDashboard.tsx`
- `dashboardv2/src/components/admin/AiModelCards.tsx`
- `dashboardv2/src/components/admin/AiPromotionReports.tsx`
- `dashboardv2/src/components/admin/AiTraceAccessLog.tsx`
- `dashboardv2/src/lib/adminAiApi.ts`
- `dashboardv2/tests/admin-ai-ops.spec.ts`
- `tests/test_admin_ai_telemetry.py`

Backend tasks:

- [x] Add admin-only AI Ops routes.
- [x] Add telemetry overview endpoint.
- [x] Add cost endpoint.
- [x] Add latency endpoint.
- [x] Add token endpoint.
- [x] Add failure endpoint.
- [x] Add search-index freshness endpoint.
- [x] Add experiment telemetry endpoint.
- [x] Add runs table endpoint with filters.
- [x] Add run detail endpoint with redacted summaries.
- [x] Add reason-gated full trace endpoint.
- [x] Add trace access log write.
- [x] Add artifact lineage endpoint.
- [x] Add promotion report approval/rejection endpoint.

Frontend tasks:

- [x] Inspect existing admin/dashboard visual patterns before building.
- [x] Add admin-only AI Ops tab.
- [x] Add runs table with filters.
- [x] Add run detail drawer.
- [x] Add telemetry dashboard for cost, latency, token usage, failures, fallback rate, search freshness, queue health, and experiment guardrails.
- [x] Add artifact lineage view.
- [x] Add experiment metrics view.
- [x] Add model card view.
- [x] Add trace access log view.
- [x] Add promotion report review flow.
- [x] Add typed `adminAiApi.ts` methods.
- [x] Add loading, empty, error, unauthorized, degraded, and disabled states.
- [x] Ensure production widgets use backend APIs, not local constants.

Required tests/checks:

```bash
pytest -q tests/test_admin_ai_telemetry.py
cd dashboardv2 && npm run lint
cd dashboardv2 && npm run build
cd dashboardv2 && npx playwright test tests/admin-ai-ops.spec.ts
git diff --check
```

Acceptance criteria:

- [x] Non-admin users cannot see or navigate to AI Ops.
- [x] Admin can inspect generated answer lineage back to model call and citations.
- [x] Admin can see telemetry dashboards without database access.
- [x] Telemetry drilldowns are redacted by default.
- [x] Full trace access requires reason code and writes access log.
- [x] Raw trace export is unavailable unless explicitly enabled.
- [x] UI matches existing dashboard visual system across desktop and mobile.

Rollout:

- Ship admin-only and feature-flagged.
- Keep full payload access disabled by default.

Rollback:

- Hide AI Ops route.
- Disable full trace access.
- Backend telemetry logging can continue if stable.

## Vertical 13: Governance And Scale Artifacts

Branch: `ai/governance-scale-artifacts`

Depends on: `ai/admin-ai-ops`

Goal: package the system into an enterprise AI/ML story with scale, cost, governance, risk, and demo artifacts.

Likely files:

- `docs/interview-artifacts/cost-scaling-memo.md`
- `docs/interview-artifacts/ai-governance-artifact.md`
- `docs/interview-artifacts/risk-control-artifact.md`
- `docs/interview-artifacts/model-risk-management.md`
- `docs/interview-artifacts/demo-script.md`
- `docs/interview-artifacts/architecture-walkthrough.md`
- `tests/test_ai_retention.py`
- `tests/test_ai_reprocessing_policy.py`

Tasks:

- [x] Add cost scaling memo with model, prompt, token, and scale tradeoffs.
- [x] Add AI governance artifact covering reproducibility, auditability, model cards, approval, rollback, and retention.
- [x] Add risk-control artifact covering user isolation, admin access, trace redaction, prompt injection, and data leakage.
- [x] Add model risk management doc.
- [x] Add final demo script.
- [x] Add architecture walkthrough.
- [x] Add retention/deletion tests.
- [x] Add rollback/reprocessing policy tests.
- [x] Update progress-over-time index with generated artifacts.
- [x] Ensure claims in artifacts are supported by generated reports or clearly labeled as projections.

Required tests/checks:

```bash
pytest -q tests/test_ai_retention.py
pytest -q tests/test_ai_reprocessing_policy.py
pytest -q tests/test_report_generation.py
pytest -q tests/test_progress_index.py
git diff --check
```

Acceptance criteria:

- [x] Cost memo compares model-choice and prompt-length tradeoffs.
- [x] Governance artifact explains reproducible, auditable workflows.
- [x] Risk artifact explains controls and known limitations.
- [x] Demo script walks through product value and backend governance.
- [x] Progress index links to final artifacts.
- [x] No artifact overclaims production scale or live-user evidence.

Rollout:

- Docs/artifacts branch. Safe to merge once claims are accurate and linked to evidence.

Rollback:

- Revert inaccurate artifact claims or generated reports.

## First Branch Recommendation

Start with `ai/ci-baseline`.

Reason:

- It gives every later branch the same pass/fail standard.
- It reduces the chance of implementing broken code.
- It does not require final Copilot, Search, or Admin AI Ops contracts.
- It creates the deployment and rollback language that each later branch should follow.

Definition of done for the first branch:

- [x] CI workflow exists.
- [x] CI helper scripts exist.
- [x] Existing backend and dashboard checks run locally.
- [x] Deployment checklist has AI platform gates.
- [x] Known limitations doc exists.
- [x] Main plan and backlog agree on branch order.
