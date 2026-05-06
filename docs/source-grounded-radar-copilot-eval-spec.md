# Source-Grounded Radar, Routed Copilot, and Shared Eval Layer Spec

## Purpose

This spec defines the next implementation step for three related reliability changes:

1. Make Radar research source-first and deterministic where possible, using verified job/company sources and structured retrieval before any LLM synthesis.
2. Make Copilot route user requests to product-specific data/actions with deterministic contracts instead of treating every message as one generic retrieval answer.
3. Add a shared eval layer across Radar, Copilot, job search/source intelligence, and classifiers so production behavior can be measured, labeled, debugged, and improved safely.

This document is based on the current code implementation, not prior spec files. Prior specs may describe intended behavior, but the actual baseline here is the code paths listed below.

## Current Code Baseline

### Radar

Current modules:

- `backend/tasks/run_research_radar.py`
- `backend/services/research_radar/graph.py`
- `backend/services/research_radar/llm.py`
- `backend/services/research_radar/nodes/search.py`
- `backend/services/research_radar/nodes/fetch.py`
- `backend/services/research_radar/nodes/extract.py`
- `backend/services/research_radar/nodes/report.py`
- `backend/services/research_radar/nodes/verify.py`
- `backend/services/opportunity_radar/sources.py`
- `backend/services/opportunity_radar/signal_extractor.py`

The current Radar has two paths:

- Internal mode collects deterministic user-owned/internal signals from applications, company visits, and company tech profiles, then creates `OpportunitySignal`, `OpportunityScore`, `OpportunityBrief`, and `RecommendedAction`.
- Research/hybrid mode runs a LangGraph pipeline:

```text
load_tracker_context
  -> normalize_research_brief
  -> validate_brief
  -> plan_research_tasks
  -> run_search_tasks
  -> fetch_documents
  -> extract_evidence
  -> dedupe_and_rank_evidence
  -> build_report_diff
  -> write_report
  -> derive_report_actions
  -> verify_report
  -> persist_report
  -> emit_alerts
  -> schedule_next_run
```

The research graph currently uses LLM tasks for brief normalization, search planning, evidence extraction, report writing, and verification. It has deterministic fallbacks, but the main retrieval path still generates web search queries, searches DuckDuckGo HTML, fetches raw public pages, strips all page text, and asks an LLM to extract evidence from that page text.

Current strengths:

- Research runs, steps, source items, evidence items, reports, and feedback already persist in normalized tables.
- Steps record model name, prompt version, token/cost counts, output snapshots, and errors.
- Fetching uses `fetch_public_https`, and unsupported domains include Indeed and LinkedIn.
- Verification now forces `needs_review` when no evidence is captured.

Current gaps:

- Radar research does not use `company_job_sources`, `job_postings`, or `backend/services/job_sources/*` as the primary source of truth.
- `run_search_tasks` performs broad search before first-party source lookup.
- `fetch_documents` stores raw page text from generic pages such as careers landing pages without enough source quality metadata.
- Evidence quality is mostly LLM-produced confidence/relevance, not deterministic checks for specificity, source trust, company match, role match, and recency.
- A generic careers page can still become weak evidence for a specific opportunity unless downstream quality gates reject it.
- Verification is mostly a model task plus simple citation coverage checks, not a deterministic claim/evidence gate.

### Source Intelligence and Job Sources

Current modules:

- `backend/services/source_intelligence/url_classifier.py`
- `backend/services/source_intelligence/url_sanitizer.py`
- `backend/services/source_intelligence/link_store.py`
- `backend/services/source_intelligence/discovery.py`
- `backend/services/source_intelligence/link_crypto.py`
- `backend/services/job_sources/base.py`
- `backend/services/job_sources/registry.py`
- `backend/services/job_sources/resolver.py`
- `backend/services/job_sources/verifier.py`
- `backend/services/job_sources/greenhouse.py`
- `backend/services/job_sources/lever.py`
- `backend/services/job_sources/ashby.py`
- `backend/services/job_sources/workable.py`
- `backend/services/job_sources/smartrecruiters.py`
- `backend/services/job_sources/workday.py`
- `backend/services/job_sources/structured_data.py`
- `backend/tasks/verify_job_sources.py`
- `backend/tasks/reprocess_source_intelligence.py`

The source intelligence layer is materially implemented. The models exist for `CompanyJobSource`, `UserApplicationLink`, `SourceDiscoveryEvent`, `JobPosting`, `ApplicationSourceLink`, `SourceVerificationRun`, and `JobSearchProviderUsage`.

Current strengths:

- URL classification, sanitization, private link storage, consent-gated source discovery, and source verification tasks exist.
- Job source adapters normalize postings to `NormalizedJobPosting`.
- Job search can use `resolve_job_search` behind `JOB_SEARCH_DIRECT_SOURCES_ENABLED`.
- Direct job search already prefers verified public sources and falls back to SerpAPI with usage caps.

Current gaps:

- Radar does not consume these source records or normalized postings.
- Source matching in job search is still basic string matching against query/company/provider key.
- `JobPosting` is not indexed into Copilot or Radar retrieval as a first-class source.
- Source health and posting freshness are not shared into Radar report quality.

### Copilot

Current modules:

- `backend/routes/copilot.py`
- `backend/services/copilot/orchestrator.py`
- `backend/services/copilot/retrieval.py`
- `backend/services/copilot/guardrails.py`
- `backend/services/copilot/schemas.py`
- `backend/services/search/indexer.py`
- `dashboardv2/src/components/copilot/CopilotPanel.tsx`

Current flow:

```text
POST /api/copilot/conversations/{id}/messages
  -> validate message and budget/rate limits
  -> store user CopilotMessage
  -> retrieve SearchDocument context by keyword/vector backend
  -> call copilot_answer JSON task
  -> validate citations
  -> store assistant CopilotMessage
  -> collect thumbs feedback
```

Current strengths:

- Copilot is user-scoped and read-only.
- Prompt extraction and oversized messages are rejected.
- Answers must cite retrieved `SearchDocument` IDs when context is available.
- Feedback is persisted in `CopilotFeedback` and transformed into `AiFeedbackRewardEvent`.
- AI model calls, safety decisions, artifacts, experiments, shadow runs, model cards, and promotion reports already exist.

Current gaps:

- There is no intent router.
- There are no feature-specific Copilot tools for Radar, job search, application pipeline, Gmail diagnostics, settings, source privacy, or admin-safe source intelligence.
- The model receives the same prompt shape for every question.
- Suggested actions are sanitized but not tied to typed product actions.
- Ambiguous requests are not routed through a deterministic clarification path.
- Frontend starter prompts imply feature help, but backend cannot execute feature-specific reads beyond generic search.

### Current Eval Code

Current modules/data:

- `backend/services/evals/assistant_eval.py`
- `backend/services/evals/search_eval.py`
- `backend/services/evals/classifier_eval.py`
- `backend/services/red_team.py`
- `evals/copilot/copilot_questions_v1.jsonl`
- `evals/search/search_documents_v1.json`
- `evals/search/search_queries_v1.jsonl`
- `evals/email_classifier/email_classifier_v1.jsonl`
- `evals/red_team/*.jsonl`
- `tests/test_copilot_eval.py`
- `tests/test_search_eval.py`
- `tests/test_red_team_eval.py`

Current strengths:

- Offline deterministic evals exist for Copilot fallback groundedness, search ranking fixtures, email classification, and red-team guardrails.
- The AI telemetry schema already captures model calls, safety decisions, artifacts, experiments, feedback reward events, shadow runs, promotion reports, and model cards.
- Radar has `ResearchFeedback`; Copilot has `CopilotFeedback`.

Current gaps:

- There is no normalized eval event table that turns production behavior into reusable eval examples.
- Human labels and weak labels are not unified across surfaces.
- Eval datasets are file fixtures, not DB-backed frozen datasets derived from sanitized production examples.
- Radar report/evidence quality is not evaluated by a reusable scorer.
- Copilot route accuracy cannot be evaluated because no route output exists.
- Admin views show AI ops telemetry, but there is no labeling/review workflow for eval examples.

### Gmail and Email Classifier

Current modules:

- `backend/services/email_classifier.py`
- `backend/services/email_filter.py`
- `backend/services/email_matcher.py`
- `backend/services/email_parser.py`
- `backend/tasks/poll_gmail.py`
- Gmail sync route in `backend/main.py`
- `evals/email_classifier/email_classifier_v1.jsonl`
- `backend/services/evals/classifier_eval.py`
- `tests/test_email_classification_corpus.py`
- `tests/test_classifier_eval.py`
- `tests/test_ai_hardening.py`

Current Gmail sync architecture:

```text
Gmail API message
  -> parse headers
  -> extract raw href URLs from Gmail MIME payload
  -> parse body text from text/plain or stripped HTML
  -> skip user feedback blocklisted domains
  -> classify email
  -> skip not_relevant or quarantined messages
  -> match to Application
  -> create EmailEvent
  -> store private/source-intelligence links
  -> index EmailEvent into SearchDocument
  -> update Application status when classification maps to a status
  -> optionally create alerts/suggestions
```

The actual code has two ingestion paths:

- `backend/main.py` Gmail sync route has richer sync stats, `EmailSyncAudit`, `is_obvious_noise_email` filtering, notifications, contact checks, and source-intelligence link storage.
- `backend/tasks/poll_gmail.py` scheduled task is leaner and older. It uses feedback blocklists and source-intelligence link storage, but it does not use the full sync audit path and does not call `should_classify` before classification.

Current classifier architecture:

- `classify_email(...)` attempts the AI task `email_classifier` whenever `ai_processing` consent is enabled.
- If AI is disabled, invalid, unavailable, or unsafe, it falls back to `_fallback_classify`.
- `_fallback_classify` is phrase/domain/rule based.
- `email_filter.py` already has useful deterministic prefilter logic:
  - ATS sender domains.
  - non-job notification domains.
  - automated sender hints.
  - recruiting/job signal phrases.
  - promotional/system noise phrases.
  - `should_classify(email, company_domains)`.
- Model output is normalized and constrained to fixed categories.
- Prompt injection or unsafe inbound content is quarantined before model classification.
- User feedback can mark emails as not job-related, which builds sender-domain blocklists.
- Offline classifier eval currently compares fallback rules against a subject-only baseline on sanitized JSONL fixtures.

Current categories:

```text
job_update
interview_request
rejection
offer
action_item
conversation
not_relevant
```

Current strengths:

- The classification space is finite and well-defined.
- Strong rule features already exist.
- Tests cover fallback classification, prefilter behavior, model-payload normalization, and prompt-injection quarantine.
- User feedback and email sync audit data already provide a learning loop.

Current gaps:

- AI-first classification is too expensive for a high-volume Gmail sync path when many labels are obvious.
- `should_classify` exists but is not consistently used before model classification.
- Manual/API Gmail sync and scheduled Celery polling are not equivalent.
- The classifier does not expose deterministic decision traces such as matched phrases, sender-domain class, confidence band, or ambiguity reason.
- Category confidence is not calibrated against eval data.
- User feedback records only job-related/not-job-related, not corrected category, stage, company, or application match.
- The fallback eval dataset is small and sanitized, but not yet fed by production-derived eval events.
- Application matching is mostly company-string and ATS-source heuristics, not a scored candidate set with explainable features.

## Target Architecture

### Principle

LLMs may summarize, classify, or choose among typed routes, but product truth must come from deterministic retrieval, verified sources, structured rows, and explicit confidence gates.

```text
Product data / verified public sources
  -> sanitize and normalize
  -> deterministic retrieval and scoring
  -> optional LLM summarization or extraction over scoped evidence
  -> deterministic validation
  -> persisted trace, labels, and eval events
```

## NLP, Embeddings, Retrieval, and RAG Design

### Current Search Baseline

Current modules:

- `backend/services/search/indexer.py`
- `backend/services/search/documents.py`
- `backend/services/search/backends/postgres.py`
- `backend/services/search/backends/opensearch.py`
- `backend/services/evals/search_eval.py`
- `evals/search/search_baselines_v1.json`

Current implementation:

- `SearchDocument` indexes applications, contacts, emails, and Radar reports.
- Email search deliberately indexes summary/snippet/key sentence/classification, not raw email body.
- The default backend is portable lexical matching using SQL `LIKE` and deterministic score boosts for title/subtitle/body.
- OpenSearch is selectable by env var but currently a placeholder that reports unavailable unless configured and implemented.
- Search evals compare keyword, semantic-expansion proxy, and hybrid boost strategies.
- Vector embeddings are explicitly skipped in CI because embeddings are not provisioned.

Target implication: do not describe vector search, transformer encoders, or semantic retrieval as live production behavior until they are actually provisioned and evaluated.

### Decision Ladder

Across Gmail, Radar, Copilot, job search, and source intelligence, use the same decision ladder:

```text
1. Hard safety/privacy filters
2. Deterministic rules and structured parsers
3. Lightweight NLP features and entity extraction
4. Lexical and metadata retrieval
5. Optional embedding retrieval
6. Optional reranker / cross-encoder
7. LLM adjudication or summarization over bounded context
8. Deterministic output validation
9. Persist trace, labels, eval event, and user-visible result or review state
```

LLMs do not replace the ladder. They only operate at the adjudication/summarization step and must route back through deterministic validation.

### Threshold Pattern

Each classifier/router/retriever should expose three thresholds:

```text
accept_threshold: high-confidence result can proceed automatically
adjudicate_threshold: result is plausible but ambiguous; send to LLM/reranker/human review depending on risk
drop_threshold: result is too weak; do not make it user-visible
```

Example:

```text
score >= 0.90
  -> accept through deterministic flow

0.40 <= score < 0.90
  -> send to contextualizer/adjudicator/reranker
  -> validate returned structured result
  -> accept, review, or drop

score < 0.40
  -> do not import into main user workflow
  -> write audit/eval event only when useful
```

Risk-sensitive flows need stricter behavior:

- Private URL classification should fail closed.
- Application status updates should require high confidence.
- Radar report publishing should require source quality and citation support.
- Copilot mutations should require explicit confirmation.
- Gmail job-related recall may allow a low-confidence review queue, but not automatic status changes.

### Component Roles

#### Rules and Parsers

Use for:

- URL classification and sanitization.
- ATS/source parsing.
- Gmail obvious noise detection.
- Known lifecycle phrases such as rejection, interview, offer, assessment, and application received.
- Date, URL, domain, and status extraction.
- Provider response normalization.

Rules should emit matched feature IDs, not just labels.

#### NER and Entity Extraction

Use for:

- company names
- role titles
- people/recruiters
- dates/deadlines
- locations
- compensation fields
- job IDs/requisition IDs
- source/provider entities

Initial implementation can be deterministic/rule-based with dictionaries and regexes. Add spaCy, a local transformer NER model, or a provider model only after eval data shows rule extraction is insufficient.

NER output must be treated as candidate evidence, not truth. Company/application matching should score entities against known companies, aliases, sender domains, provider keys, and prior applications.

#### Encoders and Embeddings

Use for:

- semantic retrieval over `SearchDocument`, `JobPosting`, Radar reports, and sanitized email summaries.
- deduping near-identical job postings or report findings.
- matching role titles to role families.
- matching user queries to product routes.
- ranking Copilot/Radar context candidates.

Do not use embeddings as the only decision maker for privacy, source sharing, or status updates.

Privacy rules:

- Embeddings of Gmail-derived or user-private text are derived user data.
- Store embedding model/version and source text hash.
- Delete or invalidate embeddings when source rows are deleted or materially redacted.
- Do not embed raw private URLs, raw Gmail body, tokens, or credentials.
- Prefer embedding product-safe summaries/snippets over raw private text.

#### Retrieval Systems

Retrieval should be hybrid:

```text
metadata filters
  + lexical search
  + optional semantic embedding search
  + source/user/recency filters
  + reranking
```

Required filters before retrieval:

- user scope for private/user-owned records
- source type
- consent and privacy eligibility
- active/stale/blocked status for job sources
- date/freshness windows where relevant

#### Search Ranking

Ranking should combine inspectable features:

```text
lexical_score
semantic_score
source_trust
source_confidence
recency_score
role_match_score
company_match_score
location_match_score
user_history_match
feedback_penalty_or_boost
dedupe_penalty
privacy_eligibility
```

Every ranked result should be able to explain why it appeared.

#### Rerankers and Cross-Encoders

Use after candidate retrieval, not as the first pass.

Good uses:

- Copilot context ordering.
- Radar evidence candidate ordering.
- job search result reranking.
- email/application match disambiguation.

Cross-encoders are more expensive than embeddings but cheaper and more deterministic than free-form generation. They should output scores, not prose.

#### RAG

RAG is appropriate for Copilot and Radar, but only with strict boundaries:

```text
retrieve validated context
  -> pass small cited context bundle to model
  -> model writes summary/answer/report section
  -> validate citations and unsupported claims
  -> persist trace and eval event
```

RAG is not appropriate as a replacement for:

- URL privacy classification.
- source verification.
- application status update decisions.
- provider access-mode decisions.
- raw broad web search without source validation.

### Surface-Specific Use

Gmail classifier:

- rules/NLP first
- optional LLM adjudication only for ambiguous workflow-impacting messages
- no RAG needed for base classification
- retrieval only for matching the email to known applications/contacts/companies

Copilot:

- route classification first
- route-specific retrieval/tool execution second
- RAG summarization third
- deterministic citation/action validation last

Radar:

- verified source retrieval first
- structured extraction and source scoring second
- optional LLM summarization/report writing third
- deterministic evidence/report validation last

Job search:

- direct source retrieval first
- lexical/semantic role matching and ranking second
- broad provider fallback only when direct sources are missing/stale/blocked
- optional reranker only after normalized postings exist

Source intelligence:

- rules/parsers/sanitizers only for privacy-critical decisions
- no LLM for deciding whether a raw user URL is shareable
- embeddings may help company/source dedupe later, but only after privacy-safe canonical metadata exists

## Product Scope and Engineering Decisions

### Realistic for This Product Now

This product does not need a bank-scale AI/search platform to become materially more reliable. The realistic near-term architecture is a source-grounded application intelligence system with deterministic gates, small eval datasets, and selective LLM use.

Build now:

- Deterministic Gmail prefiltering, rule/NLP classification, confidence bands, and LLM adjudication only for ambiguous workflow-impacting messages.
- A shared Gmail sync pipeline so manual sync and scheduled polling produce the same audit, classifier, source-link, and eval-event behavior.
- Radar retrieval from `job_postings`, verified `company_job_sources`, internal applications, company visits, and other typed sources before broad web search.
- Radar quality scoring that rejects generic, stale, wrong-company, wrong-role, and uncited evidence before report generation.
- Copilot routing for a small number of high-value read-only product routes: Radar diagnostics, report questions, job search/source status, application follow-ups, Gmail sync diagnostics, source privacy, and settings help.
- Typed route/tool outputs and citation validation for Copilot instead of one generic answer prompt for every request.
- DB-backed eval events extracted from sanitized production behavior, with weak labels from feedback and admin/source state.
- Generated eval report bundles that reuse the existing `scripts/generate_ai_report.py`, `docs/interview-artifacts/generated/*`, and AI progress index pattern.
- Lexical and metadata retrieval improvements first, with semantic expansion where it is cheap and inspectable.
- Rule-based entity extraction for companies, roles, dates, locations, providers, job IDs, deadlines, and recruiters before introducing a heavier NER model.

These choices match the current scale: limited labeled data, strong structured product state, meaningful privacy constraints, and a need for fast iteration.

### Not Worth Building Yet

Defer:

- Training a custom transformer, fine-tuning an LLM, or building an RL/RLHF loop. There is not enough labeled volume, and most current failures should be fixed by routing, retrieval, rules, and eval coverage first.
- A full vector database, OpenSearch/SOLR cluster, or cross-encoder reranking service as a prerequisite. Add these only after lexical/metadata retrieval misses are measured on frozen evals.
- Embedding raw Gmail bodies, private links, candidate links, or tokenized URLs. Embeddings are derived user data and should use product-safe summaries or normalized public records only.
- Fully autonomous Copilot mutations. Copilot should remain read-only until route accuracy, confirmation UX, audit trails, and action-specific evals are mature.
- Broad web crawling as the Radar backbone. Broad search should be discovery and fallback, not the primary research source.
- Browser automation for job-source verification. Provider APIs, structured public endpoints, and employer-owned sources are enough for the first useful version.
- Enterprise model registry, feature store, streaming voice stack, Cassandra-scale data platform, or real-time retraining. Those are relevant to a Bank of America Erica-scale system, but overbuilt for Opportunity Radar today.
- Multi-agent research orchestration. The current LangGraph can be improved by replacing nodes with deterministic retrieval and quality gates.

### Product-Specific Tradeoffs

Gmail classifier:

- Optimize for high recall on job-related emails, but do not automatically update application status unless classification and application match confidence are high.
- Let obvious noise skip the LLM entirely.
- Let ambiguous human recruiter messages reach an adjudicator or review path instead of being lost by aggressive prefiltering.

Radar:

- Optimize for precision and provenance. It is better to publish "missing verified evidence" than to infer a weak opportunity from a generic careers page.
- Use LLMs for summarization after evidence has been retrieved and scored, not for deciding what evidence exists.

Copilot:

- Start with read-only route tools because they are useful and low-risk.
- Ask clarification questions instead of guessing when route confidence is low.
- Treat suggested actions as typed proposals, not model-authored state changes.

Search and NLP:

- Keep lexical search as the baseline because it is cheap, local, inspectable, and already evaluated.
- Add embeddings only for measured retrieval misses, with source type and user scope filters applied before semantic ranking.
- Use NER as candidate extraction, not truth. Company/source/application identity still needs deterministic matching and conflict handling.

Evals:

- Do not wait for a large dataset. Start with small frozen fixtures, sanitized production traces, weak labels, and targeted human review.
- Every broken route, bad report, false Gmail classification, and source privacy miss should become an eval event, label, regression case, or failure taxonomy entry.

## Radar Target Design

### New Research Source Layer

Add a source-grounded retrieval layer for Radar:

```text
backend/services/research_sources/
  __init__.py
  catalog.py
  retriever.py
  source_quality.py
  company_resolver.py
  adapters/
    job_postings.py
    company_sources.py
    public_pages.py
    clinical_trials.py
    sec_filings.py
```

The first implementation should reuse existing source intelligence and job source modules:

- `CompanyJobSource`
- `JobPosting`
- `ResearchSourceItem`
- `backend/services/job_sources/resolver.py`
- `backend/services/job_sources/role_matcher.py`
- `backend/services/source_intelligence/discovery.py`

Do not build a second job-source registry for Radar. Radar should consume `company_job_sources` and `job_postings` as shared source infrastructure.

### Radar Source Retrieval Order

Replace broad-search-first research with this order:

1. Load tracker profile and user context.
2. Resolve target companies, roles, domains, locations, seniority, and source scopes.
3. Query existing normalized `job_postings` for matching role/company/domain/location.
4. Query verified active `company_job_sources` through adapters when postings are stale or missing.
5. Collect internal signals from applications, company visits, company tech, and prior Radar reports.
6. Query approved official public sources by domain-specific source type.
7. Use broad web search only as discovery when verified sources are missing or stale.
8. Classify any broad result URLs and enqueue source verification before using them broadly.
9. Only pass scoped, quality-scored evidence candidates to an LLM.

### Radar Source Tiers

Use source tiers in every `ResearchSourceItem.raw_json` and evidence item:

```text
tier_1_verified_first_party
tier_1_official_public_database
tier_2_reputable_secondary
tier_3_discovery_candidate
tier_4_user_private_internal
```

Default handling:

- `tier_1_verified_first_party`: can support published report findings.
- `tier_1_official_public_database`: can support published report findings.
- `tier_2_reputable_secondary`: can support published findings if source is known and citation is specific.
- `tier_3_discovery_candidate`: can be used for discovery, but not as sole support for a published insight.
- `tier_4_user_private_internal`: can support user-private recommendations but must not become shared source intelligence.

### Radar Source Types

Extend the current narrow `ResearchSearchTask.task_type` and `SearchCandidate.source_type` vocabulary.

New source/evidence types:

```text
job_posting
job_board
career_category_page
company_strategy
company_press_release
investor_report
earnings_call
clinical_trial
clinical_pipeline
regulatory_filing
engineering_blog
technical_docs
product_launch
partnership
funding_or_mna
internal_application
internal_company_visit
internal_company_tech
```

The existing `role_openings`, `company_hiring_signal`, `team_growth_signal`, `tech_stack_signal`, and `company_strategy_signal` can remain report-level evidence categories, but source type should represent where the data came from.

### Domain-Specific Retrieval Plans

Replace LLM-generated broad search tasks with deterministic retrieval plans plus optional LLM augmentation.

For biotech/pharma trackers:

- Pull matching `job_postings` for R&D, data science, bioinformatics, computational biology, AI/ML, regulatory, and clinical operations.
- Search official company pipeline pages, press releases, investor materials, and ClinicalTrials.gov.
- Extract structured signals:
  - therapeutic area
  - modality/platform
  - phase
  - trial status
  - hiring team/function
  - location
  - date

For data/ML/software trackers:

- Pull matching `job_postings`.
- Search official engineering blogs, docs, product launch pages, and company career categories.
- Extract structured signals:
  - team/function
  - stack/technology
  - product area
  - seniority
  - location
  - date

For GTM/business trackers:

- Pull matching `job_postings`.
- Search official press releases, product launches, partnerships, customer pages, and role postings.
- Extract structured signals:
  - segment
  - region
  - product line
  - growth signal
  - hiring function
  - date

### Evidence Quality Contract

Add:

```text
backend/services/research_radar/evidence_quality.py
```

Every evidence candidate must receive deterministic quality fields before report generation:

```json
{
  "source_trust": 0.0,
  "specificity_score": 0.0,
  "company_match_score": 0.0,
  "role_match_score": 0.0,
  "recency_score": 0.0,
  "citation_span": "string or null",
  "claim_type": "job_opening | company_signal | strategy | technical_signal | user_private_signal",
  "quality_flags": []
}
```

Required quality gates:

- A generic careers landing page cannot produce a high-confidence role-specific finding by itself.
- A finding must have a specific citation span or structured field value.
- A company-specific claim must match the target company by verified source, company domain, posting company, or repeated public evidence.
- A role-specific claim must match a role family or explicit job posting title.
- If evidence is discovery-only, report status must be `needs_review` unless supported by another verified source.
- If all evidence is generic, the report should publish a degraded/missing-data result rather than fabricated insight.

### Radar Graph Changes

Keep the LangGraph structure, but change the middle of the graph:

Current:

```text
plan_research_tasks -> run_search_tasks -> fetch_documents -> extract_evidence
```

Target:

```text
plan_source_retrieval
  -> retrieve_verified_sources
  -> fetch_or_refresh_sources
  -> extract_structured_evidence
  -> score_evidence_quality
  -> optional_llm_evidence_summarization
```

Suggested module changes:

- Replace or wrap `nodes/plan.py` with `nodes/plan_sources.py`.
- Replace `nodes/search.py` broad search as the default with `research_sources/retriever.py`.
- Keep `nodes/fetch.py` for safe fetch, but make it adapter-driven and source-type aware.
- Change `nodes/extract.py` so deterministic extractors run before `research_evidence_extractor`.
- Change `nodes/report.py` so report writing receives only quality-gated evidence.
- Change `nodes/verify.py` so deterministic validation can force `needs_review` even if the LLM verifier says ready.

### Radar Report Contract

Every report finding should be structured as:

```json
{
  "company": "string",
  "finding": "string",
  "why_it_matters": "string",
  "evidence": [
    {
      "source_item_id": "uuid",
      "source_type": "job_posting",
      "source_tier": "tier_1_verified_first_party",
      "citation_span": "short exact span or structured field",
      "url": "safe public URL or apptrail internal URL",
      "observed_at": "timestamp"
    }
  ],
  "confidence": 0.0,
  "next_action": "string",
  "missing_data": []
}
```

If evidence is insufficient, the report should say what is missing:

```text
No specific verified role opening was found for this company and role family. Radar checked verified job postings and official career sources, then left this item in review instead of inferring a fit from a generic careers page.
```

## Copilot Target Design

### Product Router

Add:

```text
backend/services/copilot/router.py
backend/services/copilot/routes/
  __init__.py
  base.py
  radar.py
  job_search.py
  applications.py
  gmail.py
  source_privacy.py
  settings.py
  general.py
backend/services/copilot/clarify.py
backend/services/copilot/action_registry.py
```

The existing `answer_copilot_question` should become orchestration:

```text
validate user message
  -> classify route intent
  -> if ambiguous, ask a typed clarification question
  -> retrieve route-specific data
  -> optionally call model to summarize retrieved route result
  -> validate citations/actions
  -> store message with route metadata
```

### Route Intent Schema

Add a typed route result:

```python
@dataclass(frozen=True)
class CopilotRoute:
    intent: str
    confidence: float
    entities: dict
    needs_clarification: bool
    clarification_question: str | None
    allowed_tools: list[str]
    safety_flags: list[str]
```

Supported intents:

```text
radar_run_diagnostics
radar_report_question
radar_tracker_create_or_update
opportunity_signal_prioritization
job_search
job_source_question
application_pipeline_question
application_create_or_update
follow_up_recommendation
gmail_sync_diagnostics
source_privacy_settings
settings_navigation
general_career_advice
unknown
```

### Router Policy

Use deterministic rules first, then an LLM classifier only for ambiguous language.

Default routing thresholds:

```text
confidence >= 0.85: execute route
0.55 <= confidence < 0.85: ask clarification
confidence < 0.55: general/read-only answer or unknown fallback
```

These thresholds must be calibrated from evals. Do not trust model-reported confidence directly. Store raw confidence, calibrated confidence, and route decision in message metadata.

### Route Tool Contracts

Every route should return a typed payload:

```python
@dataclass(frozen=True)
class CopilotRouteResult:
    answer_facts: list[dict]
    citations: list[CopilotCitation]
    suggested_actions: list[dict]
    tool_trace: dict
    requires_confirmation: bool
```

Route examples:

- `radar_run_diagnostics`: read latest `ResearchRun`, `ResearchRunStep`, report status, failed step, source count, evidence count, and next suggested fix.
- `radar_report_question`: retrieve specific `ResearchReport`, `ResearchEvidenceItem`, and `ResearchSourceItem` rows before summarization.
- `radar_tracker_create_or_update`: collect missing tracker fields and return a proposed mutation requiring confirmation.
- `job_search`: call direct source resolver and explain `provider_status` and `source_summary`.
- `job_source_question`: answer from `CompanyJobSource`, `SourceVerificationRun`, and `JobPosting` rows.
- `application_pipeline_question`: aggregate `Application` rows, deadlines, stages, follow-up timing, and related emails.
- `gmail_sync_diagnostics`: read `EmailSyncAudit`, connection state, recent sync failures, and safe next steps.
- `source_privacy_settings`: explain private links and consent using redacted `UserApplicationLink` metadata only.

### Copilot Action Safety

Copilot remains read-only by default.

Mutations require explicit user confirmation and a typed action:

```json
{
  "action_type": "radar_tracker_create",
  "requires_confirmation": true,
  "read_only": false,
  "payload_schema": "radar_tracker_create_v1",
  "payload": {}
}
```

Never let model text directly mutate product state. The model can propose a structured action; the backend validates the schema, permissions, consent, and route-specific safety policy.

### Copilot Persistence Changes

Extend `CopilotMessage.metadata_json`:

```json
{
  "mode": "route_model | route_deterministic | search_fallback",
  "intent": "radar_run_diagnostics",
  "route_confidence": 0.91,
  "calibrated_confidence": 0.87,
  "needs_clarification": false,
  "tools_used": ["radar.latest_run"],
  "result_quality": {
    "citation_coverage": 1.0,
    "unsupported_claim_count": 0
  }
}
```

The route metadata becomes a first-class eval source.

## Gmail Classifier Target Design

### Recommendation

For Gmail classification, a deterministic/NLP-first pipeline is better than an LLM-first pipeline.

This is not an open-ended reasoning task. It is mostly high-volume finite-label classification with strong lexical, sender-domain, ATS, URL, and user-history signals. Traditional rules, lightweight NLP features, and eventually a calibrated classifier should be the primary path. The LLM should be reserved for ambiguous messages or for extracting short summaries/company/action fields when cheaper logic is not confident.

Target policy:

```text
obvious noise -> deterministic skip
obvious ATS/application/interview/rejection/offer/action -> deterministic classify
ambiguous human recruiter conversation -> lightweight NLP score
low confidence or conflicting signals -> optional LLM adjudicator if consent allows
unsafe prompt-injection content -> quarantine/no model
```

### Target Pipeline

Keep `classify_email(...)` as the compatibility entry point, but refactor the internals behind a staged classifier:

```text
backend/services/email_intelligence/
  __init__.py
  pipeline.py
  prefilter.py
  features.py
  rules.py
  classifier.py
  adjudicator.py
  postprocess.py
  eval_events.py
```

Target flow:

```text
EmailCandidate
  -> safety preflight and prompt-injection scan
  -> sender/domain/user-feedback prefilter
  -> URL/source-intelligence feature extraction
  -> deterministic rule classifier
  -> lightweight NLP classifier or scorer
  -> ambiguity/conflict gate
  -> LLM adjudicator only when needed and consented
  -> normalized EmailClassificationResult
  -> application-match candidate scoring
  -> EmailEvent / Application / SearchDocument / eval event writes
```

### Email Candidate Contract

```python
@dataclass(frozen=True)
class EmailCandidate:
    gmail_message_id: str
    thread_id: str | None
    sender_name: str
    sender_email: str
    sender_domain: str | None
    subject: str
    body_text: str
    snippet: str | None
    raw_candidate_urls: list[str]
    received_at: datetime
    user_company_domains: set[str]
    feedback_blocked_domains: set[str]
```

### Classification Result Contract

```python
@dataclass(frozen=True)
class EmailClassificationResult:
    classification: str
    confidence: float
    confidence_band: str
    company_name: str | None
    sender_role: str
    key_sentence: str | None
    summary: str | None
    action_needed: bool
    is_automated: bool
    model_used: bool
    decision_path: str
    matched_features: list[str]
    ambiguity_reasons: list[str]
    safety_status: str | None
```

`decision_path` values:

```text
blocked_domain
obvious_noise
deterministic_rule
lightweight_nlp
llm_adjudicator
quarantined
fallback
```

### Feature Signals

Use explicit, inspectable features:

```text
sender_domain_is_ats
sender_domain_blocklisted_by_user
sender_domain_matches_active_application
sender_local_part_automated
sender_looks_human
contains_public_job_url
contains_private_candidate_url
contains_scheduler_url
contains_rejection_phrase
contains_interview_phrase
contains_offer_phrase
contains_action_required_phrase
contains_application_update_phrase
mentions_known_application_company
mentions_known_role_title
has_calendar_or_scheduling_language
has_assessment_language
has_recruiter_sender_signal
has_noise_or_marketing_signal
```

### LLM Use Criteria

Invoke the LLM only when all are true:

- `ai_processing` consent is enabled.
- The message passed safety preflight.
- The deterministic/NLP classifier is below the high-confidence threshold or has conflicting high-value signals.
- The result would affect user-visible workflow, such as creating an application suggestion, updating status, creating a network contact, or alerting the user.

Example cases where LLM adjudication is useful:

- A human recruiter follow-up with no obvious keywords.
- A nuanced rejection/hold message where status is not clear.
- A message that contains both scheduling and assessment language.
- Company extraction from a recruiter agency email.

Example cases where LLM should not be used:

- GitHub/Vercel/Railway/system notifications.
- Known user-blocklisted sender domains.
- Obvious ATS application confirmations.
- Obvious rejection/offer/interview phrases.
- Prompt-injection or secret-extraction content.

### Confidence Thresholds

Initial thresholds:

```text
>= 0.90: deterministic high confidence, no LLM
0.65 - 0.89: lightweight NLP or rules decide; LLM only for workflow-impacting ambiguity
0.40 - 0.64: LLM adjudicator if consented, otherwise low-confidence fallback
< 0.40: skip or mark not_relevant unless known ATS/company signal exists
```

These thresholds must be calibrated using eval labels, not guessed permanently.

### Application Matching Target

Replace the current single-pass heuristic with scored candidates:

```text
backend/services/email_intelligence/application_matcher.py
```

Candidate features:

```text
company_name_exact
company_name_alias
company_domain_match
job_url_provider_match
source_intelligence_provider_key_match
role_title_match
thread_history_match
sender_email_prior_match
recent_application_boost
archived_application_penalty
```

Return:

```python
@dataclass(frozen=True)
class ApplicationMatchResult:
    application_id: UUID | None
    confidence: float
    candidate_count: int
    matched_features: list[str]
    ambiguity_reasons: list[str]
```

If match confidence is low, store the email but avoid automatic status updates.

### Sync Path Unification

Unify the API Gmail sync route and `backend/tasks/poll_gmail.py` around one service:

```text
backend/services/gmail_sync/pipeline.py
```

Both paths should use the same:

- feedback blocklist
- `should_classify` prefilter
- `EmailSyncAudit`
- source-intelligence link extraction/storage
- classifier result contract
- application match scoring
- status update rules
- eval event capture

### Email Classifier Eval Additions

Add DB-backed eval events for:

```text
email_prefilter
email_classification
email_application_match
email_status_update
email_source_link_extraction
```

Additional labels:

```text
correct_job_related
false_positive_job_related
false_negative_job_related
correct_category
wrong_category
correct_application_match
wrong_application_match
ambiguous_application_match
safe_skip
unsafe_model_call_prevented
```

Metrics:

```text
job_related_precision
job_related_recall
category_accuracy
stage_accuracy
application_match_precision
application_match_recall
false_positive_noise_rate
false_negative_job_email_rate
llm_call_rate
llm_cost_per_1000_emails
quarantine_rate
prefilter_skip_rate
user_feedback_reversal_rate
```

Acceptance:

- Obvious noise is skipped before any LLM call.
- Known ATS/application confirmations classify without LLM.
- Human recruiter conversations are not lost just because they lack ATS domains.
- LLM call rate is measurable and can be capped.
- User feedback creates weak labels and updates prefilter/blocklist behavior.
- API sync and scheduled Gmail polling produce equivalent audit/event behavior.

## Shared Eval Layer

### Goal

Existing production rows already contain valuable data. The missing piece is a normalized eval layer that turns those rows into sanitized, labelable, replayable examples.

Current raw data sources:

- `AiModelCall`
- `AiSafetyDecision`
- `AiArtifact`
- `CopilotConversation`
- `CopilotMessage`
- `CopilotFeedback`
- `AiFeedbackRewardEvent`
- `ResearchRun`
- `ResearchRunStep`
- `ResearchReport`
- `ResearchReportSection`
- `ResearchEvidenceItem`
- `ResearchSourceItem`
- `ResearchFeedback`
- `SearchDocument`
- `CompanyJobSource`
- `JobPosting`
- `SourceVerificationRun`
- source intelligence private-link metadata after redaction

### Eval Artifact Pipeline

The eval layer should produce artifacts, not just dashboard numbers. This repo already has the right foundation:

- file fixtures under `evals/`
- failure taxonomy docs such as `evals/copilot/failure-taxonomy.md`
- generated report bundles under `docs/interview-artifacts/generated/`
- report generation through `scripts/generate_ai_report.py`
- index regeneration through `scripts/regenerate_ai_progress_index.py`
- persistent artifact lineage through `AiArtifact`
- promotion summaries through `AiPromotionReport`

Target pipeline:

```text
production behavior
  -> surface-specific redactor
  -> ai_eval_events
  -> weak labels from feedback and product outcomes
  -> human/admin labels for high-value cases
  -> frozen dataset items
  -> eval runner compares baseline vs candidate
  -> metrics, failure taxonomy, case results
  -> immutable generated report bundle
  -> promotion decision or RCA backlog
  -> regression fixture for important failures
```

Every eval run should create or update these artifacts:

```text
ai_eval_runs row
ai_eval_case_results rows
metrics.json
failure_summary.json
case_results.jsonl
report.md
metadata.json
source_input.json
optional confusion_matrix.json
optional rca_backlog.md
optional model_card_update.md
```

Report bundles should follow the existing generated artifact convention:

```text
docs/interview-artifacts/generated/
  YYYY-MM-DD_<report-type>_<dataset-version>_<model-or-variant>_<prompt-or-code-version>/
    report.md
    metadata.json
    metrics.json
    token_breakdown.json
    cost_breakdown.json
    latency_metrics.json
    summary_payload.json
    source_input.json
    failure_summary.json
    case_results.jsonl
```

`report.md` is the human artifact for interview/demo/admin review. `metrics.json` and `ai_eval_runs.summary_metrics` are the machine-readable gates. `case_results.jsonl` and `failure_summary.json` are the RCA inputs.

RCA workflow:

```text
failed eval case
  -> assign failure type
  -> determine root cause
  -> choose fix type
  -> add regression fixture or label
  -> link to code/prompt/config change
  -> rerun dataset
```

Root cause categories:

```text
retrieval_miss
wrong_route
bad_threshold
missing_rule
bad_prompt
schema_failure
source_quality_gap
privacy_redaction_gap
label_error
stale_data
product_state_gap
```

Fix categories:

```text
rule_change
threshold_change
retrieval_filter_change
source_quality_gate_change
prompt_change
router_training_data
human_label_needed
product_data_model_change
privacy_sanitizer_change
defer_no_fix
```

This makes evals explainable: a bad Copilot answer is not just "the LLM was wrong"; it becomes a route miss, retrieval miss, citation validation miss, prompt issue, stale data issue, or missing product-state issue.

### New Tables

Create a migration for:

#### `ai_eval_events`

Normalized sanitized examples extracted from production behavior.

```text
id uuid pk
surface text not null
task_name text not null
event_type text not null
source_table text not null
source_id uuid nullable
user_id uuid nullable
event_hash text not null
input_snapshot json not null
output_snapshot json nullable
context_snapshot json nullable
redaction_summary json nullable
policy_snapshot json nullable
model_call_id uuid nullable fk ai_model_calls.id on delete set null
created_from text not null
occurred_at timestamptz not null
created_at timestamptz not null
```

Rules:

- `input_snapshot`, `output_snapshot`, and `context_snapshot` must be redacted.
- No raw Gmail bodies.
- No raw URLs with query strings.
- No private application links.
- No access tokens, cookies, API keys, candidate IDs, or application IDs.
- `event_hash` is a keyed HMAC over the normalized redacted event.

#### `ai_eval_labels`

Weak and human labels for eval events.

```text
id uuid pk
event_id uuid not null fk ai_eval_events.id on delete cascade
label_schema text not null
label_value text not null
label_payload json nullable
label_source text not null
labeler_user_id uuid nullable fk users.id on delete set null
confidence float not null default 1
notes text nullable
created_at timestamptz not null
updated_at timestamptz not null
```

`label_source` values:

```text
weak_signal
human_admin
human_support
user_feedback
automated_scorer
gold_import
```

#### `ai_eval_datasets`

Frozen datasets for regression and promotion gates.

```text
id uuid pk
dataset_key text not null unique
surface text not null
task_name text nullable
version text not null
description text nullable
selection_query json not null
label_schema text not null
privacy_review_status text not null default 'pending'
created_by_user_id uuid nullable fk users.id on delete set null
frozen_at timestamptz nullable
created_at timestamptz not null
```

#### `ai_eval_dataset_items`

Membership for frozen datasets.

```text
id uuid pk
dataset_id uuid not null fk ai_eval_datasets.id on delete cascade
event_id uuid not null fk ai_eval_events.id on delete cascade
split text not null
weight float not null default 1
created_at timestamptz not null
```

`split` values:

```text
train
dev
test
holdout
red_team
```

#### `ai_eval_runs`

Executed eval runs.

```text
id uuid pk
dataset_id uuid not null fk ai_eval_datasets.id on delete cascade
surface text not null
task_name text not null
variant text not null
model text nullable
prompt_version text nullable
code_version text nullable
status text not null
started_at timestamptz not null
finished_at timestamptz nullable
summary_metrics json nullable
failure_summary json nullable
created_at timestamptz not null
```

#### `ai_eval_case_results`

Per-case eval results.

```text
id uuid pk
eval_run_id uuid not null fk ai_eval_runs.id on delete cascade
event_id uuid not null fk ai_eval_events.id on delete cascade
status text not null
scores json not null
failure_types json nullable
output_snapshot json nullable
created_at timestamptz not null
```

### Label Schemas

#### Radar Evidence

```text
specific
generic
wrong_company
wrong_role
unsupported
stale
privacy_risk
useful
not_useful
needs_human_review
```

#### Radar Report

```text
actionable
too_generic
unsupported_claims
missing_citations
wrong_focus
missing_data_clearly_stated
missing_data_hidden
needs_more_evidence
```

#### Copilot Router

```text
correct_route
wrong_route
should_clarify
clarification_unneeded
multi_intent_missed
unsafe_action
good_refusal
bad_refusal
```

#### Copilot Answer

```text
grounded
unsupported
missing_citation
helpful
not_helpful
wrong_entity
wrong_time_window
privacy_risk
```

#### Job Search and Source Intelligence

```text
relevant
weak_match
wrong_role
wrong_company
stale
duplicate
unsupported_source
safe_public
private_user_only
tracking_redirect
tokenized
needs_review
wrong_provider
```

### Weak Labels

Generate weak labels from existing behavior:

- Copilot thumbs up/down.
- Research thumbs up/down.
- User saves, opens, clicks, archives, deletes, or ignores suggested actions.
- User reruns a Radar tracker shortly after a report.
- User asks Copilot a correction such as "that's wrong" or "not that company".
- Radar report status is `needs_review`.
- Research extraction failed for a source.
- Source verification failed, blocked, or became stale.
- Job search result saved to pipeline.
- Job search result dismissed or never clicked.
- Admin source block/approve events.

Weak labels are not gold. They seed review queues and aggregate analysis.

### Human Labeling UI

Add admin labeling under AI Ops:

```text
GET /api/admin/evals/events
GET /api/admin/evals/events/{event_id}
POST /api/admin/evals/events/{event_id}/labels
GET /api/admin/evals/datasets
POST /api/admin/evals/datasets
POST /api/admin/evals/datasets/{dataset_id}/freeze
GET /api/admin/evals/runs
POST /api/admin/evals/runs
```

The UI must show:

- sanitized input
- sanitized output
- citations/source metadata
- route/tool trace
- model and prompt version
- existing weak labels
- human label controls
- privacy redaction summary

The UI must not show:

- raw Gmail body
- raw tokenized URLs
- query strings from private links
- encrypted private link payloads
- API keys or provider credentials

### Eval Metrics

Radar metrics:

```text
evidence_specificity_precision
generic_evidence_rate
wrong_company_rate
wrong_role_rate
citation_coverage
unsupported_claim_rate
needs_review_rate
published_without_tier1_or_tier2_evidence_rate
report_actionability_rate
```

Copilot metrics:

```text
route_accuracy
clarification_precision
clarification_recall
answer_groundedness
citation_coverage
unsupported_claim_rate
safe_action_rate
user_feedback_reward_rate
```

Job/source metrics:

```text
direct_source_coverage
broad_fallback_rate
source_verification_success_rate
stale_source_rate
job_result_relevance
duplicate_rate
private_url_false_public_rate
```

Operational metrics:

```text
cost_per_successful_answer
latency_p50_p95
model_failure_rate
safety_quarantine_rate
fallback_rate
dataset_label_coverage
```

### Eval Runners

Add:

```text
backend/services/evals/event_builder.py
backend/services/evals/labelers.py
backend/services/evals/radar_eval.py
backend/services/evals/copilot_router_eval.py
backend/services/evals/copilot_answer_eval.py
backend/services/evals/source_eval.py
backend/services/evals/artifact_writer.py
backend/tasks/build_ai_eval_events.py
scripts/run_ai_eval_suite.py
```

Existing file-fixture evals remain valid, but new DB-backed evals should become the promotion gate.

The first version of `artifact_writer.py` should wrap the existing report writer instead of creating a second report system. It should translate an `ai_eval_runs` result into the structured input expected by `scripts/generate_ai_report.py`, then record the generated path in `AiArtifact`.

## Privacy and Governance

The eval layer must use the same privacy posture as source intelligence:

- Sanitize before event creation.
- Store event hashes with keyed HMAC, not plain SHA-256.
- Do not store raw private links.
- Do not store Gmail-derived raw body text.
- Respect account deletion and anonymize `user_id` where required.
- Gate admin review behind admin permission and log access in `AiAdminAccessLog`.
- Apply privacy thresholds before aggregate reporting.
- Keep labels and eval events scoped to visible user-facing product improvement.

Fine-tuning or model training is not allowed until:

- A frozen gold dataset exists.
- Privacy review approves the dataset.
- Retrieval/rules/prompt improvements have been tried first.
- Evaluation shows a persistent model behavior gap.
- A rollback plan and model card update are approved.

## Rollout Plan

### Phase 0: Baseline and Instrumentation

- Add `ai_eval_events`, `ai_eval_labels`, `ai_eval_datasets`, `ai_eval_dataset_items`, `ai_eval_runs`, and `ai_eval_case_results`.
- Build sanitizers for Copilot, Radar, source intelligence, and job search events.
- Backfill eval events from recent `CopilotMessage`, `ResearchReport`, `ResearchEvidenceItem`, `ResearchRunStep`, `AiModelCall`, `CopilotFeedback`, `ResearchFeedback`, `EmailEvent`, `EmailFeedback`, and `EmailSyncAudit`.
- Add weak labels from current feedback and status fields.
- Add artifact generation from `ai_eval_runs` using the existing generated report bundle format.
- Add `failure_summary.json`, `case_results.jsonl`, and RCA fields to generated eval reports.

Acceptance:

- Production behavior can be sampled into eval events with no raw private data.
- At least Copilot answer, Radar evidence, Radar report, Gmail classifier, job search, and source privacy event types exist.
- Admin can inspect sanitized events and add labels.
- Each eval run can produce a machine-readable metrics file, human-readable report, failure summary, and case-result artifact.
- Generated artifacts can be linked from `docs/interview-artifacts/ai-system-progress-over-time.md`.

### Phase 1A: Gmail Classifier Hybrid Pipeline

- Unify API Gmail sync and scheduled `poll_gmail` around one sync pipeline.
- Use feedback blocklists and `should_classify` before model classification.
- Add deterministic decision traces and confidence bands to classifier results.
- Add lightweight NLP/rule scoring before the LLM adjudicator.
- Add scored application matching and avoid automatic status changes on low-confidence matches.
- Capture DB-backed eval events for prefilter, classification, application match, and status update decisions.

Acceptance:

- Obvious noise and user-blocklisted domains never call the LLM.
- Obvious ATS and phrase-matched lifecycle updates classify without the LLM.
- Ambiguous human recruiter messages are retained for classification instead of skipped as noise.
- API sync and scheduled polling produce equivalent `EmailSyncAudit` and eval-event behavior.
- LLM call rate, false positive rate, false negative rate, and user feedback reversal rate are visible.

### Phase 1: Radar Source-Grounded Retrieval

- Add `research_sources` package.
- Add Radar retrieval from `job_postings` and verified `company_job_sources`.
- Add `source_tier`, `source_trust`, `specificity_score`, company match, role match, and recency fields to source/evidence payloads.
- Add deterministic extractors for normalized job postings and internal signals.
- Use broad web search only when verified sources are missing or stale.

Acceptance:

- Radar can produce a report from verified job postings without DuckDuckGo.
- Generic careers pages are downgraded and cannot be the sole high-confidence evidence for specific role/company findings.
- Reports with only generic/discovery evidence go to `needs_review`.

### Phase 2: Radar Quality Gate and Report Contract

- Add `evidence_quality.py`.
- Add deterministic verification before and after model report writing.
- Require every report finding to cite specific evidence.
- Add missing-data sections when evidence is insufficient.
- Add Radar eval runner for evidence and report quality.

Acceptance:

- Unsupported claims and missing citations are caught without relying only on an LLM verifier.
- Report status reflects evidence quality.
- Radar evals include fixtures for generic careers pages, wrong company, wrong role, stale evidence, and good verified-source findings.

### Phase 3: Copilot Router

- Add route registry, intent classifier, clarification flow, and route result contracts.
- Implement read-only routes for Radar diagnostics, Radar report questions, job search/source status, applications, Gmail sync diagnostics, source privacy, and settings navigation.
- Store route metadata on assistant messages.
- Keep generic retrieval answer as fallback, not default.

Acceptance:

- "Why did this Radar run fail?" reads `ResearchRunStep` and cites the failed step.
- "Find data analyst jobs at X" calls job search/source resolver and explains source/fallback state.
- "Which applications need follow-up?" aggregates application data rather than generic text search alone.
- Ambiguous requests ask one concise clarification question.

### Phase 4: Eval Datasets and Gates

- Freeze initial DB-backed datasets:
  - `radar_evidence_quality_v1`
  - `radar_report_quality_v1`
  - `copilot_router_v1`
  - `copilot_answer_grounding_v1`
  - `source_privacy_v1`
  - `job_search_relevance_v1`
- Add CI or scheduled eval suite.
- Add model/prompt promotion gates using `AiPromotionReport`.

Acceptance:

- Any prompt/model/router change can be compared against frozen datasets.
- Promotion reports include route accuracy, groundedness, unsupported claim rate, cost, latency, and safety metrics.
- Release can be blocked when core eval metrics regress.

### Phase 5: Optional Learned Components

Only after Phases 0-4:

- Train/calibrate a lightweight route classifier if enough labels exist.
- Train/calibrate a source/evidence reranker if deterministic scoring is insufficient.
- Consider fine-tuning only for narrow classification/extraction tasks with approved datasets.

Acceptance:

- Learned components beat deterministic baselines on holdout data.
- Privacy and model card approvals are complete.
- Rollback is documented and tested.

## Implementation Notes

- Do not remove the existing Research Radar graph immediately. Evolve it by replacing retrieval/extraction nodes behind feature flags.
- Prefer using `job_sources` and `source_intelligence` modules instead of creating parallel provider logic.
- Keep Copilot mutation paths disabled until route evals and confirmation UX exist.
- Existing offline eval files should stay in CI as smoke/regression fixtures.
- DB-backed eval events should become the long-term source for coverage and labeling.
- Radar and Copilot should share source/evidence quality helpers where possible.

## Feature Flags

Add or reuse:

```text
RADAR_SOURCE_GROUNDED_RETRIEVAL_ENABLED=false
RADAR_BROAD_SEARCH_DISCOVERY_ONLY=true
RADAR_EVIDENCE_QUALITY_GATE_ENABLED=true
COPILOT_ROUTER_ENABLED=false
COPILOT_MUTATION_ACTIONS_ENABLED=false
EMAIL_CLASSIFIER_HYBRID_PIPELINE_ENABLED=false
EMAIL_CLASSIFIER_LLM_ADJUDICATOR_ENABLED=true
EMAIL_CLASSIFIER_TRACE_ENABLED=true
SEARCH_VECTOR_RETRIEVAL_ENABLED=false
SEARCH_RERANKER_ENABLED=false
NLP_ENTITY_EXTRACTOR_ENABLED=false
AI_EVAL_EVENT_CAPTURE_ENABLED=true
AI_EVAL_HUMAN_LABELING_ENABLED=false
AI_EVAL_PROMOTION_GATE_ENABLED=false
AI_EVAL_ARTIFACT_GENERATION_ENABLED=true
```

## Acceptance Checklist

- [ ] Radar uses `job_postings` and verified `company_job_sources` before broad web search.
- [ ] Radar does not publish high-confidence specific findings from generic careers pages alone.
- [ ] Radar evidence has source tier, source trust, specificity, company match, role match, and recency scores.
- [ ] Radar reports clearly state missing data instead of filling gaps with generic claims.
- [ ] Copilot classifies route intent before answering.
- [ ] Copilot routes feature questions to feature-specific read tools.
- [ ] Copilot asks clarification questions for ambiguous requests.
- [ ] Copilot stores route/tool metadata on assistant messages.
- [ ] Gmail classification uses prefilter/rules/NLP before LLM adjudication.
- [ ] Gmail sync API and scheduled polling share one classifier/sync pipeline.
- [ ] Email classifier decisions expose decision path, matched features, confidence band, and ambiguity reasons.
- [ ] Low-confidence application matches do not automatically update application status.
- [ ] Vector retrieval and rerankers are introduced only behind flags and measured against lexical baselines.
- [ ] Embeddings are generated only from privacy-safe text with model/version/source-hash lineage.
- [ ] RAG outputs are validated for citations and unsupported claims before they become user-visible.
- [ ] Eval event tables exist and are populated from sanitized production rows.
- [ ] Weak labels are generated from current feedback and behavior.
- [ ] Human labels can be added through admin UI without exposing private raw data.
- [ ] Frozen datasets exist for Radar evidence, Radar report quality, Copilot routing, Copilot grounding, source privacy, and job search relevance.
- [ ] Model/prompt/router changes can run against frozen evals before promotion.
- [ ] Eval runs produce `metrics.json`, `failure_summary.json`, `case_results.jsonl`, `report.md`, and DB `ai_eval_runs`/`ai_eval_case_results` records.
- [ ] Eval artifacts are linked through `AiArtifact` and can be indexed in `docs/interview-artifacts/ai-system-progress-over-time.md`.
- [ ] Failed eval cases are assigned root cause and fix categories before being closed.
- [ ] Advanced ML additions such as embeddings, rerankers, learned routers, or fine-tuning are adopted only after they beat deterministic/lexical baselines on frozen evals.
- [ ] No raw Gmail bodies, private URLs, credentials, candidate IDs, or tokenized links appear in eval tables, logs, admin views, or prompt artifacts.
