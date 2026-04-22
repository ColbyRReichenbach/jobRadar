# AppTrail — Project Specification & Development Roadmap
**Version:** 3.0 — Hardened (13 edge cases resolved)  
**Author:** Colby Reichenbach  
**Date:** March 2026  
**Stack:** Next.js · FastAPI · Supabase · Chrome Extension · Claude API  
**Build Method:** Claude Code + Stop Hook (autonomous self-healing dev)  
**Status:** Pre-development — spec complete

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [System Architecture](#2-system-architecture)
3. [Hardened Tech Stack](#3-hardened-tech-stack)
4. [Database Schema](#4-database-schema)
5. [Email Intelligence Layer](#5-email-intelligence-layer)
6. [Claude Code Setup & Autonomous Dev Strategy](#6-claude-code-setup--autonomous-dev-strategy)
7. [Development Roadmap](#7-development-roadmap)
8. [Explicit Scope Boundaries](#8-explicit-scope-boundaries)
9. [Risks & Mitigations](#9-risks--mitigations)
10. [Platform Scraping Intelligence](#10-platform-scraping-intelligence)
11. [Hardening Notes — Edge Cases Resolved Pre-Build](#11-hardening-notes--edge-cases-resolved-pre-build)
12. [Cross-Cutting Policies — Rate Limiting, Backoff & Security](#12-cross-cutting-policies--rate-limiting-backoff--security)

---

## 1. Product Overview

AppTrail is a personal job application intelligence system built for one user: you. It combines a Chrome extension (capture layer), a Next.js dashboard (command center), and a FastAPI backend with Claude API as the reasoning engine. The system tracks every application across every job site, finds contacts at target companies automatically, monitors your inbox for application status changes, and surfaces everything in a single prioritized feed.

The core problem it solves: you apply to a job, you forget about it, the position fills before you connect with anyone there, and a rejection email arrives weeks later that you almost miss. AppTrail eliminates each of those failure points.

### 1.1 Design Principles

- **Capture is instant.** One button in the extension logs a job and kicks off everything else.
- **AI does the classification.** Claude API reads every email and determines status — you never manually sort job emails again.
- **Contacts surface immediately.** Hunter.io runs the moment you log a job so you have names before you even open LinkedIn.
- **The dashboard shows signal, not noise.** Rejections are collapsed. Human replies and interview requests dominate your view.
- **Manual override is always available.** Every AI-determined value can be corrected by hand.

### 1.2 What This Is Not

- Not an auto-apply tool. You apply. AppTrail tracks everything around that action.
- Not a LinkedIn scraper. LinkedIn search URLs are generated — you click them. No account risk.
- Not a multi-user SaaS. Personal tool, single user, no auth complexity needed.
- Not a mobile app. Responsive web dashboard + Chrome extension only.

---

## 2. System Architecture

AppTrail is three distinct layers sharing one backend and one database. Each layer has a single clear responsibility.

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Chrome Extension (Capture)                        │
│  URL detection · Job panel · Contact surface · Log trigger  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP (REST)
┌──────────────────────▼──────────────────────────────────────┐
│  LAYER 2: FastAPI Backend (Brain)                           │
│  /jobs/parse  /contacts/find  /emails/sync  /jobs/search    │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ Job Scraper  │  │ Hunter.io    │  │ Email Classifier│   │
│  │ (Playwright) │  │ API Client   │  │ (Claude API)    │   │
│  └──────────────┘  └──────────────┘  └─────────────────┘   │
│  ┌──────────────┐  ┌──────────────────────────────────────┐ │
│  │ Celery Beat  │  │ Job Aggregator (SerpAPI / Greenhouse)│ │
│  │ (15min poll) │  └──────────────────────────────────────┘ │
│  └──────────────┘                                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  LAYER 3: Supabase (Data)                                   │
│  applications · contacts · email_events · job_listings      │
└─────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  LAYER 4: Next.js Dashboard (Command Center)                │
│  Pipeline Kanban · Application Detail · Email Feed          │
│  Contact Manager · Job Search · Follow-up Reminders         │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Data Flow — Happy Path

```
1. User lands on job page (Greenhouse/Workday/Indeed/etc.)
2. Extension URL detector fires → badge appears on icon
3. User opens extension panel → scraped job data shown for confirm
4. User clicks [Track This Job]
   → POST /jobs/parse with URL
   → Backend: Playwright scrapes, Claude extracts structured data
   → Supabase: applications row inserted (status: 'applied')
   → Hunter.io: domain search fired async
   → Contacts returned to extension within ~5 seconds
5. User selects contacts they reached out to → saved to DB
6. [Background, every 15 min] Celery polls Gmail
   → New emails filtered by sender pattern + keywords
   → Qualifying emails sent to Claude API for classification
   → DB updated: status, color_code, urgency, action_url
7. Dashboard auto-refreshes → colored card appears in feed
8. User opens dashboard → green card at top: interview request
```

---

## 3. Hardened Tech Stack

Every choice below is deliberate. No ambiguity at build time.

### 3.1 Frontend — Dashboard

| Key | Value |
|-----|-------|
| Framework | Next.js 15 (App Router) |
| Styling | Tailwind CSS — utility-first, no CSS files to manage |
| State | Zustand — lightweight global state for pipeline and email feed |
| Data Fetching | TanStack Query (React Query) — server state, cache, auto-refetch |
| Charts | Recharts — lightweight, sufficient for application funnel stats |
| Deployment | Vercel — zero-config CI/CD |

### 3.2 Chrome Extension

| Key | Value |
|-----|-------|
| Manifest | Manifest V3 — required for Chrome Web Store compliance |
| Framework | Vanilla JS + minimal React for the side panel UI |
| Side Panel | Chrome Side Panel API (not popup — persists across tab clicks) |
| MV3 Lifecycle | All backend requests initiated from Side Panel UI (persists while open). Service worker handles URL detection only (fast, stateless). **Never** put async fetch calls in the service worker — Chrome can kill it mid-request after 5 minutes idle. |
| Auth | API key bootstrap: one-time setup page generates key stored in `chrome.storage.local`. Sent as Bearer token on every backend request. Backend validates against `APPTRAIL_API_KEY` env var. No OAuth complexity for single-user. |

### 3.3 Backend

| Key | Value |
|-----|-------|
| Framework | FastAPI — async throughout |
| Task Queue | Celery + Upstash Redis (serverless, free tier). Beat schedule persisted in Supabase via `celery-beat-sqlalchemy`. Retry policy: 3 attempts with exponential backoff, then log to `scraper_errors`. Dead tasks never silently swallowed. |
| Web Scraping | Playwright (async) — dedicated worker process separate from FastAPI app. Concurrency cap: 2 simultaneous instances. Minimum 1GB RAM required for worker container. Job queue ensures serial processing with 30-second timeout per job. Timeout → Claude API fallback automatically. |
| Job Parsing | Claude API `claude-sonnet-4-20250514` — extracts structured JSON from raw HTML |
| Email AI | Claude API `claude-sonnet-4-20250514` — full email body classification |
| Deployment | Railway or Render — FastAPI app on Starter plan (~$5/mo). Playwright worker requires minimum 1GB RAM; free tiers are 512MB and will OOM. Use separate service for the Playwright worker. |
| Secrets | All credentials in environment variables. Local: `.env` file (gitignored). Production: Railway/Render environment variable dashboard — never commit secrets. Extension setup page displays `APPTRAIL_API_KEY` for user to copy into `chrome.storage.local` on first install. |

### 3.4 Database

| Key | Value |
|-----|-------|
| Platform | Supabase — Row Level Security, real-time subscriptions |
| ORM | SQLAlchemy (async) |
| Migrations | Alembic — version-controlled schema changes |
| Real-time | Supabase Realtime — dashboard auto-updates when DB changes |

### 3.5 External APIs

| Key | Value |
|-----|-------|
| Contact Finding | Hunter.io — domain search, department + seniority filter. Results cached in Supabase for 30 days per domain (25 free searches/month covers ~25 unique companies, not 25 applications). When monthly limit hit, degrade gracefully — never throw an error. |
| Job Aggregation | SerpAPI ($50/mo) — aggregates Indeed, LinkedIn, Google Jobs |
| Greenhouse ATS | `boards-api.greenhouse.io` — free, public, no key needed |
| Gmail | Gmail API via OAuth2 — read-only scope. Polling architecture only (Celery Beat every 15 min). No Gmail Push/watch — requires Cloud Pub/Sub and public webhook; out of scope for V1. |
| AI Classification | Anthropic Claude API (`claude-sonnet-4-20250514`) — email + job parsing |

---

## 4. Database Schema

```sql
-- applications: core tracking record
applications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company         TEXT NOT NULL,
  role_title      TEXT NOT NULL,
  department      TEXT,
  job_url         TEXT UNIQUE,
  source          TEXT,          -- greenhouse|workday|linkedin|indeed|manual
  description_text TEXT,
  applied_at      TIMESTAMPTZ DEFAULT now(),
  status          TEXT DEFAULT 'applied',
  --  applied|confirmed|reviewing|active_convo|interview|offer|denied|withdrawn
  status_updated_at TIMESTAMPTZ,
  ats_confirmed   BOOLEAN DEFAULT false,
  last_email_at   TIMESTAMPTZ,
  notes           TEXT,
  archived_at     TIMESTAMPTZ,  -- auto-set 30 days after status = denied|withdrawn
  follow_up_due   BOOLEAN DEFAULT false
  -- Dashboard default: WHERE archived_at IS NULL. 'Show Archived' toggle reveals rest.
  -- Duplicate: job_url UNIQUE constraint returns 409 Conflict with existing record data.
  -- Extension should surface 'Already tracked — view record' on 409, not silent fail.
);

-- contacts: people at the company
contacts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  UUID REFERENCES applications(id) ON DELETE CASCADE,
  name            TEXT,
  title           TEXT,
  email           TEXT,
  linkedin_url    TEXT,
  source          TEXT,          -- hunter|unc_alum|manual
  confidence_score FLOAT,        -- Hunter.io confidence 0-1
  reached_out     BOOLEAN DEFAULT false,
  reached_out_at  TIMESTAMPTZ,
  response_received BOOLEAN DEFAULT false
);

-- email_events: every classified email
email_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  UUID REFERENCES applications(id) ON DELETE SET NULL,  -- nullable
  -- NULL = unmatched email. Surface on dashboard for manual assignment.
  -- Match priority: (1) gmail_message_id dedup, (2) company name from body vs
  -- applications.company, (3) ATS sender → most recent open app on that ATS,
  -- (4) most recently applied. Still ambiguous → insert with NULL application_id.
  contact_id      UUID REFERENCES contacts(id),  -- null if ATS
  gmail_message_id TEXT UNIQUE,  -- dedup key
  sender          TEXT,
  received_at     TIMESTAMPTZ,
  pipeline        TEXT,          -- ats|human
  classification  TEXT,
  -- applied_confirmed|under_review|rejected|interview_request|offer|human_outreach|action_required
  color_code      TEXT,          -- red|green|yellow|blue|gray|purple
  urgency         TEXT,          -- high|medium|low
  action_needed   BOOLEAN DEFAULT false,
  action_url      TEXT,          -- scheduling link if present
  is_human        BOOLEAN DEFAULT false,
  key_sentence    TEXT,          -- sentence that determined classification
  summary         TEXT,          -- plain-english one-liner for dashboard
  collapsed       BOOLEAN DEFAULT false
);

-- job_listings: search results from aggregator
job_listings (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title           TEXT,
  company         TEXT,
  source          TEXT,
  url             TEXT UNIQUE,
  posted_at       TIMESTAMPTZ,
  description_snippet TEXT,
  saved_at        TIMESTAMPTZ DEFAULT now(),
  applied         BOOLEAN DEFAULT false
);

-- scraper_errors: extraction failure log (referenced in §10.10)
scraper_errors (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url             TEXT NOT NULL,
  platform        TEXT,          -- greenhouse|workday|lever|indeed|ashby|linkedin|generic
  error_type      TEXT,          -- timeout|parse_error|http_error|empty_result
  error_message   TEXT,
  html_snippet    TEXT,          -- first 2000 chars of raw HTML for debugging
  failed_at       TIMESTAMPTZ DEFAULT now(),
  resolved        BOOLEAN DEFAULT false
);

-- gmail_tokens: single-row OAuth token store (referenced in §12.4)
gmail_tokens (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  access_token  TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  expires_at    TIMESTAMPTZ NOT NULL,
  updated_at    TIMESTAMPTZ DEFAULT now()
);  -- RLS: service role only. Never expose to extension or public.
```

---

## 5. Email Intelligence Layer

### 5.1 Pre-filter (Zero AI Cost)

Before any email touches the Claude API, it passes through a deterministic filter. Two conditions — either passes it forward:

- Sender domain matches a known ATS platform (`@myworkday.com`, `@greenhouse.io`, `@lever.co`, `@ashbyhq.com`, `@icims.com`, `@jobvite.com`, `@smartrecruiters.com`)
- Sender domain matches a company domain in the applications table AND subject contains a job-related keyword (`application`, `position`, `role`, `candidate`, `interview`, `offer`, `moving forward`, `unfortunately`, `thank you for your interest`)

Everything else is ignored. No tokens spent, no noise in the dashboard.

### 5.2 Classification Tiers

| Status | Trigger Language | Dashboard Color |
|--------|-----------------|-----------------|
| `applied_confirmed` | Thank you for applying, application received | Blue — In Progress |
| `under_review` | Actively reviewing, under consideration | Blue — In Progress |
| `rejected` | Will not be moving forward, not selected | Red — Auto-collapse 24h |
| `interview_request` | Schedule a call, next steps, speak with you | Green — High Priority |
| `offer` | Pleased to offer, offer letter, compensation | Green — High Priority |
| `action_required` | Please complete, assessment, submission needed | Yellow — Needs Attention |
| `human_outreach` | Real name in From field, @company.com domain | Purple — Conversation |

---

## 6. Claude Code Setup & Autonomous Dev Strategy

This project will be built using Claude Code with a self-healing autonomous loop. The goal is maximum autonomous progress with minimum human checkpoints — you review working features, not debugging sessions.

### 6.1 Repository Structure

```
apptrail/
├── CLAUDE.md                    ← Claude Code project constitution
├── .claude/
│   ├── hooks/
│   │   ├── pre-tool.sh          ← Blocks destructive commands
│   │   ├── post-edit.sh         ← Runs linter after file edits
│   │   └── stop-hook.sh         ← Self-healing: blocks exit if tests fail
│   ├── agents/
│   │   ├── db-agent.md          ← Supabase schema + migrations specialist
│   │   ├── api-agent.md         ← FastAPI endpoint builder
│   │   ├── extension-agent.md   ← Chrome extension specialist
│   │   └── email-agent.md       ← Gmail + classification pipeline
│   └── commands/
│       ├── test-all.md          ← /test-all custom command
│       └── deploy-check.md      ← /deploy-check pre-deploy validation
├── backend/                     ← FastAPI app
├── dashboard/                   ← Next.js app
├── extension/                   ← Chrome extension
├── tests/
│   ├── backend/                 ← pytest
│   ├── dashboard/               ← Playwright E2E
│   └── extension/               ← Jest unit tests
└── docs/
    ├── PRD.md                   ← This document
    └── IMPLEMENTATION_PLAN.md   ← Auto-updated by Claude per phase
```

Register the stop hook in `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash .claude/hooks/stop-hook.sh"
          }
        ]
      }
    ]
  }
}
```

### 6.2 CLAUDE.md — Key Rules (Condensed)

Hard limit: 10 rules maximum, one sentence each. Instruction-following degrades as rule count grows. No code style (linter handles that), no file structure docs (Claude reads the repo). Only constraints that are non-obvious and universally applicable:

1. Run pytest before marking any backend task complete. If tests fail, fix them before stopping.
2. Never use `rm -rf` without explicit user confirmation. The pre-tool hook will block it.
3. All API keys come from environment variables. Never hardcode credentials.
4. Each phase has an `IMPLEMENTATION_PLAN.md`. Update it as tasks complete.
5. Use `async/await` throughout FastAPI. No synchronous blocking calls.
6. Supabase schema changes require an Alembic migration file. Never alter tables directly.
7. Import `with_retry()` from `backend/utils/retry.py` for every external API call.
8. All Playwright scrapers use randomized 2-4s delay and realistic User-Agent header.
9. Read Section 12 of this document before writing any service that calls an external API.
10. If a test fails 5+ times with the same approach, try a fundamentally different implementation.

### 6.3 The Self-Healing Loop (Stop Hook)

Each sprint is run using Claude Code's Stop hook mechanism that blocks exit until tests pass.

```bash
# .claude/hooks/stop-hook.sh
#!/bin/bash
# Claude Code injects CLAUDE_STOP_HOOK_OUTPUT with Claude's final message

cd "$(git rev-parse --show-toplevel)"  # always run from repo root

# Run backend tests
pytest tests/backend/ -q 2>&1
BACKEND_RESULT=$?

# Check for completion promise in Claude's output
if echo "$CLAUDE_STOP_HOOK_OUTPUT" | grep -q "PHASE_COMPLETE"; then
  if [ $BACKEND_RESULT -eq 0 ]; then
    exit 0   # Tests pass + promise found → allow exit
  else
    echo "PHASE_COMPLETE found but tests still failing. Fix failing tests."
    exit 2   # Block exit: send failure back to Claude
  fi
fi

echo "PHASE_COMPLETE not output yet. Continue working."
exit 2   # Block exit: Claude keeps iterating
```

Invocation per sprint — run from terminal with a scoped prompt. The stop hook does the rest:

```bash
# Run from your terminal in the project root
# The stop hook automatically blocks exit until tests pass + promise found

claude --max-turns 30 "Build Phase 1: Supabase schema + FastAPI skeleton +
basic Next.js pipeline view. Requirements in docs/IMPLEMENTATION_PLAN.md
Phase 1 section. When all pytest tests pass and /api/health returns 200,
output exactly: PHASE_COMPLETE"

# --max-turns 30 is the safety ceiling.
# Claude cannot exit until stop-hook.sh exits 0.
# If Claude outputs PHASE_COMPLETE but tests fail, hook exits 2 and
# Claude is sent back with the failure message automatically.
```

### 6.4 Per-Phase Verification Commands

`IMPLEMENTATION_PLAN.md` must include these exact commands at the end of each phase block. Claude cannot self-certify completion — it must run all three and show passing output before outputting `PHASE_COMPLETE`:

```bash
## Verify Phase Complete:
# 1. Backend unit tests
pytest tests/backend/ -v --tb=short

# 2. Dashboard E2E tests
npx playwright test tests/dashboard/

# 3. Health check (server must be running)
curl -f http://localhost:8000/api/health

# → All three must pass before outputting PHASE_COMPLETE
# If any fail, fix and re-run. Do not output PHASE_COMPLETE on partial pass.
```

---

## 7. Development Roadmap

Four phases, six weeks of evenings. Each phase produces a verifiable, independently usable product increment. No phase begins until the previous phase's outcomes are confirmed.

### Phase 1 — Weeks 1–2: Foundation — Data Model + Backend + Dashboard Shell

**Build tasks:**
- Define and migrate complete Supabase schema (all 6 tables including `scraper_errors` + `gmail_tokens`)
- Build FastAPI skeleton: `/health`, `/jobs`, `/contacts`, `/emails` endpoints with stubs
- Implement job page scraper using Playwright + Claude API extraction
- Build Next.js dashboard: pipeline Kanban view, application detail page shell
- Manual job entry form (no extension yet — prove the data model works first)
- Supabase Realtime subscription wired to dashboard — cards update live

**Verification (all must pass):**
- `pytest` passes: 100% of API endpoint tests (health, create application, list applications)
- `POST /jobs/parse` with a real Greenhouse URL returns structured JSON in < 8 seconds
- Supabase has all 6 tables with correct foreign key constraints and RLS on `gmail_tokens`
- Next.js dashboard shows a manually-entered application card in the correct status column
- `IMPLEMENTATION_PLAN.md` Phase 1 marked Complete

**Stack:** FastAPI · Supabase · Playwright · Claude API · Next.js · Tailwind · Alembic · pytest

---

### Phase 2 — Weeks 3–4: Chrome Extension + Contact Finding

**Build tasks:**
- Build Chrome extension: Manifest V3, Side Panel API, URL pattern detector
- Extension communicates with backend via REST (API key auth — Bearer token in Authorization header)
- URL detector covers: Greenhouse, Lever, Ashby, Workday, Indeed, LinkedIn Jobs
- Implement Hunter.io API client: domain search with dept + seniority filter
- Extension panel shows confirmed job data + contact candidates within 5 seconds
- Contact selection saved to DB; manual add field works
- Generate UNC alumni LinkedIn search URLs automatically per company

**Verification (all must pass):**
- Extension loads in Chrome with no console errors on target job page URLs
- Clicking "Track This Job" on a live Greenhouse URL creates a DB record and returns contacts
- Hunter.io returns at least 1 contact for 3 of 5 test company domains
- LinkedIn search URL generated for "UNC Chapel Hill + [company] + data" is correct
- Contact marked `reached_out` in DB after user selects them in extension panel
- `IMPLEMENTATION_PLAN.md` Phase 2 marked Complete

**Stack:** Chrome Extension API · Manifest V3 · Side Panel API · Hunter.io API · API key auth

---

### Phase 3 — Week 5: Email Intelligence — Gmail Polling + AI Classification

**Build tasks:**
- Gmail API OAuth2 setup (read-only scope). Token storage: `access_token` + `refresh_token` persisted in Supabase `gmail_tokens` table. Celery worker reads token on each poll, refreshes via `google-auth` library if expiring within 5 min, writes new token back to DB.
- Celery Beat job: poll Gmail every 15 minutes
- Pre-filter: ATS sender patterns + company domain matching + keyword detection
- Claude API classifier: full email body → structured JSON (`status`, `color`, `urgency`, `action_url`, `summary`)
- Human vs. ATS pipeline separation by sender pattern
- DB: `email_events` table populated, application status auto-updated
- Dashboard email feed: colored cards, collapsed rejections, action buttons for scheduling links
- Supabase Realtime: dashboard updates within 30 seconds of email arrival

**Verification (all must pass):**
- Celery Beat confirmed running: Gmail polled every 15 minutes (log evidence)
- Test email from `@myworkday.com` correctly classified as ATS, not human
- Rejection email ("will not be moving forward") classified as `rejected` with red `color_code`
- Interview request email with Calendly link: classified green, `action_url` extracted correctly
- Dashboard card updates status from `applied` to `rejected` without page refresh (Realtime)
- Pre-filter blocks > 90% of non-job emails from reaching Claude API (measured by log counts)
- `IMPLEMENTATION_PLAN.md` Phase 3 marked Complete

**Stack:** Gmail API · OAuth2 · Celery Beat · Upstash Redis · Claude API · Supabase Realtime

---

### Phase 4 — Week 6: Polish — Job Search + Follow-up + Full Integration Test

**Build tasks:**
- Job search tab: SerpAPI integration aggregating Indeed + Google Jobs results
- Greenhouse public API: search roles at known target companies without SerpAPI
- Follow-up reminder logic: flag any application with no email activity after 7 days
- Contact response tracking: when email arrives from a contact's email, mark responded
- Full pipeline integration test: apply → contacts found → email classified → status updated
- Dashboard search: full-text across companies, roles, contacts, email summaries
- Export to CSV: applications table with status history
- Performance: dashboard load < 2 seconds with 100 application records

**Verification (all must pass):**
- SerpAPI job search returns results for "Data Scientist North Carolina" with source correctly labeled
- Follow-up reminder appears on dashboard for any application > 7 days with no email activity
- End-to-end test passes: new application → Hunter contacts → simulated Gmail email → status update confirmed
- Search returns correct result for company name query across 50 seeded application records
- CSV export contains all columns including status and last email date
- Lighthouse performance score > 85 on dashboard home page
- `IMPLEMENTATION_PLAN.md` Phase 4 marked Complete — project ships

**Stack:** SerpAPI · Greenhouse API · Full-stack integration tests · Playwright E2E · CSV export

---

## 8. Explicit Scope Boundaries

### In Scope — Version 1.0
- Chrome extension with URL detection and job capture
- FastAPI backend with job scraping, contact finding, email polling
- Supabase database with real-time subscriptions
- Next.js dashboard: pipeline, detail pages, email feed, contact manager
- Gmail integration: OAuth, 15-minute polling, Claude classification
- Hunter.io contact finding by company domain and department
- Job search via SerpAPI and Greenhouse public API
- UNC alumni LinkedIn search URL generation
- Follow-up reminders for cold applications

### Explicitly Out of Scope — V1
- LinkedIn scraping (account ban risk — search URLs only)
- Auto-applying to jobs
- Resume tailoring per application
- Multi-user support or authentication beyond single user
- Native mobile app
- Workday login-based application tracking
- Outbound email sending (drafts only — you send)

### Future Considerations — V2
- Proxycurl API integration for LinkedIn profile data ($0.01/profile)
- Resume keyword gap analysis against specific JDs
- Interview prep mode: auto-generate company research brief when interview is scheduled
- Calendar integration: auto-block prep time when interview confirmed

---

## 9. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Playwright scraper fails on new ATS layout | Medium | Claude API as fallback parser for unstructured HTML; manual entry always available |
| Hunter.io finds no contacts for small companies | Low | LinkedIn search URL generated as fallback; manual contact entry in extension panel |
| Gmail API OAuth token expires | Low | Token refresh built into Celery worker; error logged and surfaced on dashboard |
| Claude API classification is wrong | Low | User can override any AI-determined status manually; `key_sentence` shown for transparency |
| SerpAPI rate limits hit | Medium | Greenhouse public API as free fallback; search results cached for 24h |
| Stop hook runs indefinitely on hard bug | Low | `--max-turns 30` hard cap; human review at each phase completion gate |

---

## 10. Platform Scraping Intelligence

This section documents the exact URL patterns, extraction methods, selectors, and fallback strategies for every job platform AppTrail supports. This is the foundation the scraper is built on — if these break, the product breaks. Each platform has a primary method (API or structured data) and a Playwright fallback for resilience.

> **Core principle:** prefer APIs and structured data over CSS selectors. Selectors break when sites redesign. JSON responses and schema.org markup are stable contracts.

### 10.1 Master Extraction Decision Tree

Every URL runs through this routing logic in order. The first method that returns valid data wins. Claude API is the final fallback.

```python
def extract_job(url: str) -> JobData:
    platform = detect_platform(url)
    # Tier 1: Official API — Greenhouse and Lever (free, stable, no scraping)
    if platform in ['greenhouse', 'lever']:
        return api_extract(url, platform)
    # Tier 2: JSON-LD structured data (check on ALL platforms first)
    json_ld = extract_json_ld(fetch_html(url))
    if json_ld and json_ld.get('@type') == 'JobPosting':
        return parse_json_ld(json_ld)
    # Tier 3: Platform-specific Playwright scraper
    if platform in ['workday', 'indeed', 'ashby']:
        return playwright_extract(url, platform)
    # Tier 4: Claude API fallback — strip HTML first (target <5000 tokens)
    # Remove all <script>, <style>, <nav>, <footer>, <header> tags.
    # Send body text only. Prompt: 'Return JSON only from main content area.'
    # Cost per call: ~$0.003. Raw HTML without stripping: $0.10-0.50. Always strip.
    return claude_extract(strip_html_noise(fetch_html(url)))
```

### 10.2 JSON-LD Universal Layer

Most ATS platforms embed `schema.org/JobPosting` in a `<script type='application/ld+json'>` tag. This is the most stable extraction method — maintained for SEO, rarely breaks on redesigns. Check for it before any CSS selector approach.

```python
from bs4 import BeautifulSoup
import json

def extract_json_ld(html: str) -> dict | None:
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if data.get('@type') == 'JobPosting':
                return {
                    'title':       data.get('title') or data.get('name'),
                    'company':     data.get('hiringOrganization', {}).get('name'),
                    'location':    data.get('jobLocation', {}).get('address', {}).get('addressLocality'),
                    'description': data.get('description'),
                    'posted_at':   data.get('datePosted'),
                }
        except (json.JSONDecodeError, AttributeError):
            continue
    return None
```

### 10.3 Greenhouse

| Field | Value |
|-------|-------|
| Method | Official Public REST API — no auth, no scraping, no Playwright |
| URL Patterns | `boards.greenhouse.io/{token}/jobs/{id}` · `{company}.com/careers?gh_jid={id}` — hosted URL: board token NOT in URL. Fetch page HTML, extract from embed script: `src='https://boards.greenhouse.io/embed/job_board?for={TOKEN}'` |
| API Endpoint | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}` |
| List All Jobs | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Key Fields | `title`, `content` (HTML description), `location.name`, `departments[]`, `offices[]` |
| board_token | Extracted from URL slug: `boards.greenhouse.io/{THIS}/jobs` |
| Reliability | Extremely high — official public API, documented, versioned |
| Target Companies | Twitch (`boards.greenhouse.io/twitch`), DraftKings (`boards.greenhouse.io/draftkings`), CapTech (`boards.greenhouse.io/captechconsulting`) |

```python
import re, asyncio
import httpx

async def greenhouse_extract(url: str, retries: int = 3) -> dict:
    match = re.search(r'greenhouse\.io/([^/]+)/jobs/(\d+)', url)
    token, job_id = match.group(1), match.group(2)
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f'https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}'
                )
                resp.raise_for_status()  # raises on 4xx/5xx
                data = resp.json()
                break
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            if attempt == retries - 1:
                raise  # exhaust retries → caller falls through to Claude fallback
            await asyncio.sleep(2 ** attempt)  # exponential backoff: 1s, 2s, 4s
    return {
        'title':       data['title'],
        'company':     token,
        'department':  data['departments'][0]['name'] if data.get('departments') else None,
        'location':    data['location']['name'],
        'description': strip_html(data['content']),
        'source':      'greenhouse',
    }
```

### 10.4 Lever

| Field | Value |
|-------|-------|
| Method | Official Public REST API — Lever explicitly allows third-party GET access |
| URL Patterns | `jobs.lever.co/{company}/{uuid}` |
| API Endpoint | `GET https://api.lever.co/v0/postings/{company}/{uuid}?mode=json` |
| List All Jobs | `GET https://api.lever.co/v0/postings/{company}?mode=json` |
| Key Fields | `text` (title), `categories.team` (department), `categories.location`, `descriptionPlain`, `applyUrl` |
| Reliability | Very high — Lever notes published jobs may be accessed by third parties |

### 10.5 Workday (myworkdayjobs.com)

Workday is the hardest platform. It is a full SPA with no public API, obfuscated CSS class names, and dynamic tokens. A simple GET request returns a loading spinner with no job data. The correct approach is intercepting background XHR calls.

| Field | Value |
|-------|-------|
| Method | Playwright + network request interception (capture background JSON API calls) |
| URL Pattern | `{company}.wd{N}.myworkdayjobs.com/{site}/job/{req_id}/{title}` |
| Key Insight | Workday fires internal REST calls after page renders. Intercept these — far cleaner than DOM scraping. |
| Intercept URL | Pattern: `**/wday/cxs/**/jobs/**` or `**/api/apply/v2/jobs/**` |
| JSON Fields | `jobTitle`, `jobDescription` (HTML), `primaryLocation`, `jobFamilyGroup` (department) |
| CSS Fallback | `[data-automation-id='jobPostingTitle']` · `[data-automation-id='jobPostingDescription']` · `[data-automation-id='locations']` |
| Reliability | Medium — `data-automation-id` attributes are stable; internal API paths change periodically |
| Your Targets | Target (`target.wd1.myworkdayjobs.com/TGT`), Lowe's (`lowes.wd5.myworkdayjobs.com/Lowes`), Wells Fargo, BofA, CVS, Allstate all use Workday |

```python
async def workday_extract(url: str) -> dict:
    job_data = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Polite scraping: randomized 2-4s delay, realistic user-agent
        await page.set_extra_http_headers({'User-Agent': REALISTIC_UA})
        # Intercept background JSON calls
        async def handle_response(response):
            if 'jobs' in response.url and response.status == 200:
                try:
                    data = await response.json()
                    if 'jobTitle' in str(data):
                        job_data.update(parse_workday_json(data))
                except Exception as e:
                    logger.warning(f'Workday XHR parse failed: {e}')
        page.on('response', handle_response)
        await asyncio.sleep(random.uniform(2, 4))  # politeness delay
        await page.goto(url, wait_until='networkidle', timeout=20000)
        # CSS fallback if interception missed it
        if not job_data.get('title'):
            job_data['title'] = await page.text_content('[data-automation-id="jobPostingTitle"]')
            job_data['description'] = await page.inner_html('[data-automation-id="jobPostingDescription"]')
        await browser.close()
    return job_data
```

### 10.6 Indeed

Indeed aggressively blocks scrapers. For individual detail pages, JSON-LD works reliably. For search aggregation, route through SerpAPI — never scrape Indeed search results directly.

| Field | Value |
|-------|-------|
| Method | JSON-LD for detail pages; SerpAPI for search |
| URL Patterns | `indeed.com/viewjob?jk={job_key}` |
| Search | SerpAPI: `api.serpapi.com/search?engine=google_jobs&q={query}&location={loc}` |
| CSS Fallback | `h1.jobsearch-JobInfoHeader-title` · `div#jobDescriptionText` · `div[data-testid='inlineHeader-companyName']` |
| Anti-bot | Set realistic user-agent, 2-3s wait after navigation, use Playwright with stealth plugin |
| Reliability | Medium via direct scrape; High via SerpAPI for search |

### 10.7 LinkedIn Jobs

LinkedIn actively blocks and litigates against scraping. The extension reads the DOM when you are already on the page — this is user-initiated access, not a bot crawl. The backend never fetches LinkedIn.

| Field | Value |
|-------|-------|
| Method | Extension content script reads live DOM client-side only — no backend fetch |
| URL Pattern | `linkedin.com/jobs/view/{job_id}` |
| DOM Selectors | `h1.job-details-jobs-unified-top-card__job-title` · `div.job-details-jobs-unified-top-card__company-name` · `div.job-details-module__content` · `span.job-details-jobs-unified-top-card__bullet` |
| Fallback | JSON-LD embedded on public LinkedIn job pages |
| **CRITICAL** | **Backend NEVER fetches LinkedIn URLs. Extension reads already-rendered page only.** |
| Reliability | High when user is viewing the page. Selectors need quarterly verification. |

### 10.8 Your Target Companies — ATS Map

| Company | ATS Platform | Extraction Method + URL |
|---------|-------------|------------------------|
| Target | Workday | Workday XHR intercept — `target.wd1.myworkdayjobs.com/TGT` |
| Lowe's | Workday | Workday XHR intercept — `lowes.wd5.myworkdayjobs.com/Lowes` |
| Wells Fargo | Workday | Workday XHR intercept — `wellsfargojobs.com` (Workday-hosted) |
| Bank of America | Workday | Workday XHR intercept — `careers.bankofamerica.com` |
| CVS Health | Workday | Workday XHR intercept — `cvshealth.wd1.myworkdayjobs.com` |
| Twitch | Greenhouse | Greenhouse API — `boards.greenhouse.io/twitch` |
| DraftKings | Greenhouse | Greenhouse API — `boards.greenhouse.io/draftkings` |
| YouTube/Google | Custom | JSON-LD first — `careers.google.com/jobs/results/{id}` |
| CapTech | Greenhouse | Greenhouse API — `boards.greenhouse.io/captechconsulting` |
| Allstate | Workday | Workday XHR intercept — `allstate.wd5.myworkdayjobs.com` |

### 10.9 Extension URL Detection Regex Patterns

```javascript
// extension/src/detector.js — evaluated on every page navigation
const PLATFORM_PATTERNS = [
  { platform: 'greenhouse',
    regex: /boards\.greenhouse\.io\/([^\/]+)\/jobs\/(\d+)/,
    extract: m => ({ token: m[1], job_id: m[2] }) },

  { platform: 'greenhouse_hosted',
    regex: /[?&]gh_jid=(\d+)/,
    extract: m => ({ job_id: m[1] }) },

  { platform: 'lever',
    regex: /jobs\.lever\.co\/([^\/]+)\/([a-f0-9-]{36})/,
    extract: m => ({ company: m[1], uuid: m[2] }) },

  { platform: 'workday',
    // wd{N} subdomain is optional — some companies use bare myworkdayjobs.com
    regex: /(?:wd\d+\.)?myworkdayjobs\.com\/([^\/]+)\/job\//,
    extract: m => ({ site: m[1] }) },

  { platform: 'ashby',
    regex: /jobs\.ashbyhq\.com\/([^\/]+)\/([a-f0-9-]{36})/,
    extract: m => ({ company: m[1], uuid: m[2] }) },

  { platform: 'linkedin',
    regex: /linkedin\.com\/jobs\/view\/(\d+)/,
    extract: m => ({ job_id: m[1] }) },

  { platform: 'indeed',
    regex: /indeed\.com\/viewjob\?jk=([a-z0-9]+)/i,
    extract: m => ({ job_key: m[1] }) },

  // Generic fallback — check JSON-LD or Claude API
  { platform: 'generic',
    regex: /\/careers?\/|\/jobs?\/|careers?\.|jobs?\./,
    extract: () => ({}) },
];
```

### 10.10 Scraper Maintenance Protocol

- **Daily canary test** via Celery Beat — one known URL per platform tested every 24h. Empty result triggers dashboard alert.
- **Selectors stored in `scraper_config.py`**, not hardcoded — platform updates require config change only, no redeploy.
- **Circuit breaker:** 3 consecutive extraction failures on a platform routes that platform to Claude API fallback automatically.
- **Failure logging:** every failed extraction writes URL, platform, error type, and raw HTML snippet to `scraper_errors` table in Supabase.
- **Quarterly LinkedIn + Indeed selector audit** — these two redesign most frequently.

---

## 11. Hardening Notes — Edge Cases Resolved Pre-Build

These 13 edge cases were identified during spec review and resolved before build begins. Each is embedded in the relevant section above. Cross-cutting policies (rate limiting, backoff, scraping politeness, security) are consolidated in Section 12.

| # | Edge Case | Severity | Resolution |
|---|-----------|----------|------------|
| 1 | No auth bootstrap flow defined | High | API key via setup page → `chrome.storage.local` → Bearer token. Validated against env var. See §3.2. |
| 2 | Redis container not specified; Celery fails silently | High | Upstash Redis (serverless). Beat schedule in Supabase. Retry: 3x exponential, then log. See §3.3. |
| 3 | Playwright on free-tier server blows up | High | Dedicated worker process, 2 concurrent max, 1GB RAM min, 30s timeout → Claude fallback. See §3.3. |
| 4 | Greenhouse hosted URL has no board token in URL | High | Fetch page HTML, extract token from embed script `src` attribute. Deterministic. See §10.3. |
| 5 | Email matched to wrong application (same domain) | High | 4-step priority matching: body name → ATS sender → most recent open → NULL unmatched. See §4. |
| 6 | Duplicate application tracking silently fails | Medium | UNIQUE on `job_url` returns 409 with existing record. Extension shows "Already tracked". See §4. |
| 7 | Hunter.io free limit hit in 2 weeks | Medium | Cache results per domain for 30 days. 25 searches → 25 companies. Graceful degradation. See §3.5. |
| 8 | Claude API fallback costs $0.50/call on raw HTML | Medium | Strip script/style/nav/footer before sending. Target <5000 tokens. Cost ~$0.003. See §10.1. |
| 9 | Workday URLs without `wd{N}` subdomain not matched | Medium | Updated regex: `/(?:wd\d+\.)?myworkdayjobs\.com/`. `wd{N}` is now optional. See §10.9. |
| 10 | CLAUDE.md bloat degrades instruction following | Medium | Hard cap: 10 rules max, 1 sentence each. No style rules. No structure docs. See §6.2. |
| 11 | Ralph loop self-certifies on vibes, not evidence | Medium | Per-phase explicit test commands in `IMPLEMENTATION_PLAN.md`. All 3 must pass. See §6.4. |
| 12 | MV3 service worker killed mid-request | Medium | All backend calls from Side Panel UI only. Service worker = URL detection only. See §3.2. |
| 13 | Kanban unmanageable after 200+ applications | Low | `archived_at` column, auto-set 30 days post-denial. Default query filters archived. See §4. |

---

## 12. Cross-Cutting Policies — Rate Limiting, Backoff & Security

These policies apply globally across every service. Claude Code must implement them consistently — not reinvent per file. Any code that calls an external API, scrapes a page, or handles credentials must follow these rules.

### 12.1 External API Retry & Backoff Policy

All HTTP calls to external APIs (Greenhouse, Lever, Hunter.io, SerpAPI, Anthropic, Gmail) use the same retry wrapper:

```python
# backend/utils/retry.py — import and use everywhere
import asyncio, httpx

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds

async def with_retry(coro_fn, *args, retries=MAX_RETRIES, **kwargs):
    for attempt in range(retries):
        try:
            return await coro_fn(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:  # rate limited
                retry_after = int(e.response.headers.get('Retry-After', BACKOFF_BASE ** attempt))
                await asyncio.sleep(retry_after)
            elif status >= 500:  # server error — retry
                await asyncio.sleep(BACKOFF_BASE ** attempt)
            else:  # 4xx client error — do not retry
                raise
        except (httpx.RequestError, asyncio.TimeoutError):
            if attempt == retries - 1: raise
            await asyncio.sleep(BACKOFF_BASE ** attempt)
    raise RuntimeError(f'Exhausted {retries} retries')
```

### 12.2 Claude API Error Handling

Both job parsing and email classification call the Anthropic API. Claude API can return 529 (overloaded) and 500 errors. These must be handled explicitly:

```python
# backend/services/claude_client.py
import anthropic, asyncio, json

client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env

async def classify_email(email_body: str) -> dict:
    for attempt in range(3):
        try:
            response = await client.messages.create(
                model='claude-sonnet-4-20250514',
                max_tokens=500,
                system='Return only valid JSON. No preamble.',
                messages=[{'role': 'user', 'content': email_body}]
            )
            return json.loads(response.content[0].text)
        except anthropic.RateLimitError:
            await asyncio.sleep(60)  # hard wait on rate limit
        except anthropic.APIStatusError as e:
            if e.status_code == 529:  # overloaded
                await asyncio.sleep(2 ** attempt)
            elif attempt == 2: raise
        except json.JSONDecodeError:
            logger.error(f'Claude JSON parse failed on attempt {attempt}')
            if attempt == 2:
                return {'classification': 'unknown', 'color_code': 'gray', 'urgency': 'low'}
```

### 12.3 Scraping Politeness Policy

This system scrapes individual job pages that you are actively applying to — not bulk crawling. Volume is very low (1-10 pages per day). These rules apply to all Playwright-based extractions:

- **Randomized delay:** `asyncio.sleep(random.uniform(2, 4))` before every `page.goto()` call.
- **Realistic User-Agent:** set via `page.set_extra_http_headers()`. Use a current Chrome UA string stored in `scraper_config.py` — not Playwright's default headless UA.
- **One page at a time:** Playwright concurrency cap of 2 means no parallel scraping of the same domain.
- **No scraping search result pages.** Extension triggers on individual job detail pages only.
- **Indeed:** JSON-LD only for detail pages. Never use Playwright on Indeed search results — SerpAPI handles all Indeed search.
- **LinkedIn:** backend never fetches LinkedIn. Extension content script reads already-rendered DOM.

### 12.4 Gmail OAuth Token Lifecycle

Token storage and refresh must follow this exact pattern:

```sql
-- Schema addition:
gmail_tokens (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  access_token  TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  expires_at    TIMESTAMPTZ NOT NULL,
  updated_at    TIMESTAMPTZ DEFAULT now()
);  -- single row, single user
```

```python
# backend/services/gmail_auth.py
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import time

async def get_valid_token(db) -> Credentials:
    row = await db.fetchone('SELECT * FROM gmail_tokens LIMIT 1')
    creds = Credentials(
        token=row.access_token,
        refresh_token=row.refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=os.getenv('GMAIL_CLIENT_ID'),
        client_secret=os.getenv('GMAIL_CLIENT_SECRET'),
    )
    if creds.expiry and creds.expiry.timestamp() - time.time() < 300:
        creds.refresh(Request())  # refresh if expiring within 5 min
        await db.execute('UPDATE gmail_tokens SET access_token=$1, expires_at=$2',
            creds.token, creds.expiry)
    return creds
```

### 12.5 Security Checklist — Pre-Deploy

- `APPTRAIL_API_KEY`: min 32 chars, generated via `secrets.token_hex(32)`. Never committed to git.
- `ANTHROPIC_API_KEY`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `HUNTER_API_KEY`, `SERPAPI_KEY`: all Railway/Render env vars. Verify with `railway variables` before deploy.
- FastAPI CORS: restrict origins to your Vercel dashboard URL and `chrome-extension://` origin only. No wildcard `*` in production.
- All backend endpoints require `Authorization: Bearer {APPTRAIL_API_KEY}` header. FastAPI dependency validates on every request. Return 401 on missing/invalid key.
- `gmail_tokens` table: enable Supabase Row Level Security. Only the service role key (used server-side only, never in extension) can read/write this table.
- Extension: `chrome.storage.local` is not encrypted. The API key stored there is low-risk (single user, personal tool) but do not store Gmail tokens or OAuth credentials in the extension under any circumstances.

---

*Spec locked. 13 edge cases + security & rate limiting policies resolved. Build begins at Phase 1.*  
*Claude Code · Stop Hook · Self-healing tests · Autonomous delivery*
