# Opportunity Radar — AI Architecture Deep Dive (Production Plan)

Date: 2026-04-21

## Why this exists

The current Opportunity Radar MVP proves end-to-end mechanics (collection → extraction → scoring → brief/action).
To get to industry-standard quality, we need a deliberate **LLMOps + agent architecture** that is:

1. Source-grounded
2. Measurable
3. Cost-aware
4. Safety-constrained
5. Continuously improvable

## Key recommendation

Do **not** jump to multi-agent orchestration immediately.

Adopt a staged architecture:

- **Stage A (now):** deterministic pipeline + single-agent enrichers + strict schema contracts
- **Stage B:** add durable graph orchestration with human-interrupt checkpoints for sensitive actions
- **Stage C:** optional specialist sub-agents (source triage, extraction, scoring explainer) only where evals show gains

This reduces complexity while preserving a path to advanced agent workflows.

## Target AI architecture

### 1) Data + evidence layer (non-LLM first)

- Keep adapters deterministic and typed.
- Preserve raw item + parsed fields + source hash.
- Require `source_url` and evidence snippets for any downstream signal.
- Add per-source trust score to scoring inputs.

### 2) Signal extraction layer (hybrid)

- Rule-first extraction for high precision events:
  - `new_role`
  - `company_visit_interest`
  - `tech_stack_signal`
- LLM extraction only for ambiguous text-heavy sources.
- Strict JSON schema with reject-on-invalid output.

### 3) Relevance scoring layer

- Keep componentized scoring (already implemented) and tune weights by feedback.
- Add score calibration job:
  - compare score deciles vs acceptance/completion outcomes
  - detect score drift per event/source type

### 4) Brief/action generation layer

- Generate from structured inputs only (signal + score + company context + profile).
- Explicitly classify each recommendation as:
  - apply
  - research
  - build
  - outreach draft
- Enforce policy gates:
  - never auto-apply
  - never auto-send
  - no LinkedIn automation

### 5) Orchestration layer (when needed)

Use durable orchestration only once we add more long-running/external-source workflows.

Candidate graph nodes:

1. collect_sources
2. normalize_dedupe
3. extract_signals
4. score_signals
5. generate_briefs
6. generate_actions
7. post_run_eval

Checkpoint boundaries at nodes 3/5 for human review in high-risk contexts.

## Should we adopt LangGraph / agent orchestration now?

**Recommendation:** yes, but in a narrow way.

- Use durable graph orchestration for reliability, retries, and resumability.
- Keep most logic deterministic and typed.
- Avoid unconstrained multi-agent loops in this phase.

Adopt only for:

- run-state persistence and resume
- interruption points (human approval on risky actions)
- explicit per-node observability

## LLMOps and model/prompt tracking (must add)

This is mandatory for quality and cost control.

### Add these entities

1. `llm_prompts`
   - `id`, `name`, `version`, `template`, `schema_version`, `active`
2. `llm_invocations`
   - model, provider, prompt_id/version, task_type, latency_ms
   - token counts (input/output/cache read/cache write)
   - estimated cost, run_id, signal_id, success/error class
3. `llm_eval_runs`
   - eval set id, prompt/model under test, judge setup, score aggregates
4. `llm_feedback_links`
   - map user action outcomes to invocation/prompt versions

### Required telemetry dimensions

- `task_type`: extraction | scoring_explainer | brief | action
- `source_type`, `event_type`
- `model_name`, `service_tier`
- `prompt_version`
- `latency_bucket`
- `cost_cents`
- `accepted_action` / `dismissed_action`

## Admin AI analytics dashboard (must add)

### Dashboard tabs

1. **Quality**
   - signal precision proxy (useful rate, wrong-company rate, too-noisy rate)
   - action acceptance/completion rate by event/source/model/prompt
2. **Cost**
   - cost/day, cost/user, cost/run, cost by task type
   - cache hit ratio and savings
3. **Latency & reliability**
   - p50/p95 latency by task/model
   - failure rate by error class/provider/model
4. **Prompt/model experiments**
   - A/B performance and guardrail violation rate
5. **Drift**
   - score calibration drift over time
   - source mix shifts and quality changes

## Evaluation program (production-grade)

### Offline evals (CI)

- Golden datasets for:
  - extraction correctness
  - evidence grounding
  - score reasonableness
  - brief usefulness rubric
- CI gates:
  - no degradation beyond threshold on key metrics

### Online evals (prod)

- Track real user outcomes:
  - useful/not useful/wrong/noisy
  - action accepted/dismissed/completed
- Weekly model/prompt leaderboard and automatic rollback criteria.

## Safety and compliance guardrails

- No claims without evidence object.
- No hiring claim from non-jobs sources.
- No autonomous platform actions.
- Domain allowlist for external collection.
- PII minimization in prompt payloads.

## Suggested near-term implementation backlog

### Sprint A (LLMOps foundation)

1. Add `llm_invocations` persistence and middleware wrapper for all LLM calls.
2. Add prompt registry tables and prompt version references.
3. Add admin API endpoints for quality/cost/latency aggregates.

### Sprint B (Eval flywheel)

1. Add offline eval harness with labeled Radar cases.
2. Add online feedback aggregation jobs.
3. Add weekly prompt/model report generation.

### Sprint C (Durable orchestration)

1. Move run pipeline to graph-based orchestrator.
2. Add retries/checkpoints/interrupts.
3. Add human approval checkpoints for high-impact actions.

## Definition of done for “great” AI layer

- >= 80% “useful” rating on top-decile signals
- >= 40% action acceptance rate on high-score recommendations
- <= 5% “wrong company/domain” feedback
- fully attributable cost/latency per model+prompt version
- one-click rollback for prompt/model regressions
