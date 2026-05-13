# Technical Overview

AppTrail is not a single-screen job tracker with a few AI calls bolted on. It is a connected job-search system with three entry points:

1. A React dashboard where the user runs the search day to day.
2. A Chrome extension that captures opportunities while the user is already browsing.
3. A FastAPI backend with workers for sync, enrichment, automation, and storage.

The codebase is large enough to show real system design, but still small enough that the tradeoffs are visible. At the time of writing, it includes:

- 177 backend route declarations
- 68 SQLAlchemy models
- 52 Alembic migrations
- 139 backend service modules
- 10 Celery task modules with 13 task declarations
- 118 backend/product test files

Those counts are not the point by themselves. The point is that AppTrail has the shape of a real product: browser capture, dashboard workflows, background jobs, user-scoped data, Gmail sync, AI governance, deployment docs, and tests around product behavior.

## System Shape

The product is split by responsibility:

```text
Chrome extension
  -> capture, page detection, visit tracking, submission detection

FastAPI API
  -> auth, application CRUD, Gmail sync triggers, resume and search endpoints,
     contact enrichment, reporting, Radar endpoints

Celery worker + beat
  -> scheduled jobs, Gmail polling, follow-up checks, recurring maintenance

PostgreSQL
  -> product data, user state, research runs, audit history

Redis
  -> Celery broker, token blacklist, auth code exchange, rate-limit backing

React dashboard
  -> working surface for the search
```

That separation matters. Gmail polling, job parsing, enrichment, and recurring checks do not belong in the browser. The extension needs a narrow API contract. The dashboard needs to stay responsive. The backend needs to own the side effects.

## Backend

The backend uses FastAPI with async SQLAlchemy. That fits the workload: lots of external I/O, Gmail sync, public-source fetching, enrichment calls, and a large endpoint surface that benefits from typed request and response models.

The application record is the center of the data model. Around it are the records that make a job search operational:

- email events and classifier traces
- contacts and contact decisions
- alerts and action candidates
- interviews and notes
- resume drafts and user profile data
- extraction reports and changelog entries
- consent records
- research profiles, runs, source items, evidence, signals, briefs, and recommended actions
- search documents, knowledge documents, document chunks, and retrieval traces

That mirrors how the product is used. A job application is not isolated. It accumulates messages, people, notes, drafts, reminders, source evidence, and next actions over time.

## Service Layer

The service layer is intentionally granular. Some examples:

- `scraper.py` handles job extraction from supported boards.
- `email_classifier.py` handles Gmail classification before any product side effects.
- `gmail_intelligence/*` handles route/subtype scoring and email-derived signals.
- `action_candidates.py` and `dedupe_gate.py` centralize safer action proposal and duplicate suppression paths.
- `email_classification_traces.py` persists classifier decision metadata.
- `retrieval/*` handles document chunking, lexical chunk retrieval, eval gates, and shadow traces.
- `company_identity.py`, `hunter.py`, and `contact_enrichment.py` handle enrichment work.
- `email_filter.py`, `email_matcher.py`, and `email_sender.py` handle communication workflow pieces.
- `research_radar/*` handles Radar orchestration, evidence persistence, report generation, and recommendation persistence.
- `ai_orchestrator.py` centralizes model-call policy, prompt versions, retries, parsing, fallback tracking, and task metrics.

This split is deliberate. The codebase mixes deterministic product rules, API adapters, background jobs, and model-backed workflows. Keeping each responsibility narrow makes it possible to tighten one slice without accidentally changing the behavior of another.

## Background Jobs

Celery runs the work that should not live in the request path:

- Gmail polling
- follow-up checks
- dead-listing checks
- ATS metrics jobs
- weekly digest and maintenance work
- Radar dispatch when enabled

The reason is not fancy. The product needs retryable work outside the request cycle. Gmail sync, scheduled checks, and background analysis should keep moving even when nobody has the dashboard open.

## Frontend

The dashboard is a React 19 single-page app built with Vite and strict TypeScript. It uses a tabbed shell because the product behaves more like a workstation than a content site.

Major views are lazy-loaded:

- Pipeline
- Radar
- Inbox
- Conversations
- Network
- Calendar
- Job Search
- Analytics
- Export
- Classifier Audit
- Extraction Reports
- Profile
- Settings

The dashboard is not a thin CRUD wrapper. It is built around workflow loops: reviewing the pipeline, triaging email, following up with recruiters, preparing for interviews, maintaining profile data, and reviewing Radar opportunities.

## Auth And Session Design

The frontend keeps access tokens in memory instead of local storage. After Google OAuth, the backend exchanges the callback for a one-time code, then the dashboard exchanges that code for a session. Refresh happens through an HttpOnly cookie.

That design is more work than throwing a token into browser storage. It is also the right tradeoff for a product that connects Gmail, stores private job-search data, and has an extension surface.

The extension uses its own user-scoped API key path. That key is intentionally narrower than the dashboard session. Extension capture should not automatically mean broad dashboard access.

## Chrome Extension

The extension exists because most job-search tools lose the user at capture. If saving a role requires a context switch, it gets deferred, and then the role is gone.

The extension uses Manifest V3 with:

- platform detection
- content extraction
- side panel review/editing
- background message routing
- career-page visit tracking
- submission detection
- offline queueing

The main implementation pieces are split by job:

- `detector.js` decides whether the current page is relevant.
- `content.js` extracts structured job data.
- `tracker.js` handles broader career-page visit tracking.
- `background.js` coordinates storage, sync, and messaging.
- `sidepanel.js` manages capture UI.
- `banner.js` handles page-level prompts and suppression behavior.

The extension also handles stale ATS pages, unsupported job pages, false-positive suppression, offline saves, and local development backends. Those are the parts that make browser products reliable in practice.

## AI And Automation

AppTrail uses deterministic logic where wrong decisions can mutate product state, and reserves model calls for bounded interpretation tasks.

OpenAI-backed flows exist for:

- ambiguous Gmail classification adjudication after local preflight/redaction
- draft generation
- resume parsing
- resume tailoring
- Radar research synthesis and verification when research mode is enabled
- legacy compatibility extraction paths

The Gmail classifier is deliberately not LLM-first. Local route/subtype scoring runs before any model call. The LLM path is limited to ambiguous, preflight-safe cases. If preflight fails, the system falls back to deterministic output or review instead of sending raw inbox content to a model.

That is the main design principle across the AI surface: model calls should be useful, bounded, observable, and reversible where possible. They should not quietly become the control plane for the product.

## Retrieval And Grounding

The current product search path still uses user-scoped, source-level lexical `SearchDocument` retrieval. A newer retrieval foundation also exists:

- `UserKnowledgeDocument`
- `DocumentChunk`
- deterministic chunking
- lexical chunk retrieval
- `RetrievalTrace`
- local retrieval eval gates
- opt-in source-vs-chunk shadow tracing

That foundation is intentionally not the same thing as a promoted production RAG system. There are no production embeddings, vector search, BM25, reranking, or claim-level support guarantees in the default product path yet. Those are gated behind evals because retrieval errors can become unsupported answers.

## Radar

Opportunity Radar is not treated as an open-ended autonomous agent. It has graph-style orchestration, persisted runs and steps, source/evidence/report persistence, model-call cost tracking, and verifier behavior.

The current limitation is evidence quality. Broad public web research is brittle. The direction is source-registry-first Radar: verified company/job sources, structured provider adapters, persisted source evidence, trust/freshness scoring, and claim-level verification before treating output as product-grade.

## Security, Consent, And Privacy

Several choices are worth calling out:

- Google OAuth with a one-time code exchange instead of tokens in URLs
- refresh tokens in HttpOnly cookies
- per-user extension API keys with narrower scope
- consent-aware AI and enrichment paths
- encrypted Gmail tokens at rest
- token blacklisting and auth-code exchange backed by Redis with local fallbacks
- production metrics protection
- admin-gated AI metrics
- prompt preflight and redaction before LLM adjudication

Security details live in [SECURITY.md](SECURITY.md). The short version is that auth, consent, and extension trust boundaries are not side notes in this codebase. They are part of the architecture.

## Local And Production Operation

Local development supports both:

- full Docker stack through `make local-open` or `make local-up`
- manual service startup for backend, worker, scheduler, and dashboard

The intended production shape is straightforward:

- dashboard on Vercel
- backend API on Railway or a comparable container host
- separate worker and beat services
- PostgreSQL and Redis as external services

There is no exotic deployment trick here. The product needs reliable, replaceable infrastructure and clear operational boundaries.

## Testing And Quality

The repo currently has 118 product/backend test files. Coverage includes:

- auth and redirect behavior
- API key flows
- Gmail sync and email processing
- classifier traces and AI artifact behavior
- action candidates and dedupe behavior
- metrics and readiness
- Radar workflows
- extension-related backend paths
- resume and draft flows
- retrieval foundation behavior

The important thing is not the raw count. The useful part is that the tests cover workflow behavior, not only isolated helpers.

## What This Shows

From a product-engineering standpoint, AppTrail demonstrates:

- full-stack ownership across browser, backend, workers, and UI
- pragmatic AI architecture instead of model-first architecture
- real handling of long-running jobs, auth, consent, and privacy
- external integrations without letting providers own the product design
- incremental hardening of cross-cutting systems like AI orchestration, action candidates, dedupe, and retrieval

The codebase is not trying to make every feature look more advanced than it is. Some parts are production-shaped. Some parts are beta scaffolding. Some parts are deliberately gated until there is enough evidence to promote them. That is the point: the system is built to make those tradeoffs explicit.
