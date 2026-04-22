# Technical Overview

This document explains how AppTrail is built, why the major engineering choices were made, and what the system demonstrates from a product and implementation standpoint. It is written for someone evaluating the codebase as a real software project, not just reading feature marketing.

## Product Shape

AppTrail is not a single-screen job tracker. It is a connected system with three main entry points:

1. A React dashboard where the user runs the search day to day.
2. A Chrome extension that captures opportunities while the user browses.
3. A FastAPI backend with workers that handles sync, enrichment, automation, and storage.

At the time of writing, the codebase includes:

- 121 API endpoints
- 34 SQLAlchemy models
- 35 Alembic migrations
- 35 service modules
- 5 Celery task modules
- 47 test files

## Architecture

The system is split so each surface has a clear job.

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
  -> operator console for the whole workflow
```

This structure matters because the product does a mix of request-response work and long-running background work. Job parsing, Gmail sync, and recurring status checks do not belong in the dashboard, and the extension needs a thin, reliable API contract rather than business logic in the browser.

## Backend

### Framework choice

The backend uses FastAPI with async SQLAlchemy. That fits the workload well:

- external APIs and scraping create lots of I/O waits
- Gmail sync and enrichment are easier to reason about when the request path stays non-blocking
- typed request and response models keep a large endpoint surface manageable

### Domain model

The application record is the center of the system. Around it are the records that give the workflow context:

- email events
- contacts
- alerts
- interviews and interview notes
- resume drafts
- user profile and role interests
- extraction reports and changelog entries
- data consent
- research profiles, runs, source items, signals, scores, briefs, and actions

That model design mirrors how the product is used. A job application is not isolated. It accumulates messages, people, notes, drafts, and reminders over time.

### Service layer

The service layer is intentionally granular. Key examples:

- `scraper.py` handles job extraction from supported boards
- `email_classifier.py`, `draft_writer.py`, `resume_parser.py`, and `resume_tailor.py` handle LLM-backed product tasks
- `company_identity.py`, `hunter.py`, and `contact_enrichment.py` handle enrichment work
- `email_filter.py`, `email_matcher.py`, and `email_sender.py` handle the communication workflow
- `opportunity_radar/*` handles signal collection, scoring, brief generation, and recommended actions

This is the right shape for a codebase that mixes deterministic logic, API adapters, and model-backed workflows. It keeps each responsibility testable and makes it practical to tighten one slice without destabilizing unrelated features.

### Background jobs

Celery runs the scheduled and retryable work:

- Gmail polling
- follow-up checks
- dead-listing checks
- ATS metrics jobs
- digest and maintenance jobs

The practical reason for Celery here is simple: the product needs reliable work outside the request cycle. That includes polling external services, updating internal state, and doing work that can tolerate retry or delay.

## Frontend

### App shell

The dashboard is a React 19 single-page app built with Vite and strict TypeScript. It uses a tabbed shell instead of route-heavy navigation because the product behaves more like a workstation than a content site.

The major views are lazy-loaded:

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

That gives a fast initial shell without turning the app into a full router-driven document site.

### Auth model

The frontend keeps access tokens in memory rather than local storage. After Google OAuth, the backend exchanges the callback for a one-time code, then the dashboard exchanges that code for a session. Refresh happens with an HttpOnly cookie. That is a stronger fit than dropping a long-lived token into browser storage.

### Product behavior

The dashboard is built around actual workflow loops:

- pipeline review
- inbox triage
- recruiter follow-up
- interview preparation
- profile maintenance
- opportunity review in Radar

That shows up in the component structure. The UI is not a thin shell over CRUD endpoints. It is opinionated around decision-making and status movement.

## Chrome Extension

The extension is a serious part of the product, not a promo add-on.

### Why it exists

Most job search tools fail at the capture step. If saving a role requires context switching, the user waits, and the data is lost. The extension solves that problem where it starts: on the job page.

### Extension design

The extension uses Manifest V3 with:

- platform detection
- content extraction
- side panel editing
- background message routing
- career-page visit tracking
- submission detection
- offline queueing

The implementation separates concerns cleanly:

- `detector.js` decides whether the current page is relevant
- `content.js` extracts structured job data
- `tracker.js` handles broader career-page visit tracking
- `background.js` coordinates storage, sync, and messaging
- `sidepanel.js` manages the capture UI
- `banner.js` handles page-level prompts and suppression behavior

That is the right split for a browser product that needs to stay reliable across many job-board implementations.

### Reliability choices

The extension has explicit handling for:

- stale ATS pages
- unsupported job pages
- false-positive suppression
- offline saves
- local development backends

That matters because browser extensions fail at the edges if they only handle the happy path.

## AI And Automation

### Current posture

AppTrail uses LLM-backed features where free-form interpretation helps the workflow and keeps deterministic logic where rules are better.

That is the right tradeoff.

The product currently uses OpenAI for:

- email classification
- draft generation
- resume parsing
- resume tailoring
- legacy compatibility extraction paths

### Orchestration

The orchestration layer now lives in `backend/services/ai_orchestrator.py`. It centralizes:

- task definitions
- model selection
- prompt versioning
- retries
- JSON parsing
- fallback tracking
- task metrics

That refactor matters because scattered LLM calls become hard to reason about fast. A single policy layer gives you one place to manage model choices, failures, prompt inventory, and observability.

### Where the product stays deterministic

Opportunity Radar is deliberately not built as an open-ended agent loop. Collection, scoring, briefs, and actions are mostly deterministic or tightly bounded. That makes the feature easier to test, cheaper to operate, and simpler to explain.

## Security, Consent, And Privacy

Several implementation choices are worth calling out because they show deliberate system design rather than convenience defaults:

- Google OAuth with a one-time code exchange instead of putting tokens in URLs
- refresh tokens in HttpOnly cookies
- per-user API keys for the extension
- consent-aware data handling for AI processing and third-party enrichment
- encrypted Gmail tokens at rest
- token blacklisting and auth code storage backed by Redis with local fallbacks
- structured logging and Prometheus-style metrics

Security details live in [SECURITY.md](SECURITY.md), but the short version is that the codebase treats auth, consent, and extension trust boundaries as first-order design constraints.

## Local And Production Operation

Local development is supported in two ways:

- full Docker stack through `make local-open` or `make local-up`
- manual service startup for backend, worker, scheduler, and dashboard

The intended production shape is:

- dashboard on Vercel
- backend API on Railway or a comparable container host
- separate worker and beat services
- PostgreSQL and Redis as external services

That deployment story is boring in the best way. It uses familiar, replaceable infrastructure and does not depend on fragile platform magic.

## Testing And Quality

The repo currently has 47 test files, and the current working suite is green. The coverage spans:

- auth and redirect behavior
- API key flows
- Gmail and email-processing behavior
- duplicate handling
- metrics
- Radar workflows
- extension-related backend paths
- resume and draft flows

The important point is not the raw count. It is that the project tests workflow behavior, not just isolated helpers.

## What This Demonstrates

If I were reviewing this project as hiring material, the strongest signals would be:

- full-stack product ownership across browser, backend, workers, and UI
- pragmatic architecture decisions instead of fashionable ones
- real handling of long-running jobs, consent, and auth
- comfort integrating external systems without letting them dominate the design
- willingness to refactor cross-cutting concerns, such as AI orchestration, once the initial product loop is proven

The codebase is large enough to show real system design, but still structured enough that the reasoning behind it is visible.
