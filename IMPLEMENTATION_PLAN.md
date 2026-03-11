# IMPLEMENTATION_PLAN.md
# AppTrail — Autonomous Build Plan
# Claude Code reads this at the start of every phase session.
# Do not skip sections. Do not build features outside the active phase scope.

---

## HOW TO USE THIS FILE

Each phase has:
- **Scope** — exactly what gets built. Nothing more.
- **Tasks** — ordered list. Complete in order.
- **Verify** — the exact commands to run. All must pass before outputting PHASE_COMPLETE.
- **Status** — update this as you complete each task. Mark phase Done when verified.

Cross-cutting rules that apply to every phase are in `CLAUDE.md`.
Full technical spec, schema, and platform details are in `docs/PRD.md`.
When in doubt, PRD.md wins.

---

## PHASE STATUS SUMMARY

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Foundation — Schema + Backend + Dashboard Shell | `[x] Done` |
| 2 | Chrome Extension + Contact Finding | `[x] Done` |
| 3 | Email Intelligence — Gmail + AI Classification | `[x] Done` |
| 4 | Polish — Job Search + Follow-up + Integration Test | `[x] Done` |

---

---

# PHASE 1 — Foundation
## Weeks 1–2 | Schema + Backend + Dashboard Shell

### Scope
Build the data layer, the FastAPI backend skeleton, the Playwright scraper, and the
Next.js dashboard Kanban shell. No Chrome extension. No email. No Hunter.io.
Prove the data model works via manual entry before any automated capture is added.

### Prerequisites
- Supabase project created. `DATABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`.
- `ANTHROPIC_API_KEY` in `.env`.
- Python 3.11+ and Node 18+ available.
- Playwright browsers installed: `playwright install chromium`.

---

### Tasks

**1.1 — Alembic migrations: all 6 tables**
Create and run migrations for:
- `applications` (with `archived_at`, `status_updated_at`, UNIQUE on `job_url`)
- `contacts` (ON DELETE CASCADE from applications)
- `email_events` (ON DELETE SET NULL from applications, nullable `application_id`)
- `job_listings` (UNIQUE on `url`)
- `scraper_errors`
- `gmail_tokens` (single row; enable RLS — service role only after creation)

Schema source of truth: `docs/PRD.md` Section 4.
All migrations in `backend/alembic/versions/`. Never ALTER TABLE directly.

Status: `[x]`

---

**1.2 — FastAPI app skeleton**
Create `backend/main.py` with:
- `GET /api/health` → `{"status": "ok", "timestamp": <iso>}`
- `POST /api/jobs/parse` → stub returning `{"status": "pending"}`
- `GET /api/jobs` → stub returning `[]`
- `POST /api/jobs` → stub accepting application payload
- `GET /api/contacts` → stub returning `[]`
- `GET /api/emails` → stub returning `[]`

All routes fully async. Auth dependency on every route except `/health`:
```python
# backend/dependencies.py
async def verify_api_key(authorization: str = Header(...)):
    expected = f"Bearer {os.getenv('APPTRAIL_API_KEY')}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

CORS: allow origins = `["http://localhost:3000"]` for local dev.
Will be updated to Vercel URL + chrome-extension:// before Phase 4 deploy.

Status: `[x]`

---

**1.3 — Retry utility**
Create `backend/utils/retry.py` with the `with_retry()` async wrapper from `docs/PRD.md` Section 12.1.
This is imported by every service that calls an external API. Build it first.

Status: `[x]`

---

**1.4 — Playwright job scraper**
Create `backend/services/scraper.py`.
Implement the full extraction decision tree from `docs/PRD.md` Section 10.1:

- Tier 1: `greenhouse_extract()` — httpx async, with retry/backoff (PRD §10.3 code)
- Tier 1: `lever_extract()` — httpx async, same retry pattern
- Tier 2: `extract_json_ld()` — BeautifulSoup (PRD §10.2 code)
- Tier 3: `workday_extract()` — Playwright XHR intercept (PRD §10.5 code)
  - Randomized 2-4s delay before page.goto()
  - Realistic User-Agent header
  - Proper exception handling (no bare `except: pass`)
- Tier 4: `claude_extract()` — strips noise HTML first, sends <5000 tokens to Claude API
  - Uses `claude_client.py` with error handling from PRD §12.2

Wire `POST /api/jobs/parse` to call `extract_job(url)` and return structured JSON.

Status: `[x]`

---

**1.5 — Claude API client**
Create `backend/services/claude_client.py` with:
- `classify_email(body: str) -> dict` 
- `extract_job_from_html(html: str) -> dict`

Both use the error handling pattern from `docs/PRD.md` Section 12.2:
- Retry on 529 (overloaded) with exponential backoff
- Hard 60s wait on RateLimitError
- Return safe default dict on JSON parse failure after 3 attempts

Model: `claude-sonnet-4-20250514`. `ANTHROPIC_API_KEY` from env.

Status: `[x]`

---

**1.6 — SQLAlchemy models + async session**
Create `backend/models.py` with SQLAlchemy ORM models matching the Alembic schema.
Create `backend/database.py` with async session factory.
All DB operations use `async with session:` — no sync calls.

Status: `[x]`

---

**1.7 — POST /api/jobs (create application)**
Implement the create endpoint fully:
- Accepts: `company`, `role_title`, `job_url`, `source`, `department`, `description_text`
- Writes to `applications` table
- Returns 409 with existing record JSON if `job_url` already exists (UNIQUE violation)
- Returns 201 with created record on success

Status: `[x]`

---

**1.8 — GET /api/jobs (list applications)**
Implement list endpoint:
- Returns all non-archived applications (`WHERE archived_at IS NULL`)
- Ordered by `applied_at DESC`
- Optional `?status=` filter
- Optional `?archived=true` to include archived

Status: `[x]`

---

**1.9 — Next.js dashboard: pipeline Kanban**
Create `dashboard/` with Next.js 15 App Router.
Build the main pipeline view:
- Kanban columns: Applied | Reviewing | Active Convo | Interview | Offer
- Each column fetches `GET /api/jobs?status=<col>` via TanStack Query
- Application card shows: company, role, applied date, status badge
- Tailwind styling — clean, minimal, readable

Supabase Realtime: subscribe to `applications` table changes.
When a row updates, TanStack Query cache invalidates and cards re-render without page refresh.

Status: `[x]`

---

**1.10 — Manual job entry form**
Add a form to the dashboard (modal or sidebar):
- Fields: Company, Role Title, Job URL, Department, Source (dropdown: manual/linkedin/indeed/other)
- On submit: `POST /api/jobs`
- On 409: show "Already tracked" message with link to existing record
- On success: new card appears in "Applied" column via Realtime

Status: `[x]`

---

**1.11 — pytest suite: Phase 1**
Create `tests/backend/test_phase1.py`:

```python
# Required tests — all must pass before PHASE_COMPLETE
def test_health_endpoint()          # GET /api/health returns 200
def test_auth_required()            # GET /api/jobs without key returns 401
def test_create_application()       # POST /api/jobs creates DB record
def test_duplicate_returns_409()    # POST same job_url twice → 409 with existing record
def test_list_applications()        # GET /api/jobs returns created application
def test_archived_filtered()        # archived application not in default list
def test_greenhouse_parse()         # POST /api/jobs/parse with real Greenhouse URL
                                    # returns structured JSON with title, company, description
                                    # Use: https://boards.greenhouse.io/twitch/jobs/7526682002
                                    # (or any live Greenhouse URL — verify it's active first)
```

Status: `[x]`

---

### Verify Phase 1 Complete

Run all three. All must pass. Do not output PHASE_COMPLETE on partial pass.

```bash
# 1. Backend tests
pytest tests/backend/test_phase1.py -v --tb=short

# 2. Health check (uvicorn must be running: uvicorn backend.main:app --port 8000)
curl -f http://localhost:8000/api/health

# 3. Manual dashboard check
# Next.js dev server running: cd dashboard && npm run dev
# Open http://localhost:3000
# Manually enter one application via the form
# Confirm card appears in "Applied" column
# Confirm it persists on page refresh
```

When all pass: output exactly `PHASE_COMPLETE`

**Phase 1 Status: `[x] Done`**

---

---

# PHASE 2 — Chrome Extension + Contact Finding
## Weeks 3–4 | Extension + Hunter.io Integration

### Scope
Build the Chrome extension with Manifest V3, Side Panel API, URL detection, and
the Track This Job flow. Wire Hunter.io contact finding. No email. No Gmail.

### Prerequisites
- Phase 1 complete and verified.
- `HUNTER_API_KEY` in `.env`.
- `APPTRAIL_API_KEY` generated: `python -c "import secrets; print(secrets.token_hex(32))"` — add to `.env`.

---

### Tasks

**2.1 — Hunter.io service + domain caching**
Create `backend/services/hunter.py`:
- `find_contacts(domain: str, company: str) -> list[dict]`
- Filter: department = "engineering" OR "data" OR "analytics"; seniority = "senior" OR "manager" OR "director"
- Cache results in Supabase: before calling Hunter.io API, check `contacts` table for existing entries with same `application_id`'s company domain fetched within last 30 days
- Use `with_retry()` from `backend/utils/retry.py`
- On 429 from Hunter.io: respect `Retry-After` header
- On monthly limit hit: return `[]` with log warning — never raise to caller

Status: `[x]`

---

**2.2 — POST /api/contacts/find endpoint**
Wire Hunter.io into the API:
- Accepts: `application_id`, `company`, `domain`
- Calls `find_contacts(domain, company)`
- Writes results to `contacts` table linked to `application_id`
- Returns contact list with `confidence_score`, `name`, `title`, `email`
- Generate LinkedIn search URL: `https://www.linkedin.com/search/results/people/?keywords=UNC+Chapel+Hill+{company}+data`

Status: `[x]`

---

**2.3 — Chrome extension scaffold**
Create `extension/` directory:
```
extension/
├── manifest.json        ← Manifest V3
├── background.js        ← Service worker: URL detection only
├── sidepanel.html       ← Side panel shell
├── sidepanel.js         ← All backend communication lives here
├── content.js           ← LinkedIn DOM reader (LinkedIn only)
├── detector.js          ← URL pattern matching (PRD §10.9 regex patterns)
└── setup.html           ← One-time API key entry page
```

`manifest.json` must declare:
- `"side_panel"` permission
- `"activeTab"`, `"storage"` permissions
- `"host_permissions"`: backend URL + job site domains
- Content script on `linkedin.com/jobs/*` only

Status: `[x]`

---

**2.4 — Setup page (API key bootstrap)**
`setup.html` / `setup.js`:
- Text input for API key
- On save: `chrome.storage.local.set({ apiKey: value })`
- Validate by calling `GET /api/health` with the key — show success/fail
- Opens automatically on extension install if no key stored

Status: `[x]`

---

**2.5 — URL detector (service worker)**
`background.js`:
- On every tab update: run URL against `PLATFORM_PATTERNS` from PRD §10.9
- If match: `chrome.action.setBadgeText({ text: '●', tabId })` (green dot)
- Store detected platform + extracted params in `chrome.storage.session`
- Service worker does NOT call backend. Detection only.

Status: `[x]`

---

**2.6 — Side panel: Track This Job flow**
`sidepanel.js`:
- On open: read detected platform + params from `chrome.storage.session`
- If LinkedIn: message `content.js` to extract DOM data, receive result
- For all others: call `POST /api/jobs/parse` with URL
- Show scraped job data (title, company, location) for user confirmation
- "Track This Job" button:
  1. `POST /api/jobs` → creates application record
  2. On 409: show "Already tracked" with link
  3. On 201: call `POST /api/contacts/find` with domain
  4. Display contact cards: name, title, email, LinkedIn search URL
  5. Checkbox per contact: "I reached out to this person"
  6. On check: `PATCH /api/contacts/{id}` sets `reached_out: true`, `reached_out_at: now()`

All fetch calls include `Authorization: Bearer {apiKey}` from `chrome.storage.local`.

Status: `[x]`

---

**2.7 — LinkedIn content script**
`content.js` (runs on `linkedin.com/jobs/view/*` only):
- Listens for message from `sidepanel.js`
- Reads DOM using selectors from PRD §10.7
- Falls back to JSON-LD if DOM selectors fail
- Returns structured job object to side panel
- No backend calls from content script

Status: `[x]`

---

**2.8 — PATCH /api/contacts/{id} endpoint**
Implement contact update:
- Accepts: `reached_out`, `reached_out_at`, `response_received`
- Updates `contacts` table record
- Returns updated record

Status: `[x]`

---

**2.9 — pytest suite: Phase 2**
Create `tests/backend/test_phase2.py`:

```python
def test_hunter_find_contacts()        # Returns contacts for known domain (e.g. "stripe.com")
def test_hunter_caching()              # Second call for same domain hits cache, not Hunter API
def test_hunter_limit_degrades()       # Mock 429 from Hunter → returns [] not exception
def test_contacts_find_endpoint()      # POST /api/contacts/find returns list + linkedin URL
def test_contact_update()              # PATCH /api/contacts/{id} updates reached_out fields
def test_linkedin_search_url_format()  # URL contains UNC Chapel Hill + company + data
```

Status: `[x]`

---

### Verify Phase 2 Complete

```bash
# 1. Backend tests (both phases)
pytest tests/backend/ -v --tb=short

# 2. Manual extension test
# Load extension in Chrome: chrome://extensions → Load unpacked → select extension/
# Navigate to: https://boards.greenhouse.io/twitch/jobs/7526682002
# Open side panel
# Confirm job data appears (title, company, location)
# Click "Track This Job"
# Confirm application created in Supabase dashboard
# Confirm contacts appear within 5 seconds
# Confirm LinkedIn search URL is correct format

# 3. Navigate back to same job URL
# Open side panel
# Confirm "Already tracked" message appears (409 handled correctly)
```

When all pass: output exactly `PHASE_COMPLETE`

**Phase 2 Status: `[x] Done`**

---

---

# PHASE 3 — Email Intelligence
## Week 5 | Gmail Polling + AI Classification

### Scope
Gmail OAuth setup, Celery Beat polling, pre-filter, Claude API classification,
email feed on dashboard. No new scraping. No new extension features.

### Prerequisites
- Phase 2 complete and verified.
- Google Cloud project created. OAuth2 credentials (client ID + secret) downloaded.
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` in `.env`.
- Upstash Redis account created. `REDIS_URL` in `.env`.
- `celery-beat-sqlalchemy` added to `requirements.txt`.

---

### Tasks

**3.1 — Gmail OAuth flow**
Create `backend/services/gmail_auth.py` using the exact token lifecycle from PRD §12.4:
- `get_valid_token(db)` reads from `gmail_tokens` table
- Refreshes if expiring within 5 minutes using `google-auth` library
- Writes new token + expiry back to DB after refresh
- Create `GET /api/auth/gmail` endpoint: OAuth2 redirect → callback → stores tokens in `gmail_tokens`
- Run this once manually before starting Celery

Status: `[x]`

---

**3.2 — Celery + Upstash Redis setup**
Create `backend/celery_app.py`:
- Broker: `REDIS_URL` from env (Upstash connection string)
- Beat schedule: `poll_gmail` every 15 minutes
- Beat scheduler: `celery_sqlalchemy_scheduler.DatabaseScheduler` (persists in Supabase)
- Retry policy on tasks: `max_retries=3`, `default_retry_delay=60`
- Failed tasks after 3 retries: write to `scraper_errors` table, do not raise

Status: `[x]`

---

**3.3 — Pre-filter (zero AI cost)**
Create `backend/services/email_filter.py`:

```python
ATS_DOMAINS = {
    "myworkday.com", "greenhouse.io", "lever.co", "ashbyhq.com",
    "icims.com", "jobvite.com", "smartrecruiters.com", "taleo.net"
}

JOB_KEYWORDS = {
    "application", "position", "role", "candidate", "interview",
    "offer", "moving forward", "unfortunately", "thank you for your interest",
    "next steps", "assessment", "decision"
}

def should_classify(email: dict, company_domains: set[str]) -> bool:
    sender_domain = extract_domain(email["sender"])
    if sender_domain in ATS_DOMAINS:
        return True
    if sender_domain in company_domains:
        subject_lower = email["subject"].lower()
        if any(kw in subject_lower for kw in JOB_KEYWORDS):
            return True
    return False
```

`company_domains` = set of domains from all non-archived applications in DB.

Status: `[x]`

---

**3.4 — Gmail poll task**
Create `backend/tasks/poll_gmail.py`:

```python
@celery_app.task(bind=True, max_retries=3)
async def poll_gmail(self):
    try:
        creds = await get_valid_token(db)
        service = build('gmail', 'v1', credentials=creds)
        
        # Fetch emails since last poll (store last_polled_at in gmail_tokens table)
        messages = service.users().messages().list(
            userId='me', q='newer_than:1d'
        ).execute()
        
        company_domains = await get_active_company_domains(db)
        
        for msg in messages.get('messages', []):
            email = fetch_full_message(service, msg['id'])
            
            # Dedup: skip if gmail_message_id already in email_events
            if await email_already_processed(db, msg['id']):
                continue
            
            if not should_classify(email, company_domains):
                continue  # pre-filter: no AI cost
            
            # Classify with Claude API
            result = await classify_email(email['body'])
            
            # Match to application
            application_id = await match_email_to_application(db, email, result)
            
            # Write email_event record
            await create_email_event(db, email, result, application_id)
            
            # Update application status if classification warrants it
            if result['classification'] in STATUS_UPDATES:
                await update_application_status(db, application_id, result)
                
    except Exception as e:
        self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
```

Status: `[x]`

---

**3.5 — Email-to-application matching**
Create `backend/services/email_matcher.py` implementing the 4-step priority from PRD §4:
1. Check if `gmail_message_id` already exists (dedup)
2. Extract company name from email body/sender → match against `applications.company`
3. If ATS sender → find most recent open application using that ATS platform
4. If multiple candidates → pick most recently `applied_at`
5. If still ambiguous → return `None` (insert with NULL `application_id`)

Status: `[x]`

---

**3.6 — GET /api/emails endpoint**
Return email events for dashboard:
- Default: all non-collapsed events, ordered by `received_at DESC`
- Optional `?application_id=` filter
- Optional `?unmatched=true` for NULL application_id events
- Include linked application data (company, role_title) via JOIN

Status: `[x]`

---

**3.7 — PATCH /api/emails/{id} endpoint**
Allow manual override:
- `collapsed`: true/false
- `application_id`: reassign unmatched email to an application
- `classification`: manual override of AI classification
- Returns updated record

Status: `[x]`

---

**3.8 — Dashboard email feed**
Add email feed tab/panel to Next.js dashboard:
- Colored cards per `color_code` (red/green/yellow/blue/purple/gray)
- Rejected cards (`color_code: red`) auto-collapsed after 24h — show count, expand on click
- Green cards (interview/offer) pinned to top
- `action_url` present → show "Schedule" button linking to Calendly/calendar URL
- `is_human: true` → purple border + "Human Contact" badge
- `application_id: null` → amber border + "Unmatched — assign" dropdown
- Supabase Realtime: new `email_events` rows appear without refresh

Status: `[x]`

---

**3.9 — pytest suite: Phase 3**
Create `tests/backend/test_phase3.py`:

```python
def test_prefilter_blocks_noise()         # Random email → should_classify() = False
def test_prefilter_passes_ats()           # @myworkday.com sender → should_classify() = True
def test_prefilter_passes_company_kw()    # Company domain + "interview" subject → True
def test_email_matching_by_company()      # Email with "Target" in body → matches Target application
def test_email_matching_ambiguous()       # Two Target apps → matches most recent
def test_email_matching_unmatched()       # No match → application_id = None
def test_classify_rejection()            # Mock Claude response → rejected, red, low urgency
def test_classify_interview()            # Mock Claude response → interview_request, green, high urgency
def test_classify_action_url()           # Calendly link in body → action_url extracted
def test_email_event_created()           # Full pipeline: email in → event in DB
def test_application_status_updated()    # Rejection email → application status = denied
def test_celery_task_retries()           # Mock Gmail API failure → task retries with backoff
```

Status: `[x]`

---

### Verify Phase 3 Complete

```bash
# 1. All backend tests
pytest tests/backend/ -v --tb=short

# 2. Celery worker running check
celery -A backend.celery_app inspect active
# Should show worker connected, beat schedule registered

# 3. Manual Gmail poll trigger
celery -A backend.celery_app call backend.tasks.poll_gmail.poll_gmail
# Check Supabase: new rows in email_events?
# Check dashboard: colored cards appear?

# 4. Realtime check
# Dashboard open → trigger poll → cards appear without refresh
```

When all pass: output exactly `PHASE_COMPLETE`

**Phase 3 Status: `[x] Done`**

---

---

# PHASE 4 — Polish
## Week 6 | Job Search + Follow-up + Integration Test

### Scope
SerpAPI job search tab, Greenhouse proactive search, follow-up reminders,
contact response tracking, full E2E integration test, search, CSV export,
performance pass, and deploy.

### Prerequisites
- Phase 3 complete and verified.
- `SERPAPI_KEY` in `.env`.
- Vercel project created for dashboard.
- Railway/Render services configured for backend + Playwright worker.
- All production env vars set in Railway/Render dashboard.

---

### Tasks

**4.1 — SerpAPI job search**
Create `backend/services/job_search.py`:
- `search_jobs(query: str, location: str) -> list[dict]`
- Calls `https://serpapi.com/search?engine=google_jobs&q={query}&location={location}`
- Use `with_retry()` wrapper
- Cache results in `job_listings` table for 24h — same query within 24h returns cached
- Also proactively search Greenhouse API for known target companies:
  - Twitch, DraftKings, CapTech: `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs`

Create `GET /api/search?q=&location=` endpoint returning combined results.

Status: `[x]`

---

**4.2 — Follow-up reminder logic**
Add Celery Beat task `check_followups` (daily at 9am):
- Query: applications where `status = 'applied'` AND `last_email_at IS NULL` AND `applied_at < now() - interval '7 days'` AND `archived_at IS NULL`
- For each: set a `follow_up_due` flag (add column via Alembic migration) = true
- Dashboard: applications with `follow_up_due = true` show amber banner "Follow up overdue"

Status: `[x]`

---

**4.3 — Contact response tracking**
In the Gmail poll task, add detection:
- When an email arrives: check if `sender` email matches any `contacts.email`
- If match: `UPDATE contacts SET response_received = true WHERE email = sender`
- Dashboard contact card updates to show "Responded ✓"

Status: `[x]`

---

**4.4 — Dashboard: job search tab**
Add job search tab to dashboard:
- Search input + location input → calls `GET /api/search`
- Results: job card with title, company, source badge (SerpAPI/Greenhouse), posted date
- "Track This Job" on result card → `POST /api/jobs` with pre-filled data
- Results cached — don't re-call API if same query within 10 minutes (TanStack Query cache)

Status: `[x]`

---

**4.5 — Dashboard search (full-text)**
Add global search bar:
- Searches across: `applications.company`, `applications.role_title`, `contacts.name`, `contacts.email`, `email_events.summary`
- `GET /api/search/global?q=` endpoint — Supabase full-text search via `to_tsvector`
- Results grouped by type (Application / Contact / Email)

Status: `[x]`

---

**4.6 — CSV export**
Add `GET /api/export/csv` endpoint:
- Returns all applications (including archived) as CSV
- Columns: company, role_title, department, job_url, source, applied_at, status, last_email_at, notes, contacts_count, archived_at
- Dashboard: "Export CSV" button in settings/header

Status: `[x]`

---

**4.7 — CORS + security hardening for production**
Update FastAPI CORS:
```python
origins = [
    os.getenv("DASHBOARD_URL"),          # Vercel URL
    "chrome-extension://*",               # Extension origin
]
```
Verify `APPTRAIL_API_KEY` is set and ≥32 chars in production env.
Verify `gmail_tokens` RLS is enabled in Supabase.
Verify no `.env` file is committed: `git log --all -- .env` should return nothing.

Status: `[x]`

---

**4.8 — Full E2E integration test**
Create `tests/test_e2e.py`:

```python
def test_full_pipeline():
    # 1. Parse a real Greenhouse job
    # 2. Create application record
    # 3. Find Hunter.io contacts for company domain
    # 4. Simulate incoming rejection email
    # 5. Run pre-filter → passes
    # 6. Run Claude classifier → rejected, red
    # 7. Match to application
    # 8. Confirm application status = denied
    # 9. Confirm email_event record created with correct color_code
    # 10. Confirm archived_at set 30 days in future (mock time)
```

Status: `[x]`

---

**4.9 — Performance pass**
- Lighthouse audit on dashboard: `npx lighthouse http://localhost:3000 --output=json`
- Must score ≥85 on Performance
- If below: check for unoptimized images, missing `loading="lazy"`, blocking JS
- Supabase: add indexes if any query in logs is doing full table scans

Status: `[x]`

---

**4.10 — Deploy**
- **Chosen production stack:** Vercel for `dashboardv2/`; Railway for backend runtime services and data services.
- `dashboardv2/`: deploy to Vercel (`vercel --prod`)
- `backend/` web API: Railway service running `gunicorn -c gunicorn.conf.py backend.main:app`
- `backend/` Celery worker: separate Railway service running `celery -A backend.celery_app:celery_app worker --loglevel=info`
- `backend/` Celery beat: separate Railway service running `celery -A backend.celery_app:celery_app beat --loglevel=info`
- PostgreSQL: Railway managed Postgres
- Redis: Railway managed Redis
- Set all production env vars in Railway and Vercel dashboards
- Update `DASHBOARD_URL` with the final Vercel URL and `VITE_API_URL` with the final backend API URL
- Detailed execution checklist: `docs/deployment-checklist.md`
- Smoke test: hit production `/api/health`, open production dashboard, track one real job

Status: `[x]`

---

**4.11 — pytest suite: Phase 4**
Create `tests/backend/test_phase4.py`:

```python
def test_job_search_returns_results()    # SerpAPI query returns ≥1 result
def test_job_search_caching()            # Same query within 24h returns cached results
def test_greenhouse_search()             # Twitch Greenhouse search returns jobs
def test_followup_flagging()             # 8-day-old applied application gets follow_up_due = true
def test_contact_response_tracking()     # Email from contact email → response_received = true
def test_csv_export()                    # GET /api/export/csv returns valid CSV with correct columns
def test_global_search()                 # Search "target" returns matching application
def test_e2e_pipeline()                  # Full pipeline test from task 4.8
```

Status: `[x]`

---

### Verify Phase 4 Complete

```bash
# 1. All tests — all four phases
pytest tests/ -v --tb=short

# 2. E2E test specifically
pytest tests/test_e2e.py -v

# 3. Lighthouse performance
npx lighthouse http://localhost:3000 --output=json | python -c "
import json,sys; d=json.load(sys.stdin)
score = d['categories']['performance']['score'] * 100
print(f'Performance: {score}')
assert score >= 85, f'Score {score} below threshold'
"

# 4. Production smoke test (after deploy)
curl -f https://{your-railway-url}/api/health
```

When all pass: output exactly `PHASE_COMPLETE`

**Phase 4 Status: `[x] Done`**

---

# HARDENING TRACK

## Sprint H1 — Auth & Security Hardening

**H1.4 — Per-user data isolation (GAP-005, GAP-006, GAP-007)**
- Added `user_id` ownership columns for core user-owned records via Alembic migration `020_add_user_id_to_core_tables.py`
- Enforced JWT-only access on user-owned routes that cannot be safely scoped with the shared API key
- Scoped user-owned reads and writes by `user_id`, including ownership checks on updates and cross-resource lookups
- Added regression coverage for cross-user isolation and shared-API-key rejection on user-owned endpoints

Status: `[x]`

---

---

## NOTES FOR CLAUDE CODE

- Update task status `[ ]` → `[x]` as each task completes.
- Update phase status at top of file when phase is verified.
- Do not skip verification steps and self-certify. Run the commands.
- If a task is blocked by a missing env var, stop and output what is needed. Do not proceed with mocked values in production code.
- If a test is failing after 5+ attempts with the same approach, try a fundamentally different implementation — not another variation of the same broken code.
- The spec (`docs/PRD.md`) is the authority on architecture. This file is the authority on task order and verification. When they conflict, flag it before proceeding.
