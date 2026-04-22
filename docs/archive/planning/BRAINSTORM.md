# AppTrail — Feature Roadmap & Vision

## Core Vision
The **operating system for job searching**. Every job seeker generates the same data exhaust — emails, job pages visited, applications submitted, conversations had. Nobody stitches it together into a living, intelligent system. AppTrail does.

---

## 🚨 PRIORITY: Dead UI Fixes (Must fix before new features)

The following buttons/actions exist in the frontend but are NOT wired to any backend functionality. These need to be fixed first — users see these, click them, and nothing happens.

### CRITICAL — User-visible broken functionality

**1. Conversations: "Send Reply" button** — [Conversations.tsx:315-325](dashboardv2/src/components/Conversations.tsx#L315-L325)
- User types a reply, clicks Send, text disappears, **nothing is sent**
- Comment in code: `// In a real app, this would trigger an API call to send the email`
- **Fix:** Wire to POST `/api/emails/send` (§9b Outbound Email). Needs `gmail.send` scope + `email_sender.py` service. Until outbound email is built, either **remove the reply UI** or **show a "coming soon" tooltip** — a silent no-op is the worst option.

**2. KanbanBoard: "+ Add Job" button** — [KanbanBoard.tsx:87-89](dashboardv2/src/components/KanbanBoard.tsx#L87-L89)
- Primary CTA button, **no onClick handler at all**
- Backend POST `/api/jobs` exists and works — just needs a modal
- **Fix:** Create `AddJobModal` component with form fields (company, role, job URL, status). Wire button to open modal, form submits to POST `/api/jobs`.

**3. Conversations: "Draft Follow-up with AI" button** — [Conversations.tsx:262](dashboardv2/src/components/Conversations.tsx#L262)
- Shows when `requiresFollowUp` is true, **no onClick handler**
- **Fix:** Wire to POST `/api/drafts/generate` (§9d AI Drafts). Until AI drafts are built, remove the button or disable with tooltip.

**4. Conversations: "Mark as Resolved" button** — [Conversations.tsx:336-338](dashboardv2/src/components/Conversations.tsx#L336-L338)
- **No onClick handler**, no backend field for resolved status
- **Fix:** Add `resolved` boolean column to EmailEvent (or a thread-level concept). Add PATCH endpoint. Wire button.

### HIGH — Features half-implemented

**5. KanbanBoard: "Edit" button on Notes section** — [KanbanBoard.tsx:257](dashboardv2/src/components/KanbanBoard.tsx#L257)
- Shows "Edit" text link, **no onClick handler**
- Backend PATCH `/api/jobs/{id}` supports `notes` field — just needs inline edit UI
- The "Click to add notes" placeholder div (line 264) also has `cursor-text` CSS but **no onClick**
- **Fix:** Toggle to inline textarea on click, save on blur/enter via PATCH.

**6. KanbanBoard: "Edit" button on Job Description** — [KanbanBoard.tsx:277](dashboardv2/src/components/KanbanBoard.tsx#L277)
- Same pattern — "Edit" link with **no onClick handler**
- Backend supports `description_text` via PATCH
- **Fix:** Same inline edit pattern as notes.

**7. JobSearch: "Filters" button** — [JobSearch.tsx:96-99](dashboardv2/src/components/JobSearch.tsx#L96-L99)
- Button with Filter icon, **no onClick handler**
- Backend `/api/search` only supports `q` and `location` params
- **Fix:** Either build filter dropdown (location, salary, date) with backend support, or remove button until filters exist.

**8. JobSearch: "Apply on Company Site" button** — [JobSearch.tsx:257-259](dashboardv2/src/components/JobSearch.tsx#L257-L259)
- In job detail modal, **no onClick handler**
- Job URL is available in the data
- **Fix:** Simple `window.open(selectedJob.url, '_blank')` — trivial fix.

### MEDIUM — Niche features

**9. EmailFeed: "Take Action" button** — [EmailFeed.tsx:238-240](dashboardv2/src/components/EmailFeed.tsx#L238-L240)
- Only shows for `action_item` classification emails, **no onClick handler**
- No backend action tracking system
- **Fix:** For now, could open the `action_url` if available from email classification. Full fix requires action item tracking system.

### Summary

| # | Component | Button | Severity | Fix Difficulty |
|---|-----------|--------|----------|----------------|
| 1 | Conversations | Send Reply | 🔴 CRITICAL | Hard (needs gmail.send) |
| 2 | KanbanBoard | + Add Job | 🔴 CRITICAL | Medium (modal + existing API) |
| 3 | Conversations | Draft Follow-up with AI | 🟡 HIGH | Hard (needs AI draft service) |
| 4 | Conversations | Mark as Resolved | 🟡 HIGH | Easy (new field + PATCH) |
| 5 | KanbanBoard | Edit Notes | 🟡 HIGH | Easy (inline edit + existing API) |
| 6 | KanbanBoard | Edit Description | 🟡 HIGH | Easy (inline edit + existing API) |
| 7 | JobSearch | Filters | 🟡 HIGH | Medium (UI + backend params) |
| 8 | JobSearch | Apply on Company Site | 🟡 HIGH | Trivial (window.open) |
| 9 | EmailFeed | Take Action | 🟠 MEDIUM | Medium (needs design decision) |

**Recommendation:** Fix #2, #4, #5, #6, #8 immediately (all easy/trivial with existing backend). Disable or remove #1, #3 until outbound email (§9b) is built. Decide on #7 and #9 scope.

---

## 1. Email Intelligence Pipeline ✅ BUILT (Phase 5A)

**Status:** Complete. All components implemented and tested (24 tests).

**What's built:**
- Haiku LLM classifier (7 categories: interview_request, rejection, offer, action_item, job_update, conversation, not_relevant)
- Multipart MIME parser with HTML stripping, signature/footer removal
- Company identity layer (60+ domain overrides, Clearbit logos, platform domain blocklist)
- "Not in pipeline" detection with one-click add
- User feedback loop (sender domain blocklist from dismissals)
- Conversation auto-detection and routing
- Gmail sync every 15 min via Celery Beat

**Existing code:** `email_classifier.py`, `email_parser.py`, `company_identity.py`, `email_matcher.py`, `email_filter.py`, `poll_gmail.py`

---

## 2. Extension Intelligence (Priority: HIGH)

**Status:** Partially built. Manual save + multi-platform detection works. Auto-detection features are new.

**What's built:** Chrome extension with Manifest V3, Side Panel API, platform detection (Greenhouse, Lever, Workday, Ashby, LinkedIn, Indeed), job parsing via backend, one-click pipeline add.

**What's new:**

### 2a. Application Form Submission Detection
- Detect when user submits an application on ATS pages (Greenhouse, Lever, Workday)
- Listen for form submission events or URL changes (e.g., `/confirmation`, `/thank-you`)
- Auto-update application status from "saved" → "applied" with timestamp
- **Data source:** Extension content script DOM observation. No new API needed.
- **Implementation:** Add form submission listeners to `content.js` for known ATS patterns. Send message to background → PATCH `/api/jobs/{id}` with `status: "applied"`.

### 2b. Passive Career Page Tracking
- Track which company career pages user browses without explicit save
- Aggregate: "You've looked at Stripe 4 times this week but haven't applied"
- Nudge: "Want to track this company?"
- **Data source:** Extension `webNavigation` API, match against known career page URL patterns.
- **Implementation:** New `tracker.js` content script. Store page visits in `chrome.storage.local` with domain + timestamp. Aggregate in side panel. Optional: sync to backend `CompanyVisit` table for dashboard display.

### 2c. Job Save Enrichment
- On every job save, extract additional data from the page: tech stack mentions, salary if visible, team/department, hiring manager name
- Company enrichment: Clearbit API for logo/size/industry/funding
- **Data source:** Job page DOM (already parsed by scraper). Clearbit API for company metadata.
- **Implementation:** Extend `scraper.py` to extract tech stack keywords from description. Add `tech_stack[]` column to Application model. Clearbit call in `company_identity.py`.

---

## 3. Role Taxonomy & Classification (Priority: HIGH)

**Status:** Not built. No role classification exists in codebase.

### The Problem
Job titles are chaos. "Data Analyst", "Business Intelligence Analyst", "Reporting Analyst", "Analytics Engineer", "Decision Scientist" — all basically the same role at different companies.

### Role Umbrella System
- Define ~50-100 umbrella categories (Data Analyst, Software Engineer, Product Manager, etc.) each with a known alias set
- LLM classifier takes `{title, description, company}` → assigns to umbrella + confidence score
- Runs on every job save (extension) AND every job listing from search
- Alias map grows from real data: "Goldman Sachs calls Data Analysts 'Strats Analysts'" — knowledge nobody else has

### Implementation Plan
1. **New DB table:** `role_umbrella` (id, name, aliases[], typical_skills[], typical_tools[], industry_context, parent_id for hierarchy)
2. **New DB column:** `Application.umbrella_id` (FK to role_umbrella)
3. **New service:** `backend/services/role_classifier.py` — Haiku call with umbrella list in system prompt, returns umbrella_id + confidence
4. **Integration points:** Called on POST `/api/jobs` (after parse), on job search results, on extension save
5. **Seed data:** Start with ~50 umbrellas across engineering, data, product, design, marketing, finance, operations, healthcare
6. **Data source:** Job title + description text (already have both from scraper). No new ingestion needed.
7. **Frontend:** Filter pipeline by umbrella category. Group search results by umbrella.

---

## 4. Resume Intelligence (Priority: HIGH)

**Status:** Not built. No resume handling in codebase.

### Upload & Parse
- User uploads PDF resume in-app
- LLM extracts structured data: skills, education, years of experience, past roles, certifications, tools/technologies
- Store as structured user profile — skills as searchable tags

### Match Scoring Engine
- For every job posting: compare user profile against parsed job requirements
- Generate match score (0-100) with breakdown: skills match, experience match, education match
- Surface score on every job card in pipeline and search results

### Gap Analysis
- "This role requires Snowflake but you don't list it"
- "Want to highlight your BigQuery experience as a transferable skill?"
- Missing skills flagged so user knows how to position themselves

### Resume Tailoring (AI Service — Pro tier)
- LLM reads job description + user's base resume → generates tailored version
- **Critical constraint:** NEVER invents experience — only reframes existing truth
- Diff review UI, save as dated draft, PDF export

### Implementation Plan
1. **New DB tables:** `user_profile` (id, user_id, raw_text, parsed_json, skills[], education[], experience_years, tools[]), `resume_draft` (id, user_id, application_id, original_text, tailored_text, created_at)
2. **New service:** `backend/services/resume_parser.py` — PDF text extraction (PyPDF2/pdfplumber) + Haiku structured extraction
3. **New service:** `backend/services/match_scorer.py` — Compare user_profile.skills against job description extracted requirements
4. **New endpoint:** POST `/api/resume/upload` — accepts PDF, returns parsed profile
5. **New endpoint:** GET `/api/jobs/{id}/match` — returns match score + breakdown
6. **New endpoint:** POST `/api/resume/tailor` — generates tailored resume for specific job
7. **Data source:** User-uploaded PDF (new). Job descriptions (already stored in `Application.description_text`).

---

## 5. Dead Application Detection (Priority: MEDIUM-HIGH)

**Status:** Not built. We have `job_url` on every application but never re-check it.

### Concept
Job postings disappear — they get filled, the req closes, the page 404s. Users waste time hoping to hear back on dead roles. We can detect this.

### How It Works
- Periodically re-visit `job_url` for all active applications (status: saved, applied, interviewing)
- Check for signals: HTTP 404, redirect to generic careers page, "position filled" text, listing removed from company board
- Alert user: "This posting at Stripe appears to have been taken down. The role may be filled."
- Track posting lifecycle: when first seen → when disappeared

### Implementation Plan
1. **New Celery task:** `backend/tasks/check_dead_apps.py` — Daily Beat task, checks active application URLs
2. **New DB columns:** `Application.listing_alive` (bool, default True), `Application.listing_last_checked` (datetime), `Application.listing_died_at` (datetime)
3. **Logic:** HTTP HEAD request to `job_url`. If 404 → mark dead. If 200, check for "position has been filled", "no longer accepting", redirect to careers homepage. Platform-specific: Greenhouse returns 404, Lever shows "position closed" banner, Workday removes from search.
4. **Rate limiting:** Max 50 checks per task run. Randomized 2-4s delays (per CLAUDE.md rule 8). Rotate User-Agent.
5. **Frontend:** Dead application badge/indicator on job card. "This posting may no longer be active" warning.
6. **Data source:** `Application.job_url` (already stored). Just need HTTP requests — no new API.

---

## 6. ATS Decode Ring (Priority: MEDIUM-HIGH)

**Status:** Not built. We detect ATS platforms in `detector.js` and `scraper.py` but don't analyze platform-specific behavior patterns.

### Concept
Each ATS (Greenhouse, Lever, Workday, etc.) has distinct behavioral patterns — email formats, response timing, status update styles. By tracking these patterns across all emails we process, we build an "ATS decode ring" that helps users interpret signals.

### What We Can Learn Per ATS
- **Email patterns:** Greenhouse sends from `no-reply@greenhouse.io`, Lever from `notifications@lever.co`. Different subject line formats.
- **Response timing:** Average days between application → first response, by platform
- **Rejection style:** Greenhouse sends immediate auto-reject vs. Workday ghosting for weeks
- **Status signals:** "Your application has been reviewed" on Lever means human eyes; on Workday it's often automated
- **Interview scheduling:** Which platforms use Calendly links vs. inline scheduling vs. manual email

### Implementation Plan
1. **New DB table:** `ats_behavior` (id, platform, metric_name, metric_value, sample_size, last_updated)
2. **Aggregate from existing data:** Query `EmailEvent` grouped by `sender_domain` → map to known ATS platforms → compute avg response times, rejection rates, email patterns
3. **New service:** `backend/services/ats_intelligence.py` — Aggregation queries + pattern detection
4. **New endpoint:** GET `/api/intelligence/ats/{platform}` — returns behavioral profile for a platform
5. **Frontend:** On job cards, show ATS-specific tips: "Workday applications typically take 14 days for first response" or "Greenhouse companies reject faster — no response in 7 days is unusual"
6. **Data source:** All existing `EmailEvent` records (sender_domain, classification, received_at) + `Application` (source platform, applied_at, status). **Already have this data** — just need aggregation logic.

---

## 7. Network Warm Path Detection (Priority: MEDIUM-HIGH)

**Status:** Not built. We have Hunter.io contacts and Gmail email history but don't cross-reference them.

### Concept
Before a user applies cold to a company, scan their existing email history and contacts for warm connections. "You exchanged emails with someone@stripe.com 6 months ago — want to reach out before applying cold?"

### How It Works
- When user saves a new job or views a company, scan their Gmail history for any prior email exchanges with that company's domain
- Cross-reference against contacts table (Hunter.io results)
- Surface: "You have existing connections at this company"
- Show contact details, last interaction date, relationship strength (number of emails exchanged)

### Implementation Plan
1. **Gmail history scan:** On job save, query Gmail API for messages matching the company's email domain (e.g., `from:*@stripe.com OR to:*@stripe.com`). Already have Gmail OAuth tokens stored.
2. **New DB table:** `warm_connection` (id, user_id, company_domain, contact_email, contact_name, email_count, last_interaction_at, discovered_at)
3. **New service:** `backend/services/warm_path.py` — Queries Gmail API by domain, counts interactions, stores discovered connections
4. **New endpoint:** GET `/api/jobs/{id}/warm-paths` — returns warm connections for a job's company
5. **Integration:** Call on POST `/api/jobs` (async background task after job created). Also callable on-demand from dashboard.
6. **Frontend:** "Warm Connections" section on job detail view. Shows contacts with interaction history and "Reach Out" button.
7. **Data source:** Gmail API (already authenticated — `GmailToken` table has refresh tokens). Hunter.io contacts (already in `Contact` table). Company domain (already extracted by `company_identity.py`). **All data sources already available.**

---

## 8. Timing Intelligence (Priority: MEDIUM)

**Status:** Partially built. We have `check_followups` Celery task that flags 7+ day old applications. Response time tracking and adaptive cadence are new.

### 8a. Response Time Intelligence
- Track when companies historically respond (derived from email timestamps vs. application date)
- "DraftKings typically responds in 5 days"
- "You applied 10 days ago — similar applicants heard back in 7 days. Consider following up."
- **Data source:** `Application.applied_at` + `EmailEvent.received_at` (both already stored). Just need aggregation.
- **Implementation:** New column `Application.first_response_days` (computed on email match). Aggregation query by company domain. Surface in frontend.

### 8b. Job Posting Lifecycle Tracking
- Track when roles are posted vs closed (ties into Dead Application Detection §5)
- "This role has been open for 60 days — they might be desperate or the req is frozen"
- Alert when a role you saved gets taken down
- **Data source:** `Application.created_at` (first seen) + dead app checks (§5). SerpAPI results timestamps.
- **Implementation:** Extends dead app detection. Add `Application.posting_first_seen` and use `listing_died_at` from §5.

### 8c. Adaptive Scraping Cadence
- Default: scrape tracked company career pages once daily
- If a company is ramping (3+ new posts detected in 48h) → increase to every 4 hours
- **Data source:** Job search results over time. Need a `CompanyPostingVelocity` tracking mechanism.
- **Implementation:** New Celery task that monitors posting counts per company. Adjusts scrape frequency dynamically.

---

## 9. Contacts Network & Relationship Intelligence (Priority: MEDIUM-HIGH)

**Status:** Partially built. We have `Contact` table with Hunter.io data, outreach tracking, and response tracking. Network view, people graph, outbound email, and auto-drafts are all new.

### 9a. Contacts / Network Page
A dedicated page — like a LinkedIn connections view — that surfaces all your contacts as first-class entities instead of burying them inside individual applications.

- **Network list view:** Card per contact showing name, title, company, source (Hunter, email, warm path)
- **Contact detail panel:** Click a card → expands to show:
  - Full email history with this person (pulled from `EmailEvent` by sender_email)
  - Last interaction date + interaction count
  - Which application(s) they're linked to
  - Company info (logo, other contacts at same company)
  - "Start Conversation" button → opens compose (§9c)
  - LinkedIn profile link (if available from Hunter)
- **Grouping:** By company, by recency, by relationship strength (email count)
- **Search/filter:** By name, company, role title
- **Data source:** `Contact` table (Hunter.io), `EmailEvent` sender data, warm path connections (§7). **All already stored** — just need a unified view.
- **Implementation:**
  1. New endpoint GET `/api/network` — aggregates contacts + unique email senders into unified contact list, deduped by email address
  2. New endpoint GET `/api/network/{contact_id}` — returns full contact profile with email history
  3. New frontend component `NetworkPage.tsx` — card grid with expandable detail panel
  4. New sidebar tab: "Network" (between Conversations and JobSearch)

### 9b. Outbound Email / Compose
Right now we're read-only on Gmail — we ingest but never send. Adding compose/send makes the app a complete communication hub.

- **"Start Conversation" button:** On contact cards, network page, and job detail views
- **Reply buttons:** Existing reply/respond buttons in EmailFeed and Conversations components get wired to the same send service — currently they're UI-only with no backend send capability
- **Compose modal:** To (pre-filled from contact or original sender on reply), Subject (pre-filled with `Re:` on reply), Body with AI draft suggestion. On reply: includes `In-Reply-To` and `References` headers so Gmail threads the response correctly.
- **After send:** Email gets indexed into our system — the recipient gets added/updated as a contact, linked to the relevant company and application
- **Thread tracking:** Outbound emails create a conversation thread. Replies come in through Gmail sync and get matched to the thread via `thread_id`.
- **Data source:** Gmail API `send` scope (new — currently only have `readonly`).
- **Implementation:**
  1. Add `gmail.send` scope to OAuth flow in `gmail_auth.py`
  2. New service `backend/services/email_sender.py` — compose + send via Gmail API, create local EmailEvent record with `is_from_user=True`. Supports both new compose and reply (with `thread_id`, `In-Reply-To` header).
  3. New endpoint POST `/api/emails/send` — accepts to, subject, body, optional application_id, optional reply_to_message_id (for threading)
  4. On send: upsert contact record (name from email, company from domain via `company_identity.py`), create EmailEvent, link to application if provided
  5. Frontend: Compose modal component, accessible from Network page, Conversations tab, and job detail view. **Wire existing reply buttons in EmailFeed.tsx and Conversations.tsx** to open compose modal pre-filled with original sender, `Re: subject`, and thread context.

### 9c. People Graph
- Map contacts per company: who you've interacted with, who referred you, who ghosted you
- "You know 2 people at Coinbase through previous conversations — want to reach out before applying cold?"
- Track recruiter movements across companies (same email appearing at different company domains over time)
- **Data source:** `Contact` table, `EmailEvent` sender data, warm path connections (§7). All already stored.
- **Implementation:** Aggregation endpoint GET `/api/network/graph` that returns contacts grouped by company with interaction metadata. Optional: frontend network visualization (d3.js force graph).

### 9d. AI-Drafted Communications
- Follow-up emails based on conversation context and tone matching
- Suggested LinkedIn connection messages
- Context-aware: knows application stage, last conversation, company details
- **Data source:** `EmailEvent.body` for tone, `Application.status` for stage context, `Contact` for recipient info. All available.
- **Implementation:** New service `backend/services/draft_writer.py`. Sonnet-level LLM call with conversation history + application context. New endpoint POST `/api/drafts/generate`. Feeds into compose modal (§9b) as suggested draft.

---

## 10. Company Tech Stack Intelligence (Priority: MEDIUM-HIGH)

**Status:** Not built. We store `description_text` on applications but don't extract or aggregate tech mentions.

### How It Works
- Parse every job description for tech stack mentions (languages, frameworks, tools, platforms)
- Build per-company tech stack profile from aggregate of all their postings
- "Through BofA's last 20 data analyst postings, they prefer Snowflake, Tableau, Python"

### Cross-Company & Per-Role Patterns
- "Fintech companies hiring Data Analysts prefer SQL + Python + Snowflake 73% of the time"
- Required vs nice-to-have skill frequency per umbrella category
- Tech stack trends by industry, over time

### Implementation Plan
1. **Tech extraction:** LLM or keyword-based extraction from `Application.description_text`. Store as `Application.tech_stack[]` (JSONB array).
2. **New DB table:** `company_tech_profile` (id, company_domain, tech_name, mention_count, last_seen_at)
3. **Aggregation service:** `backend/services/tech_intelligence.py` — queries across applications grouped by company, computes frequency.
4. **New endpoints:** GET `/api/intelligence/tech/{company_domain}`, GET `/api/intelligence/tech/trends`
5. **Data source:** `Application.description_text` (already stored on every scraped/saved job). **No new ingestion needed** — just parsing existing data.

---

## 11. Salary Intelligence (Priority: MEDIUM-HIGH)

**Status:** Not built. We have a `salary` field on Application but it's manually entered and rarely populated.

### Per-Role Salary Ranges
- Parse salary data from job descriptions (many list ranges or use phrases like "competitive", "$X-$Y")
- Map to umbrella role categories (requires §3 Role Taxonomy)
- Personalized: adjust range based on YOE, skills, location from user profile (requires §4 Resume Intelligence)

### Geographic Demand Intelligence
- Track where specific umbrella roles are being posted most heavily
- Heat map view: role demand by metro area
- Remote vs on-site ratio trends per role umbrella

### Skill Premium Analysis
- Which skills command higher salaries within an umbrella category
- "Adding Snowflake certification could increase offers by ~12%"

### Implementation Plan
1. **Salary extraction:** Regex + LLM from job descriptions for salary range (min, max, currency, period). Store on `Application` or new `salary_data` table.
2. **Aggregation:** Group by umbrella category (§3) + location. Compute percentiles.
3. **Dependencies:** Needs Role Taxonomy (§3) for meaningful grouping. Needs Resume Intelligence (§4) for personalization.
4. **Data source:** `Application.description_text` (already stored). SerpAPI results sometimes include salary. **Partial data available** — salary coverage depends on how many postings include ranges (~30-40% of US postings do).

---

## 12. Interview Calendar (Priority: MEDIUM-HIGH)

**Status:** Not built. No calendar functionality in codebase.

### Built-in Interview Calendar
- Dedicated calendar view for interview scheduling
- Shows: company, role, interview type (phone/technical/onsite), date/time, interviewer name

### Google Calendar Integration
- Already have Google OAuth — just need to add Calendar scope
- AI scans calendar events for interview-related entries
- Two-way sync: AppTrail ↔ Google Calendar

### Email → Calendar Auto-Detection
- LLM scans `interview_request` classified emails for date/time mentions
- "We'd like to schedule a call for Tuesday at 2pm EST" → suggest adding to calendar
- One-click confirm

### Implementation Plan
1. **New DB table:** `interview` (id, application_id, user_id, interview_type, scheduled_at, duration_minutes, interviewer_name, interviewer_email, location/link, notes, outcome, created_at)
2. **Google Calendar:** Add `calendar.readonly` + `calendar.events` scopes to OAuth. New service `backend/services/calendar_sync.py`.
3. **Date extraction:** Extend email classifier to extract datetime from interview_request emails. Use Python `dateutil` for parsing.
4. **New endpoints:** CRUD for `/api/interviews`, GET `/api/interviews/upcoming`, POST `/api/interviews/from-email/{email_id}`
5. **Frontend:** New Calendar component (week/month view). FullCalendar.js or similar React library.
6. **Data source:** Google Calendar API (new scope needed), `EmailEvent` with classification=interview_request (already have). **Calendar scope is incremental — same OAuth flow, just add scope.**

---

## 13. Smart Alerts System (Priority: MEDIUM)

**Status:** Partially built. Follow-up reminders exist (`check_followups` task). Smart alerts and in-app notifications are new.

### Alert Types
- "You applied to Stripe 10 days ago and haven't heard back — consider following up" *(partially built: `follow_up_due` flag exists)*
- "3 new jobs posted at a company you're tracking"
- "This posting appears to have been taken down" (from §5 Dead App Detection)
- "You have a warm connection at this company" (from §7 Network Warm Path)
- Follow-up reminders based on stage and company response patterns (from §8a)

### Implementation Plan
1. **New DB table:** `alert` (id, user_id, alert_type, title, body, action_url, read, created_at)
2. **Alert generation:** Each feature (§5, §7, §8) creates alerts when relevant conditions are met
3. **New endpoint:** GET `/api/alerts` (with unread count), PATCH `/api/alerts/{id}` (mark read)
4. **Frontend:** Bell icon in sidebar with badge count. Alert dropdown/panel.
5. **Data source:** All internal — generated from existing application/email/contact data.

---

## 14. Notification Channels (Priority: MEDIUM)

**Status:** Not built. No SMS, no email digest.

### SMS (Time-Sensitive Only)
- Interview requests, offer notifications, approaching deadlines
- User opt-in required. No marketing.
- **Implementation:** Twilio API integration. New `notification_preferences` table. Triggered by alert system (§13).

### Weekly Summary Email
- Stats: applications submitted, interviews scheduled, responses received
- Highlights + actionable links back into app
- **Implementation:** Celery Beat weekly task. SendGrid/SES for email delivery. HTML template.

### In-App Notifications
- Badge counts on sidebar tabs (unread emails, alerts, follow-ups due)
- **Implementation:** Extend existing sidebar with count badges from API.

---

## 15. Onboarding Flow (Priority: MEDIUM)

**Status:** Not built. Users go straight to empty pipeline after OAuth.

### First-Time User Experience
1. Role interests → multi-select from umbrella categories (requires §3)
2. Company interests → free-text with autocomplete
3. Preferences → location, remote/hybrid/onsite, salary range
4. Resume upload → parse → extract skills → confirm (requires §4)

### Implementation Plan
1. **New DB columns on User:** `onboarding_complete`, `preferred_locations[]`, `preferred_remote_type`, `target_salary_min/max`
2. **New DB table:** `user_role_interest` (user_id, umbrella_id) — many-to-many
3. **Frontend:** Multi-step onboarding modal after first login. Stores preferences via new endpoints.
4. **Data source:** User input. Umbrella categories from §3.

---

## 16. Second Brain / Interview Prep (Priority: LOW-MEDIUM)

**Status:** Not built. `Application.notes` exists but is free-text, not structured interview notes.

### Concept
- After each interview, prompt user to log structured notes (questions asked, what went well, what to improve)
- Before next interview, surface past notes for that company
- Pattern detection: which company types / role types you get furthest with

### Implementation Plan
1. **New DB table:** `interview_note` (id, interview_id, application_id, questions_asked, went_well, to_improve, overall_feeling, created_at)
2. **Tie to Interview Calendar (§12):** After interview datetime passes, prompt for notes
3. **Pattern analysis:** Aggregate outcomes by umbrella category, company size, industry
4. **Data source:** User input (new). Interview outcomes from §12.

---

## 17. Mobile App (Priority: MEDIUM)

**Status:** Not built.

### Why Mobile Matters
- Job seekers check email on phone constantly — need updates and quick responses
- Interview calendar access anywhere
- Push notifications for time-sensitive items

### Approach
- React Native (Expo) sharing API client logic with dashboardv2
- Core screens: Pipeline (kanban), Email Feed, Conversations, Calendar, Profile
- Offline-capable: cache pipeline state locally, sync on reconnect
- Push notifications via Firebase/APNs

### Implementation Plan
1. **Prerequisite:** Backend API is already REST — mobile client consumes same endpoints
2. **Auth:** Same JWT flow — Google OAuth in mobile browser → deep link back with token
3. **New:** Push notification service (Firebase Cloud Messaging). New `device_token` table.
4. **Data source:** Same backend API. No new data ingestion.

---

## 18. Two-Sided Value Philosophy (Priority: FUTURE)

**Status:** Guiding principle, not a feature to build now.

### Core Principle
AppTrail makes it better for BOTH applicants AND recruiters. We never auto-fill or auto-submit applications. We never spam recruiters. We never share individual data without consent.

### For Recruiters (Future)
- Anonymized candidate intent signals ("X candidates are actively looking at your company")
- AppTrail candidates are "verified active" — organized, responsive, serious
- Hiring analytics: time-to-fill, pipeline health

### Implementation: Requires scale first. See FUTURE_IDEAS.md for parking lot items.

---

## 19. Internal Knowledge Graph (Priority: MEDIUM — foundational layer)

**Status:** Not built. We have the raw data across multiple tables but no unified graph structure or AI retrieval layer.

### Architecture: Company as Hub Node

The knowledge graph is a **relational graph modeled in Postgres** (not a separate graph DB — we don't need heavy traversal queries yet). Company is the central hub — almost everything connects through it.

```
                        ┌──────────────┐
                        │   UMBRELLA   │  (Data Analyst, SWE, PM...)
                        │    ROLE      │
                        └──────┬───────┘
                               │ categorizes
                               ▼
┌───────────┐   employs   ┌──────────┐   applied_to   ┌──────────┐
│  COMPANY  │────────────▶│   JOB    │◀───────────────│   USER   │
│  (node)   │             │(Application)              │ (Profile)│
└─────┬─────┘             └────┬─────┘                └────┬─────┘
      │                        │                           │
      │ has_contacts      generates_emails            has_skills
      ▼                        ▼                           ▼
┌───────────┐           ┌──────────┐               ┌──────────┐
│  CONTACT  │◀─────────▶│  EMAIL   │               │  SKILL   │
│  (Person) │ sent/recv │ (Event)  │               │(from resume)
└─────┬─────┘           └────┬─────┘               └──────────┘
      │                      │
      │ interactions    classified_as
      ▼                      ▼
┌───────────┐           ┌──────────┐
│INTERACTION│           │  ATS     │
│(email hist│           │BEHAVIOR  │
│ outreach) │           │(platform)│
└───────────┘           └──────────┘
```

### Company Node (Central Entity)
Each company becomes a rich node aggregating everything we know:
- **Identity:** name, domain, logo (from `company_identity.py` — already built)
- **Jobs:** all applications at this company (from `Application` table — already stored)
- **Contacts:** people we know there (from `Contact` table + email senders — already stored)
- **Email history:** all emails from this domain (from `EmailEvent.sender_domain` — already stored)
- **Tech stack:** extracted from their job descriptions (§10 — needs extraction logic)
- **ATS platform:** which ATS they use (from `Application.source` — already stored)
- **Response patterns:** avg response time, ghosting rate (§6, §8a — needs aggregation)
- **Hiring velocity:** how many jobs they're posting and how fast (§8c — needs tracking)

### How AI Accesses the Graph
The LLM doesn't query the graph directly. We build **structured retrieval functions** that assemble context:

```python
# When AI needs context about a company:
def get_company_context(company_domain: str) -> dict:
    return {
        "company": get_company_info(domain),           # name, logo, industry
        "jobs": get_applications_by_company(domain),    # all jobs at this company
        "contacts": get_contacts_by_company(domain),    # people you know there
        "emails": get_emails_by_domain(domain),         # email history
        "tech_stack": get_tech_profile(domain),          # extracted tech
        "ats_behavior": get_ats_behavior(platform),     # platform patterns
        "response_time": get_avg_response(domain),      # how fast they reply
        "warm_paths": get_warm_connections(domain),      # existing connections
    }
```

The AI reasons over the assembled JSON — it doesn't need to understand the schema.

### New DB Table: `company` (The Hub)
Right now companies exist implicitly (as strings on Application, domains on EmailEvent). We need a first-class Company entity:

| Column | Type | Source |
|--------|------|--------|
| id | UUID | auto |
| domain | text (unique) | extracted from emails/job URLs |
| name | text | from `company_identity.py` overrides or domain |
| logo_url | text | Clearbit |
| industry | text | Clearbit enrichment or LLM extraction |
| size | text | Clearbit (startup/mid/enterprise) |
| ats_platform | text | from Application.source |
| avg_response_days | float | computed from email timestamps |
| total_jobs_seen | int | count of Applications |
| total_contacts | int | count of Contacts |
| hiring_velocity | text | computed (ramping/stable/slowing) |
| first_seen_at | datetime | earliest Application.created_at |
| last_activity_at | datetime | latest email or job |

### Implementation Plan
1. **New DB table:** `company` as described above. Alembic migration.
2. **Backfill service:** Scan existing `Application` and `EmailEvent` tables, extract unique company domains, create company records, link via FK.
3. **Add FKs:** `Application.company_id`, `Contact.company_id`, `EmailEvent.company_id` (all nullable, backfilled from domain matching)
4. **Company upsert on ingestion:** Every job save, email sync, and contact search upserts the company record.
5. **Retrieval service:** `backend/services/knowledge_graph.py` — `get_company_context()` assembles full context for AI consumption.
6. **New endpoints:** GET `/api/companies` (list with stats), GET `/api/companies/{domain}` (full company profile with graph data)
7. **Frontend:** Company detail page accessible from job cards, email cards, and network page. Shows all graph data in one view.
8. **Data source:** **All data already exists** across Application, Contact, EmailEvent, and company_identity.py. Just need a unified table + aggregation.

---

## 20. Cross-User Intelligence (Priority: LOW — requires scale + consent)

**Status:** Not built. Requires significant user base.

### Privacy-First Design
- All data: explicit opt-in + fully anonymized
- Only aggregates with minimum thresholds

### Aggregate Insights
- Company response rates, ghosting rates, hiring freeze signals
- Recruiter reputation scores
- Similar profile matching: "3 users with similar backgrounds got interviews here"

### Implementation Plan
1. **Prerequisites:** Scale (1000+ users), consent framework, anonymization layer
2. **New tables:** `anonymized_outcome` (hashed user, company, umbrella, stage_reached, days_to_response)
3. **Aggregation:** Batch job computing per-company stats with minimum sample thresholds
4. **Data source:** Internal application/email data. **Already have the raw data** — just need scale and consent infrastructure.

---

## 21. Monetization (Priority: FUTURE)

### Free Tier
- Manual tracking, basic email sync, 50 LLM classifications/month, basic pipeline view

### Pro Tier ($X/month)
- Unlimited LLM classification, smart alerts, resume tailoring, match scoring, ATS intelligence, warm path detection, interview calendar, outbound email compose

### Enterprise / Recruiter Flip
- Anonymized candidate intent signals, hiring analytics dashboard

---

## Build Order (Recommended)

### Phase 5A — Email Intelligence ✅ COMPLETE
1. LLM email classifier (Haiku) ✅
2. Full email body parsing ✅
3. Company identity layer ✅
4. "Not in pipeline" detection ✅
5. "Not job related" feedback ✅
6. Conversation auto-detection ✅

### 🚨 Phase 5A.1 — Dead UI Fixes (DO FIRST)
1. `AddJobModal` component + wire "+ Add Job" button (backend exists)
2. Inline edit for Notes + Description in KanbanBoard (backend exists)
3. `window.open(job.url)` for "Apply on Company Site" button (trivial)
4. `Mark as Resolved` — add `resolved` field to EmailEvent + PATCH endpoint + wire button
5. Disable/remove "Send Reply" button until outbound email (§9b) is built — silent no-op is unacceptable
6. Disable/remove "Draft Follow-up with AI" until AI drafts (§9d) are built
7. Decide on "Filters" button — build or remove
8. Decide on "Take Action" button — wire to `action_url` or remove

### Phase 5B — Extension Intelligence + Role Classification + Knowledge Graph Foundation
1. **Company table + backfill (§19)** — foundational: everything else references companies
2. Role umbrella classifier (§3) — Haiku call on every job save
3. Tech stack extraction from descriptions (§10)
4. Auto-detect application form submissions (§2a)
5. Company enrichment on save (§2c)
6. Passive career page browsing tracking (§2b)

### Phase 6 — Resume Intelligence + Onboarding
1. Resume upload + PDF parsing (§4)
2. LLM extraction → user profile (§4)
3. Match scoring engine (§4)
4. Gap analysis per application (§4)
5. Onboarding flow (§15)
6. Resume tailoring service — Pro tier (§4)

### Phase 7 — Network, Communication & Behavioral Intelligence
1. **Contacts network page (§9a)** — unified view of all contacts across sources
2. **Outbound email / compose (§9b)** — Gmail send scope + compose modal
3. Dead application detection (§5)
4. ATS decode ring (§6)
5. Network warm path detection (§7)
6. Response time tracking (§8a)
7. Smart alerts system (§13)
8. AI-drafted communications (§9d) — feeds into compose modal
9. Interview calendar + Google Calendar integration (§12)
10. Knowledge graph retrieval layer (§19) — `get_company_context()` for AI

### Phase 8 — Salary & Market Intelligence
1. Salary extraction from descriptions (§11)
2. Personalized salary ranges (§11)
3. Geographic demand mapping (§11)
4. Skill premium analysis (§11)

### Phase 9 — Scale Features, Mobile & Monetization
1. Cross-user anonymized insights (§20)
2. Mobile app (§17)
3. Notification channels — SMS + weekly email (§14)
4. Tiered pricing (§21)
5. Two-sided recruiter value (§18)

---

## Data Availability Summary

| Feature | Data Source | Status |
|---------|-----------|--------|
| Role Taxonomy (§3) | Job title + description | ✅ Already stored |
| Resume Intelligence (§4) | User-uploaded PDF | 🆕 New ingestion |
| Dead App Detection (§5) | Application.job_url | ✅ Already stored |
| ATS Decode Ring (§6) | EmailEvent + Application | ✅ Already stored |
| Network Warm Path (§7) | Gmail API + Contact table | ✅ Already authenticated |
| Response Time (§8a) | Application + EmailEvent timestamps | ✅ Already stored |
| Contacts Network (§9a) | Contact + EmailEvent tables | ✅ Already stored |
| Outbound Email (§9b) | Gmail API send scope | 🔑 New OAuth scope needed |
| Tech Stack (§10) | Application.description_text | ✅ Already stored |
| Salary (§11) | Job descriptions + SerpAPI | ⚠️ ~30-40% coverage |
| Interview Calendar (§12) | Google Calendar API | 🔑 New OAuth scope needed |
| Interview Prep (§16) | User input | 🆕 New ingestion |
| Knowledge Graph (§19) | All existing tables | ✅ Already stored (needs unification) |
| Cross-User (§20) | Internal data | ⏳ Needs scale |

---

*Last updated: 2026-03-09*
