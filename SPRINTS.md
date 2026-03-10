# AppTrail — Sprint Plan

Each sprint is a self-contained unit of work with clear deliverables and a definition of done. Sprints are ordered by dependency and priority.

---

## Sprint 1: Dead UI Fixes ✅ COMPLETE
**Goal:** Every button in the app either works or doesn't exist. Zero silent no-ops.

### Tasks
1. **AddJobModal** — Create modal component (company, role, URL, status fields). Wire "+ Add Job" button in KanbanBoard to open it. Form submits to POST `/api/jobs`. Show success/409 conflict feedback.
2. **Inline Edit: Notes** — KanbanBoard "Edit" button + "Click to add notes" placeholder toggle to textarea. Save on blur/enter via PATCH `/api/jobs/{id}` with `notes`. Show save indicator.
3. **Inline Edit: Description** — Same pattern for job description section. PATCH with `description_text`.
4. **Apply on Company Site** — JobSearch modal button: `window.open(selectedJob.url, '_blank')`. Guard for missing URL.
5. **Mark as Resolved** — Add `resolved` boolean to EmailEvent model (default False). Alembic migration. PATCH `/api/emails/{id}` already exists — add `resolved` to accepted fields. Wire Conversations button. Resolved threads move to bottom or hide.
6. **Disable Send Reply** — Replace Conversations "Send Reply" button with disabled state + tooltip: "Coming soon — outbound email is in development." Remove the silent no-op.
7. **Disable Draft Follow-up** — Same treatment for "Draft Follow-up with AI" button. Disabled + tooltip.
8. **Filters button** — Remove the Filters button from JobSearch for now. Add back when filter backend exists.
9. **Take Action button** — Wire to `window.open(email.actionUrl)` if `action_url` exists. Otherwise hide the button.

### Definition of Done
- All 9 items addressed
- No button in the app silently does nothing
- Pytest passes (migration + new resolved field)
- Manual click-through of every button confirms behavior

### Files Touched
- `dashboardv2/src/components/KanbanBoard.tsx` (tasks 1-3)
- `dashboardv2/src/components/JobSearch.tsx` (tasks 4, 8)
- `dashboardv2/src/components/Conversations.tsx` (tasks 5-7)
- `dashboardv2/src/components/EmailFeed.tsx` (task 9)
- `backend/main.py` (task 5 — add resolved to PATCH)
- `backend/models.py` (task 5 — add resolved column)
- `backend/alembic/versions/005_*.py` (task 5 — migration)
- New: `dashboardv2/src/components/AddJobModal.tsx` (task 1)

---

## Sprint 2: Company Entity + Knowledge Graph Foundation ✅ COMPLETE
**Goal:** Companies become first-class entities. Every job, contact, and email links to a company record.

### Tasks
1. **Company model** — New `Company` table in `models.py`: id (UUID), domain (unique), name, logo_url, industry, size, ats_platform, first_seen_at, last_activity_at.
2. **Alembic migration** — Create company table. Add nullable `company_id` FK to Application, Contact, EmailEvent.
3. **Company upsert service** — `backend/services/company_service.py`: `upsert_company(domain)` — creates or updates company record. Uses `company_identity.py` for name/logo. Called on job save, email sync, contact search.
4. **Backfill script** — `scripts/backfill_companies.py`: scan existing Application.company + EmailEvent.sender_domain, extract unique domains, create company records, populate FKs.
5. **Wire into ingestion** — POST `/api/jobs`: after creating application, upsert company from job URL domain, set `application.company_id`. `poll_gmail.py`: on email sync, upsert company from sender_domain, set `email_event.company_id`. `/api/contacts/find`: upsert company from domain, set `contact.company_id`.
6. **Company endpoints** — GET `/api/companies` (list with job count, contact count, email count). GET `/api/companies/{domain}` (full company profile: jobs, contacts, recent emails).
7. **Company stats** — Computed fields: total_jobs_seen, total_contacts via SQL aggregation in endpoints (not stored — derived from FKs).

### Definition of Done
- Company table exists with migration
- All new jobs/emails/contacts auto-link to a company record
- GET `/api/companies` returns company list with counts
- GET `/api/companies/{domain}` returns full profile
- Backfill script works against test DB
- All existing tests pass + new company tests

### Files Touched
- `backend/models.py` (Company model, FKs)
- `backend/alembic/versions/006_*.py` (migration)
- New: `backend/services/company_service.py`
- New: `scripts/backfill_companies.py`
- `backend/main.py` (new endpoints + wire upsert into existing endpoints)
- `backend/tasks/poll_gmail.py` (wire company upsert)
- `backend/services/company_identity.py` (may extend)
- New: `tests/backend/test_company.py`

---

## Sprint 3: Role Taxonomy & Classification ✅ COMPLETE
**Goal:** Every job gets classified into an umbrella role category. Pipeline filterable by category.

### Tasks
1. **RoleUmbrella model** — New table: id, name, aliases (JSON array), typical_skills (JSON array), parent_id (self-FK for hierarchy). Seed with ~50 categories across engineering, data, product, design, marketing, finance, operations.
2. **Alembic migration** — Create role_umbrella table. Add nullable `umbrella_id` FK to Application.
3. **Seed data script** — `scripts/seed_umbrellas.py`: insert initial umbrella categories with known aliases.
4. **Role classifier service** — `backend/services/role_classifier.py`: Haiku LLM call with umbrella list in system prompt. Input: title + description snippet. Output: umbrella_id + confidence. Fallback: keyword matching against aliases.
5. **Wire into job save** — POST `/api/jobs`: after parse, classify role → set `application.umbrella_id`. Also classify on job search results for display.
6. **Backfill existing applications** — Script to classify all existing applications.
7. **Pipeline filter** — GET `/api/jobs` accepts optional `umbrella_id` filter. Frontend: dropdown filter on KanbanBoard.
8. **Frontend display** — Show umbrella category badge on job cards.

### Definition of Done
- Umbrella table seeded with 50+ categories
- Every new job gets classified on save
- Pipeline filterable by umbrella category
- Tests for classifier (fallback + mapping)

### Files Touched
- `backend/models.py` (RoleUmbrella model, Application.umbrella_id)
- `backend/alembic/versions/007_*.py`
- New: `backend/services/role_classifier.py`
- New: `scripts/seed_umbrellas.py`
- `backend/main.py` (wire classifier, add filter param)
- `dashboardv2/src/components/KanbanBoard.tsx` (filter dropdown, badge)
- New: `tests/backend/test_role_classifier.py`

---

## Sprint 4: Tech Stack Extraction ✅ COMPLETE
**Goal:** Every job description gets parsed for tech stack mentions. Companies build aggregate tech profiles.

### Tasks
1. **Tech extraction service** — `backend/services/tech_extractor.py`: keyword-based extraction from job descriptions. Curated list of ~200 technologies (languages, frameworks, tools, cloud platforms). Returns array of matched tech names.
2. **Application.tech_stack column** — JSON array on Application model. Alembic migration.
3. **Wire into job save** — POST `/api/jobs`: after parse, extract tech stack from description_text, store on application.
4. **Company tech profile** — New table `company_tech_profile` (company_id FK, tech_name, mention_count, last_seen_at). Aggregation endpoint: GET `/api/companies/{domain}/tech`.
5. **Backfill** — Script to extract tech from all existing application descriptions.
6. **Frontend** — Show tech stack tags on job cards and job detail modal. Show company tech profile on company detail (when built).

### Definition of Done
- Tech extracted from every job description on save
- Company tech profiles aggregate from their jobs
- Tech tags visible on job cards
- Tests for extraction logic

### Files Touched
- New: `backend/services/tech_extractor.py`
- `backend/models.py` (tech_stack column, CompanyTechProfile table)
- `backend/alembic/versions/008_*.py`
- `backend/main.py` (wire extraction, new endpoint)
- `dashboardv2/src/components/KanbanBoard.tsx` (tech tags)
- New: `tests/backend/test_tech_extractor.py`

---

## Sprint 5: Resume Intelligence ✅ COMPLETE
**Goal:** Users upload a resume, system extracts structured profile, and scores match against jobs.

### Tasks
1. **UserProfile model** — New table: id, user_id FK, raw_text, skills (JSON), education (JSON), experience_years, tools (JSON), certifications (JSON), created_at, updated_at.
2. **Resume parser service** — `backend/services/resume_parser.py`: PDF text extraction (pdfplumber). Haiku LLM call to extract structured fields. Returns UserProfile data.
3. **Upload endpoint** — POST `/api/resume/upload`: accepts PDF file, parses, creates/updates UserProfile. Returns parsed profile for user confirmation.
4. **Match scoring service** — `backend/services/match_scorer.py`: compare UserProfile.skills against job description extracted requirements (from tech_extractor). Returns 0-100 score with breakdown (skills %, experience %, education %).
5. **Match endpoint** — GET `/api/jobs/{id}/match`: returns match score + breakdown for authenticated user.
6. **Gap analysis** — Part of match response: list of required skills user is missing, transferable skills to highlight.
7. **Frontend** — Resume upload page/modal in profile. Match score badge on job cards (color-coded: green 80+, yellow 50-79, red <50). Match detail in job modal.

### Definition of Done
- User can upload PDF resume
- Profile extracted and stored
- Match scores appear on job cards
- Gap analysis shown in job detail
- Tests for parser and scorer

### Files Touched
- `backend/models.py` (UserProfile)
- `backend/alembic/versions/009_*.py`
- New: `backend/services/resume_parser.py`
- New: `backend/services/match_scorer.py`
- `backend/main.py` (upload + match endpoints)
- `dashboardv2/src/components/KanbanBoard.tsx` (match score badge)
- New: `dashboardv2/src/components/ResumeUpload.tsx`
- New: `tests/backend/test_resume.py`

### Dependencies
- Sprint 4 (tech extraction — used for skill matching)

---

## Sprint 6: Onboarding Flow ✅ COMPLETE
**Goal:** New users get guided through setup instead of landing on an empty pipeline.

### Tasks
1. **User preferences columns** — Add to User model: onboarding_complete (bool), preferred_locations (JSON), preferred_remote_type (text), target_salary_min (int), target_salary_max (int). Migration.
2. **User role interests table** — `user_role_interest` (user_id, umbrella_id) many-to-many.
3. **Preferences endpoints** — POST `/api/profile/preferences` (save onboarding choices), GET `/api/profile/preferences`.
4. **Onboarding component** — Multi-step modal: (1) Select target role categories from umbrellas, (2) Dream companies, (3) Location/remote/salary preferences, (4) Resume upload (reuse Sprint 5 component).
5. **Auto-show** — If `user.onboarding_complete === false`, show onboarding modal after login. Skip button available.

### Definition of Done
- New users see onboarding modal on first login
- Preferences saved to backend
- Returning users skip onboarding
- Can be re-accessed from profile/settings

### Dependencies
- Sprint 3 (role taxonomy — umbrella picker)
- Sprint 5 (resume upload — step 4)

### Files Touched
- `backend/models.py` (User columns, UserRoleInterest)
- `backend/alembic/versions/010_*.py`
- `backend/main.py` (preferences endpoints)
- New: `dashboardv2/src/components/OnboardingModal.tsx`
- `dashboardv2/src/components/LoginPage.tsx` (trigger onboarding)

---

## Sprint 7: Dead Application Detection ✅ COMPLETE
**Goal:** Detect when job postings are taken down and alert users.

### Tasks
1. **Application columns** — Add: listing_alive (bool, default True), listing_last_checked (datetime), listing_died_at (datetime). Migration.
2. **Dead app checker task** — `backend/tasks/check_dead_apps.py`: Celery Beat daily task. For active applications (saved/applied/interviewing), HEAD request to job_url. Check for 404, "position filled" text, redirect to generic careers page. Platform-specific detection (Greenhouse 404, Lever "closed" banner, Workday removal). Max 50 per run, 2-4s random delay.
3. **Wire into Celery Beat** — Add to `celery_app.py` schedule.
4. **Frontend indicator** — Dead application badge on job cards. Warning banner in job detail modal: "This posting may no longer be active."

### Definition of Done
- Daily task checks active application URLs
- Dead postings detected and flagged
- Visual indicator on dashboard
- Tests for detection logic (mock HTTP responses)

### Files Touched
- `backend/models.py` (Application columns)
- `backend/alembic/versions/011_*.py`
- New: `backend/tasks/check_dead_apps.py`
- `backend/celery_app.py` (beat schedule)
- `dashboardv2/src/components/KanbanBoard.tsx` (dead badge)
- New: `tests/backend/test_dead_apps.py`

---

## Sprint 8: ATS Decode Ring ✅ COMPLETE
**Goal:** Aggregate behavioral patterns per ATS platform and surface platform-specific intelligence.

### Tasks
1. **ATS behavior table** — New table: id, platform, metric_name, metric_value (float), sample_size (int), last_updated. Migration.
2. **ATS intelligence service** — `backend/services/ats_intelligence.py`: aggregation queries over EmailEvent + Application. Compute per-platform: avg response days, rejection rate, ghosting rate (no response in 14+ days), auto-email ratio.
3. **Aggregation task** — Celery Beat weekly task to recompute ATS metrics.
4. **Endpoint** — GET `/api/intelligence/ats/{platform}` returns behavioral profile.
5. **Frontend** — ATS insight tooltip on job cards: "Greenhouse companies typically respond in 5 days" based on the job's source platform.

### Definition of Done
- ATS metrics computed from existing email/application data
- Platform profiles accessible via API
- Insights shown on job cards
- Tests for aggregation logic

### Dependencies
- Sprint 2 (company entity — links to ATS platform)

### Files Touched
- `backend/models.py` (AtsBehavior)
- `backend/alembic/versions/012_*.py`
- New: `backend/services/ats_intelligence.py`
- `backend/celery_app.py` (beat schedule)
- `backend/main.py` (endpoint)
- `dashboardv2/src/components/KanbanBoard.tsx` (tooltip)
- New: `tests/backend/test_ats_intelligence.py`

---

## Sprint 9: Network Warm Path Detection ✅ COMPLETE
**Goal:** Before applying cold, discover existing connections at target companies via Gmail history.

### Tasks
1. **WarmConnection model** — New table: id, user_id FK, company_domain, contact_email, contact_name, email_count (int), last_interaction_at, discovered_at. Migration.
2. **Warm path service** — `backend/services/warm_path.py`: Query Gmail API by company domain (`from:*@domain OR to:*@domain`). Count interactions, extract contact names. Store discovered connections.
3. **Wire into job save** — On POST `/api/jobs`, fire async background task to scan for warm paths at the new company's domain.
4. **Endpoint** — GET `/api/jobs/{id}/warm-paths` returns warm connections for that job's company.
5. **Frontend** — "Warm Connections" section in job detail modal. Shows contacts with interaction count and last date. "Reach Out" button (links to compose when outbound email is built, otherwise mailto: link).

### Definition of Done
- Warm paths discovered on job save
- Connections shown in job detail
- Tests with mocked Gmail API responses

### Dependencies
- Sprint 2 (company entity — domain matching)

### Files Touched
- `backend/models.py` (WarmConnection)
- `backend/alembic/versions/013_*.py`
- New: `backend/services/warm_path.py`
- `backend/main.py` (endpoint + wire into job save)
- `dashboardv2/src/components/KanbanBoard.tsx` (warm connections section)
- New: `tests/backend/test_warm_path.py`

---

## Sprint 10: Contacts Network Page ✅ COMPLETE
**Goal:** Dedicated page showing all contacts across all sources as a unified network view.

### Tasks
1. **Network aggregation endpoint** — GET `/api/network`: query Contact table + unique EmailEvent senders. Dedupe by email address. Return unified list with: name, email, title, company, source (hunter/email/warm_path), last_interaction_at, email_count, linked applications.
2. **Contact detail endpoint** — GET `/api/network/{email}`: full contact profile — all emails exchanged, linked applications, company info, interaction timeline.
3. **NetworkPage component** — Card grid layout. Each card: avatar initial, name, title, company logo, source badge, last interaction date. Click to expand detail panel.
4. **Detail panel** — Email history with this person, linked applications, company info, "Start Conversation" button (mailto: until outbound email Sprint 12 is built).
5. **Sidebar integration** — Add "Network" tab to Sidebar between Conversations and JobSearch.
6. **Search/filter** — Search by name or company. Filter by source, company.

### Definition of Done
- Network page shows all contacts from all sources
- Contact detail shows full interaction history
- Searchable and filterable
- New sidebar tab

### Dependencies
- Sprint 2 (company entity — company_id on contacts)

### Files Touched
- `backend/main.py` (network endpoints)
- New: `dashboardv2/src/components/NetworkPage.tsx`
- `dashboardv2/src/components/Sidebar.tsx` (new tab)
- `dashboardv2/src/lib/api.ts` (network API functions)
- `dashboardv2/src/types.ts` (NetworkContact type)

---

## Sprint 11: Response Time Intelligence + Smart Alerts ✅ COMPLETE
**Goal:** Track company response patterns and surface actionable alerts.

### Tasks
1. **Response time tracking** — Add `first_response_days` (int) to Application. On email match in `email_matcher.py`, compute days between `applied_at` and first email's `received_at`. Store on application.
2. **Company response aggregation** — In company endpoints, include avg_response_days computed from applications at that company.
3. **Alert model** — New table: id, user_id FK, alert_type, title, body, action_url, read (bool), created_at. Migration.
4. **Alert endpoints** — GET `/api/alerts` (with `?unread=true`), PATCH `/api/alerts/{id}` (mark read), GET `/api/alerts/count` (unread count).
5. **Alert generation** — In `check_followups` task: create alert when marking follow_up_due. In `check_dead_apps`: create alert when listing dies. In warm path discovery: create alert when warm connections found.
6. **Frontend alerts** — Bell icon in sidebar with unread badge count. Alert dropdown panel showing recent alerts. Click to navigate to relevant item.

### Definition of Done
- Response times tracked per application
- Alerts generated from follow-ups, dead apps, warm paths
- Bell icon with badge count in sidebar
- Alert dropdown with navigation

### Dependencies
- Sprint 7 (dead app detection — generates alerts)
- Sprint 9 (warm paths — generates alerts)

### Files Touched
- `backend/models.py` (Application.first_response_days, Alert)
- `backend/alembic/versions/014_*.py`
- `backend/services/email_matcher.py` (compute response days)
- `backend/tasks/check_followups.py` (create alerts)
- `backend/tasks/check_dead_apps.py` (create alerts)
- `backend/main.py` (alert endpoints)
- `dashboardv2/src/components/Sidebar.tsx` (bell icon + badge)
- New: `dashboardv2/src/components/AlertPanel.tsx`

---

## Sprint 12: Outbound Email + Reply ✅ COMPLETE
**Goal:** Users can send emails and reply to conversations from within the app.

### Tasks
1. **Gmail send scope** — Add `gmail.send` to OAuth scopes in `gmail_auth.py`. Handle scope upgrade for existing users.
2. **Email sender service** — `backend/services/email_sender.py`: compose + send via Gmail API. Create local EmailEvent with `is_from_user=True`. Support reply threading (thread_id, In-Reply-To, References headers).
3. **Send endpoint** — POST `/api/emails/send`: accepts to, subject, body, optional application_id, optional reply_to_message_id. Upserts contact from recipient. Links to application.
4. **Compose modal component** — Reusable modal: To (autocomplete from contacts), Subject, Body textarea. On reply: pre-fill To, `Re: subject`, thread context.
5. **Wire reply buttons** — Conversations.tsx "Send Reply": open compose modal pre-filled. Re-enable the button (undo Sprint 1 disable). EmailFeed: add reply option in detail view.
6. **Wire "Start Conversation"** — Network page contact cards: "Start Conversation" opens compose pre-filled with contact email.

### Definition of Done
- Users can compose and send emails from the app
- Replies thread correctly in Gmail
- Sent emails appear in conversation threads
- Contact auto-created on send
- Tests with mocked Gmail API

### Dependencies
- Sprint 1 (disabled reply buttons — re-enable)
- Sprint 10 (network page — start conversation button)

### Files Touched
- `backend/services/gmail_auth.py` (add send scope)
- New: `backend/services/email_sender.py`
- `backend/main.py` (send endpoint)
- New: `dashboardv2/src/components/ComposeModal.tsx`
- `dashboardv2/src/components/Conversations.tsx` (wire reply)
- `dashboardv2/src/components/NetworkPage.tsx` (wire start conversation)
- `dashboardv2/src/lib/api.ts` (sendEmail function)
- New: `tests/backend/test_email_sender.py`

---

## Sprint 13: Interview Calendar ✅ COMPLETE
**Goal:** Built-in calendar for tracking interviews with Google Calendar integration.

### Tasks
1. **Interview model** — New table: id, application_id FK, user_id FK, interview_type (phone/technical/onsite/panel), scheduled_at, duration_minutes, interviewer_name, interviewer_email, location_or_link, notes, outcome (pending/passed/failed), created_at. Migration.
2. **Google Calendar scope** — Add `calendar.readonly` + `calendar.events` to OAuth. New service `backend/services/calendar_sync.py`: read events, detect interview-related entries, create Interview records.
3. **Email → calendar detection** — Extend email classifier to extract datetime from interview_request emails. Endpoint: POST `/api/interviews/from-email/{email_id}` — creates interview from classified email.
4. **Interview CRUD endpoints** — POST/GET/PATCH/DELETE `/api/interviews`. GET `/api/interviews/upcoming`.
5. **Calendar component** — Week/month view using FullCalendar.js or similar. Shows interviews color-coded by type. Click to view/edit details.
6. **Sidebar integration** — Add "Calendar" tab.

### Definition of Done
- Users can create/view/edit interviews
- Google Calendar events auto-detected
- Interview emails auto-suggest calendar entries
- Calendar view in dashboard

### Dependencies
- Sprint 12 (outbound email — interview confirmations)

### Files Touched
- `backend/models.py` (Interview)
- `backend/alembic/versions/015_*.py`
- New: `backend/services/calendar_sync.py`
- `backend/services/email_classifier.py` (datetime extraction)
- `backend/main.py` (interview endpoints)
- New: `dashboardv2/src/components/Calendar.tsx`
- `dashboardv2/src/components/Sidebar.tsx` (calendar tab)

---

## Sprint 14: AI-Drafted Communications ✅ COMPLETE
**Goal:** AI generates context-aware draft emails for follow-ups, introductions, and replies.

### Tasks
1. **Draft writer service** — `backend/services/draft_writer.py`: Sonnet LLM call. Input: conversation history, application context (stage, company, role), contact info, draft type (follow_up/introduction/reply). Output: subject + body draft.
2. **Draft endpoint** — POST `/api/drafts/generate`: accepts application_id, contact_email, draft_type. Returns generated draft.
3. **Wire into compose modal** — "Suggest Draft" button in ComposeModal. Loads AI-generated content into body field. User edits before sending.
4. **Wire "Draft Follow-up with AI"** — Re-enable Conversations button (undo Sprint 1 disable). Clicks → generates draft → opens compose modal with draft pre-filled.
5. **Tone matching** — Service analyzes previous email exchange tone (formal/casual) and matches.

### Definition of Done
- AI generates contextual email drafts
- Drafts load into compose modal for editing
- "Draft Follow-up" button works in Conversations
- Tests for draft generation (mocked LLM)

### Dependencies
- Sprint 12 (compose modal — where drafts are loaded)

### Files Touched
- New: `backend/services/draft_writer.py`
- `backend/main.py` (draft endpoint)
- `dashboardv2/src/components/ComposeModal.tsx` (suggest draft button)
- `dashboardv2/src/components/Conversations.tsx` (re-enable draft button)
- New: `tests/backend/test_draft_writer.py`

---

## Sprint 15: Knowledge Graph Retrieval Layer ✅ COMPLETE
**Goal:** AI can access full company context through structured retrieval functions.

### Tasks
1. **Knowledge graph service** — `backend/services/knowledge_graph.py`: `get_company_context(domain)` assembles full company context — identity, jobs, contacts, emails, tech stack, ATS behavior, response time, warm paths.
2. **Company detail page** — Frontend component showing full company profile: all graph data in one view. Accessible from job cards, email cards, network page.
3. **Endpoint** — GET `/api/companies/{domain}/context` returns assembled graph context.
4. **Sidebar company list** — Optional: show tracked companies in sidebar or as a dedicated tab.

### Definition of Done
- `get_company_context()` returns complete assembled profile
- Company detail page shows all available data
- Accessible from multiple entry points

### Dependencies
- Sprint 2 (company entity)
- Sprint 4 (tech stack)
- Sprint 8 (ATS behavior)
- Sprint 9 (warm paths)
- Sprint 11 (response time)

### Files Touched
- New: `backend/services/knowledge_graph.py`
- `backend/main.py` (context endpoint)
- New: `dashboardv2/src/components/CompanyDetail.tsx`
- `dashboardv2/src/components/KanbanBoard.tsx` (link to company detail)

---

## Sprint 16: Salary Intelligence ✅ COMPLETE
**Goal:** Extract salary data from job descriptions and show personalized ranges.

### Tasks
1. **Salary extraction** — Extend tech_extractor or new service: regex + LLM to find salary ranges in description_text. Parse min/max/currency/period.
2. **Salary data storage** — New columns on Application: salary_min, salary_max, salary_currency, salary_period. Or new salary_data table. Migration.
3. **Aggregation** — Group by umbrella category + location. Compute percentiles (25th, 50th, 75th).
4. **Personalized ranges** — Adjust based on user profile (YOE, skills) from Sprint 5.
5. **Geographic demand** — Track where umbrella roles are posted most. Endpoint: GET `/api/intelligence/salary/{umbrella_id}`.
6. **Frontend** — Salary range badge on job cards. Salary insights panel in analytics.

### Definition of Done
- Salary extracted from descriptions where available
- Aggregated by role category and location
- Visible on job cards and in analytics

### Dependencies
- Sprint 3 (role taxonomy — grouping)
- Sprint 5 (resume intelligence — personalization)

### Files Touched
- New or extend: `backend/services/salary_extractor.py`
- `backend/models.py` (salary columns)
- `backend/alembic/versions/016_*.py`
- `backend/main.py` (salary intelligence endpoints)
- `dashboardv2/src/components/KanbanBoard.tsx` (salary badge)
- `dashboardv2/src/components/Analytics.tsx` (salary insights)

---

## Sprint 17: Extension Intelligence ✅ COMPLETE
**Goal:** Chrome extension auto-detects application submissions and passively tracks career page browsing.

### Tasks
1. **Form submission detection** — Add listeners to `content.js` for Greenhouse/Lever/Workday confirmation pages. On detect: send message to background → PATCH `/api/jobs/{id}` with status "applied".
2. **Passive career page tracking** — New `tracker.js` content script. Use `webNavigation` API to log career page visits. Store in `chrome.storage.local` with domain + timestamp.
3. **Browsing nudge** — Side panel shows: "You've visited Stripe's careers page 4 times. Want to track this company?"
4. **Sync to backend** — Optional: POST career page visits to backend `CompanyVisit` table for dashboard display.
5. **Job save enrichment** — On save, extract additional data: salary if visible in page, team/department.

### Definition of Done
- Extension detects when user submits an ATS application
- Career page visits tracked and surfaced
- Nudge shown after repeated visits

### Files Touched
- `extension/content.js` (form detection)
- New: `extension/tracker.js`
- `extension/manifest.json` (new content script, permissions)
- `extension/sidepanel.js` (browsing nudge)
- `extension/background.js` (message handling)

---

## Sprint 18: Interview Prep / Second Brain ✅ COMPLETE
**Goal:** Structured interview notes with pattern detection across applications.

### Tasks
1. ✅ **InterviewNote model** — New table: id, interview_id FK, application_id FK, questions_asked (text), went_well (text), to_improve (text), overall_feeling (text: great/good/okay/poor), created_at. Migration.
2. ✅ **Note endpoints** — CRUD for `/api/interviews/{id}/notes`, plus past-due and patterns endpoints.
3. ✅ **Post-interview prompt** — After interview scheduled_at passes, show prompt in dashboard: "How did your interview at {company} go?"
4. ✅ **Pre-interview prep** — Before upcoming interview, surface past notes for that company via `/api/interviews/{id}/prep`.
5. ✅ **Pattern analysis** — Aggregate outcomes by interview type and company via `/api/interviews/patterns`.

### Definition of Done
- ✅ Users can log structured interview notes
- ✅ Notes surfaced before next interview at same company
- ✅ Basic pattern analysis available

### Dependencies
- Sprint 13 (interview calendar — interview records)

### Files Touched
- `backend/models.py` (InterviewNote)
- `backend/alembic/versions/017_*.py`
- `backend/main.py` (note endpoints)
- `dashboardv2/src/components/Calendar.tsx` (note prompt + prep surface)

---

## Sprint 19: Notification Channels ✅ COMPLETE
**Goal:** SMS for urgent alerts and weekly email digest.

### Tasks
1. ✅ **Notification preferences** — NotificationPreference model (already existed from migration 019). GET/PUT `/api/notifications/preferences` endpoints.
2. ✅ **Twilio SMS integration** — `backend/services/sms_sender.py`: send SMS via Twilio REST API for urgent alerts (offers, interview requests). Auto-triggered on alert creation.
3. ✅ **Weekly digest task** — `backend/tasks/send_weekly_digest.py`: Celery Beat weekly task. Aggregates week's stats (apps submitted, interviews, responses, follow-ups). Preview endpoint at `/api/digest/preview`.
4. ✅ **Settings page** — `dashboardv2/src/components/Settings.tsx` with SMS toggle, phone input, weekly digest toggle.

### Definition of Done
- ✅ Users can opt into SMS for urgent alerts
- ✅ Weekly digest assembled and delivered as in-app alert (extensible to email)
- ✅ Settings page for preferences

### Dependencies
- Sprint 11 (alert system — triggers SMS)

### Files Touched
- `backend/models.py` (NotificationPreference)
- `backend/alembic/versions/018_*.py`
- New: `backend/services/sms_sender.py`
- New: `backend/tasks/send_weekly_digest.py`
- `backend/celery_app.py` (beat schedule)
- `backend/main.py` (preference endpoints)
- New: `dashboardv2/src/components/Settings.tsx`

---

## Sprint 20: Resume Tailoring (Pro Feature) ✅ COMPLETE
**Goal:** AI generates tailored resume versions per job application.

### Tasks
1. ✅ **ResumeDraft model** — Already existed from migration 019 (id, user_id FK, application_id FK, original_text, tailored_text, changes_summary, created_at).
2. ✅ **Tailoring service** — `backend/services/resume_tailor.py`: Sonnet LLM call with critical constraint: never invents experience, only reframes. Fallback template when LLM unavailable.
3. ✅ **Tailor endpoint** — POST `/api/resume/tailor/{application_id}`: generates tailored version from user profile or custom text.
4. ✅ **Diff view** — `ResumeTailor.tsx` side-by-side original vs. tailored with changes summary and keyword alignments.
5. ✅ **Text export** — Download buttons for both original and tailored versions as .txt files.
6. ✅ **Draft history** — GET `/api/resume/drafts/{app_id}`, GET/DELETE individual drafts, chronological list with clickable cards.

### Definition of Done
- ✅ AI generates tailored resume per job
- ✅ Diff view for review
- ✅ Text export (downloadable .txt)
- ✅ Draft history per application

### Dependencies
- Sprint 5 (resume intelligence — user profile)

### Files Touched
- `backend/models.py` (ResumeDraft)
- `backend/alembic/versions/019_*.py`
- New: `backend/services/resume_tailor.py`
- `backend/main.py` (tailor endpoint)
- New: `dashboardv2/src/components/ResumeTailor.tsx`

---

## Future Sprints (Requires Scale)

### Sprint 21: Cross-User Intelligence
- Anonymized opt-in data sharing
- Company response rate aggregates
- Similar profile matching
- *Prerequisite: 1000+ users*

### Sprint 22: Mobile App
- React Native (Expo)
- Core screens: Pipeline, Email Feed, Conversations, Calendar
- Push notifications via Firebase
- Offline support

### Sprint 23: Monetization
- Tiered pricing (Free/Pro/Enterprise)
- Stripe integration for payments
- Feature gating per tier
- Usage tracking (LLM calls/month)

---

## Sprint Dependency Graph

```
Sprint 1 (Dead UI) ──────────────────────────────────────────────────┐
Sprint 2 (Company Entity) ───┬── Sprint 8 (ATS) ───┐               │
                              ├── Sprint 9 (Warm Path) ─┤               │
                              └── Sprint 10 (Network) ──┤               │
Sprint 3 (Role Taxonomy) ─┬── Sprint 6 (Onboarding) │               │
                           └── Sprint 16 (Salary) ──┘               │
Sprint 4 (Tech Stack) ────── Sprint 5 (Resume) ──┬── Sprint 6      │
                                                   ├── Sprint 16     │
                                                   └── Sprint 20     │
Sprint 7 (Dead Apps) ─────── Sprint 11 (Alerts) ─── Sprint 19      │
Sprint 11 (Alerts) ◀──────── Sprint 9 + Sprint 7                    │
Sprint 12 (Outbound Email) ◀── Sprint 1 + Sprint 10 ────────────────┘
Sprint 13 (Calendar) ─────── Sprint 18 (Interview Prep)
Sprint 14 (AI Drafts) ◀───── Sprint 12
Sprint 15 (Graph Layer) ◀─── Sprint 2 + 4 + 8 + 9 + 11
```

---

*Created: 2026-03-09*
