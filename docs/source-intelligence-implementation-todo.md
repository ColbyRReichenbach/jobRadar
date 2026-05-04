# Source Intelligence Implementation TODO

This checklist implements `docs/source-intelligence-job-search-spec.md` in order. Each sprint must end with tests green. If any test or check fails, inspect the failing logs, make the smallest targeted fix, and rerun the same test set until green before moving on.

## Branch and Change Control

- [x] Start from the intended feature branch after current dirty work is committed or intentionally set aside.
- [x] Do not commit `.env`, secrets, screenshots, generated browser artifacts, or private interview-planning docs.
- [x] Keep `docs/ai-copilot-search-eval-plan.md` local only unless explicitly approved.
- [x] Add `docs/source-intelligence-job-search-spec.md` and this TODO doc only when the implementation branch is ready for documentation changes.
- [x] Use small commits by sprint or logical vertical:
  - `source-intel: add privacy data contracts`
  - `source-intel: harden application urls`
  - `source-intel: add url classifier`
  - `source-intel: add provider adapters`
  - `source-intel: add admin source dashboard`
- [x] Before every commit, run `git diff --check` and inspect `git status --short`.

## Required Defaults

- [x] `source_intelligence` consent defaults to `false` for existing and new users.
- [x] Private user workflow URL classification can run under existing core/Gmail consent.
- [x] Shared source writes require explicit `source_intelligence=true`.
- [x] Workday shared source verification defaults disabled.
- [x] Custom career-page crawling defaults disabled.
- [x] Broad search fallback obeys global and per-user caps.
- [x] Email tracking redirects are never network-fetched.

## Sprint 0: Privacy Retrofit For Existing URL Paths

Goal: close current privacy gaps before adding shared source intelligence.

### Backend Discovery

- [x] Inspect all current places that read, normalize, store, export, index, or display job/application URLs:
  - `backend/main.py`
  - `backend/tasks/poll_gmail.py`
  - Gmail body parsing helpers
  - application suggestion endpoints
  - application create/update endpoints
  - `/api/jobs/parse`
  - `backend/services/scraper.py` if present
  - search indexing tasks
  - export endpoints
  - frontend application forms
- [x] Identify every current use of first-URL regex extraction.
- [x] Identify every server-side URL fetch path and whether it bypasses `backend/services/url_safety.py`.
- [x] Identify current log redaction helpers and AI telemetry redaction paths.

### URL Safety Retrofit

- [x] Extend `backend/services/url_safety.py` with max response byte enforcement.
- [x] Ensure safe fetch behavior:
  - HTTPS only.
  - No URL credentials.
  - Reject localhost/private/link-local/reserved/metadata IPs.
  - Validate redirects before following.
  - No cookies.
  - Stable Opportunity Radar user agent.
  - Timeout required.
  - Max bytes required.
- [x] Retrofit `/api/jobs/parse` to use the safe fetch wrapper.
- [x] Remove or disable Playwright/browser automation from shared source verification paths.
- [x] Ensure AI fallback cannot fetch or summarize private/tokenized links.

### Existing Application URL Hardening

- [x] Add preliminary URL classifier/sanitizer call before saving `Application.job_url`.
- [x] Ensure private URLs are never saved into `Application.job_url`.
- [x] Ensure private URLs are not indexed into `SearchDocument`.
- [x] Ensure private URLs are not included in export payloads.
- [x] Ensure application suggestions do not choose the first URL blindly.
- [x] Ensure application suggestions choose the safest public posting URL or no URL.
- [x] Ensure `EmailEvent.action_url` is classified before being exposed or accepted.

### Tracking Redirect Rule

- [x] Implement offline-only redirect parameter extraction for known parameters:
  - `url`
  - `u`
  - `target`
  - `redirect`
  - `q`
- [x] Never issue HEAD/GET/preview requests to email tracking redirect URLs.
- [x] If destination cannot be extracted offline and safely classified, mark as private/unresolved.

### Logging Redaction

- [x] Expand redaction for:
  - `token`
  - `auth`
  - `session`
  - `jwt`
  - `candidate`
  - `candidateId`
  - `applicationId`
  - `profileId`
  - `magic`
  - `invite`
  - `interview`
  - scheduler URL patterns
  - `api_key`
  - `x-smarttoken`
- [x] Strip CR/LF from redacted evidence and provider error messages.
- [x] Do not log provider request URLs when credentials are query params.

### Sprint 0 Tests

- [x] Add/update unit tests proving private URLs cannot be stored in `Application.job_url`.
- [x] Add tests for scheduler, candidate-home, magic-login, token, `candidateId`, and `applicationId` URLs.
- [x] Add tests proving email tracking redirects are not network-fetched.
- [x] Add tests proving `/api/jobs/parse` rejects private/local/oversized/redirect-to-private URLs.
- [x] Add tests proving search indexing and exports contain only safe public URLs.
- [x] Run targeted backend tests for URL privacy and job parsing.
- [x] Run existing relevant tests:
  - `pytest tests/test_public_url_safety.py`
  - `pytest tests/test_search_security.py`
  - any application suggestion tests touched
- [x] Fix failures from logs and rerun until green.

## Sprint 1: Data Contracts, Consent, And Private Link Storage

Goal: create durable, secure data contracts without enabling shared source writes by default.

### Migration

- [x] Add Alembic revision `049_add_source_intelligence.py`.
- [x] Add `company_job_sources`.
- [x] Add `user_application_links`.
- [x] Add `source_discovery_events`.
- [x] Add `job_postings`.
- [x] Add `application_source_links`.
- [x] Add `source_verification_runs`.
- [x] Add `job_search_provider_usage`.
- [x] Add `source_intelligence` consent flag to the existing consent model.
- [x] Implement Postgres expression unique index or generated normalized key columns for `company_job_sources`.
- [x] Avoid relying only on SQLite behavior for migration correctness.

### Models

- [x] Add SQLAlchemy models for all new tables.
- [x] Add relationships where useful:
  - application to application source links
  - application source link to user application link
  - application source link to job posting
  - company job source to source verification runs
- [x] Ensure cascade/delete behavior matches the spec.
- [x] Add created/updated timestamp defaults using existing repo conventions.

### Crypto

- [x] Add source-link encryption helper with key-purpose separation from Gmail tokens.
- [x] Add keyed HMAC-SHA256 helper for URL hashes.
- [x] Add key version fields and helpers.
- [x] Add env var validation for:
  - `SOURCE_LINK_ENCRYPTION_KEY`
  - `SOURCE_LINK_ENCRYPTION_KEY_VERSION`
  - `SOURCE_LINK_HASH_KEY`
  - `SOURCE_LINK_HASH_KEY_VERSION`
- [x] In tests, provide deterministic test keys without using `.env`.
- [x] Never log plaintext raw URLs, encrypted values, or HMAC keys.

### Consent API And UI

- [x] Update `/api/consent` to include `source_intelligence`.
- [x] Default `source_intelligence=false`.
- [x] Update Settings UI with a Source Intelligence consent section.
- [x] Explain private vs shared data in user-facing language.
- [x] Add private-link management placeholder or basic list endpoint depending on implementation scope.
- [x] Update privacy policy copy if the repo maintains user-facing policy docs.

### Gmail Limited-Use Compliance

- [x] Add a visible UI disclosure for Gmail-derived source intelligence.
- [x] Ensure shared source writes require explicit consent.
- [x] Ensure admin views show only redacted/aggregate Gmail-derived metadata by default.
- [x] Add support/security/legal exception language or audit reason field before any user-specific admin access.

### Sprint 1 Tests

- [x] Add migration tests for Postgres or a CI migration job.
- [x] Add SQLite-safe model metadata tests only as supplementary coverage.
- [x] Add crypto tests:
  - encryption round trip
  - HMAC deterministic with same key
  - HMAC changes with key version/key
  - no plain SHA-256 behavior
- [x] Add consent tests:
  - default false
  - update true/false
  - shared source write blocked when false
- [x] Add API tests for admin redaction behavior.
- [x] Run:
  - `pytest tests/test_consent.py`
  - new source crypto/privacy tests
  - migration test job if available
- [x] Fix failures from logs and rerun until green.

## Sprint 2: URL Classifier, Sanitizer, And Email Href Extraction

Goal: create deterministic URL handling that all later source intelligence uses.

### Classifier Module

- [x] Add `backend/services/source_intelligence/url_classifier.py`.
- [x] Implement `ClassifiedUrl` dataclass.
- [x] Extract URLs from:
  - raw Gmail MIME HTML hrefs
  - raw Gmail plaintext bodies
  - `EmailEvent.action_url`
  - `EmailEvent.body`
  - `EmailEvent.snippet`
  - `EmailEvent.summary`
  - `EmailEvent.key_sentence`
  - `Application.job_url`
  - manual job URL fields
- [x] Normalize HTML entities and punctuation wrappers.
- [x] Classify link types:
  - public job posting
  - company career page
  - ATS job board
  - application status
  - interview scheduler
  - assessment
  - tracking redirect
  - magic login
  - candidate home
  - unknown
- [x] Detect private indicators in path/query/fragment.
- [x] Detect provider type and provider key when possible.

### Sanitizer Module

- [x] Add `backend/services/source_intelligence/url_sanitizer.py`.
- [x] Remove tracking params:
  - `utm_*`
  - `gh_src`
  - `source`
  - `ref`
  - `trk`
  - `campaign`
  - `email`
  - `mc_cid`
  - `mc_eid`
- [x] Reject or privatize token params:
  - `token`
  - `auth`
  - `jwt`
  - `session`
  - `candidate`
  - `candidateId`
  - `applicationId`
  - `magic`
  - `invite`
- [x] Normalize host and path.
- [x] Drop fragments unless explicitly allowlisted.
- [x] Preserve provider path information needed for public detail fetches.
- [x] Generate canonical public URL and keyed HMACs.
- [x] Fail closed to `private_user_only`, `rejected`, or `needs_review`.

### Gmail Integration

- [x] Modify Gmail sync to extract raw MIME hrefs before HTML stripping.
- [x] Preserve extracted candidate links as classified private records, not as raw email body text.
- [x] Keep existing display-safe email body behavior.
- [x] Write `user_application_links` records for classified links when allowed.
- [x] Do not block Gmail sync on source verification.

### Application Integration

- [x] Use classifier/sanitizer in application create/update.
- [x] Create `application_source_links` for private and public supporting records.
- [x] Set `Application.job_url` only when a safe public canonical URL exists.
- [x] Update application suggestions to pick safest public posting URL.
- [x] Ensure duplicate application logic still works when private URLs are excluded from `Application.job_url`.

### Sprint 2 Tests

- [x] Add `tests/test_source_url_classifier.py`.
- [x] Add `tests/test_source_url_sanitizer.py`.
- [x] Add `tests/test_source_email_url_extraction.py`.
- [x] Add fixtures for:
  - Greenhouse
  - Lever
  - Ashby
  - Workable
  - SmartRecruiters
  - Workday public posting
  - Workday candidate-home
  - iCIMS public page
  - Calendly/scheduler
  - assessment links
  - magic login
  - tracking redirect
  - tokenized query params
- [x] Add tests proving Gmail hrefs are extracted before HTML stripping.
- [x] Add tests proving no tracking redirect network request is made.
- [x] Add application create/update API tests for private URL rejection.
- [x] Run all new classifier/sanitizer tests and affected email/application tests.
- [x] Fix failures from logs and rerun until green.

## Sprint 3: Provider Base Contracts And Public Adapters

Goal: implement direct-source search for low-risk public providers before Workday.

### Base Package

- [x] Add `backend/services/job_sources/`.
- [x] Add `base.py` with:
  - `SourceConfig`
  - `SearchQuery`
  - `VerificationResult`
  - `NormalizedJobPosting`
  - adapter interface
- [x] Add provider-safe HTTP client wrapper using `url_safety`.
- [x] Add provider response normalization helpers.
- [x] Add provider-specific redaction helpers.

### Greenhouse Adapter

- [x] Parse `boards.greenhouse.io/{board}` and `job-boards.greenhouse.io/{board}`.
- [x] Verify public board through official job board API.
- [x] Fetch jobs.
- [x] Normalize title, company, location, URL, updated date, department if present.
- [x] Use `access_mode=public`.

### Lever Adapter

- [x] Parse `jobs.lever.co/{site}`.
- [x] Verify postings endpoint.
- [x] Fetch postings with JSON mode.
- [x] Normalize categories, location, commitment, team, hosted URL.
- [x] Use `access_mode=public`.

### Ashby Adapter

- [x] Parse `jobs.ashbyhq.com/{board}`.
- [x] Verify public posting API.
- [x] Fetch jobs.
- [x] Normalize compensation where present.
- [x] Use `access_mode=public`.

### Workable Adapter

- [x] Parse account from `apply.workable.com/{account}` and `{account}.workable.com`.
- [x] Verify `www.workable.com/api/accounts/{account}?details=true`.
- [x] Fetch public published jobs only.
- [x] Normalize URL, application URL, department, location, workplace type, salary, shortcode.
- [x] Do not use `/spi/v3/jobs` without approved API key.
- [x] Use `access_mode=public` for verified published-job endpoint.

### Registry Writes

- [x] Add source registry upsert helper.
- [x] Add job posting upsert helper.
- [x] Add dedupe key generation.
- [x] Add `application_source_links` upsert helper.
- [x] Make all upserts idempotent.

### Sprint 3 Tests

- [x] Add mocked integration tests with `respx` or existing repo equivalent.
- [x] Test each adapter parse/verify/fetch/normalize flow.
- [x] Test provider timeout and 429 behavior.
- [x] Test redirect to private IP rejection.
- [x] Test oversized response rejection.
- [x] Test redacted metadata contains no tokens/raw private URLs.
- [x] Run:
  - provider adapter tests
  - `pytest tests/test_public_url_safety.py`
  - affected job search tests
- [x] Fix failures from logs and rerun until green.

## Sprint 4: Source Resolver, Search API, And Cost Caps

Goal: replace hardcoded search behavior with direct-first resolver behind a feature flag.

### Resolver

- [x] Add `backend/services/job_sources/resolver.py`.
- [x] Resolve query into company/role/location terms.
- [x] Find verified active sources for company/domain.
- [x] Query adapters only for allowed access modes:
  - `public`
  - `api_key` only when approved server credentials exist
- [x] Skip:
  - `unknown`
  - `blocked`
  - unapproved `credentialed`
  - unapproved `partner`
- [x] Fall back to broad provider only when direct sources are missing/stale/failed/blocked.
- [x] If broad provider returns ATS/company URLs, classify and enqueue verification candidates.
- [x] Return provider status and source summary.

### Broad Provider Usage

- [x] Add persistent usage enforcement using `job_search_provider_usage`.
- [x] Add keyed HMAC query hashes.
- [x] Enforce global monthly cap.
- [x] Enforce per-user monthly cap.
- [x] Track request mode and result count.
- [x] Show clear provider-limited response when capped or disabled.

### Search API

- [x] Preserve existing `/api/search` response fields:
  - `results`
  - `cached`
  - `provider_status`
- [x] Add `source_summary`.
- [x] Add richer result fields behind `JOB_SEARCH_DIRECT_SOURCES_ENABLED`.
- [x] Keep frontend compatibility while adding new fields.
- [x] Do not mix global `job_postings` with old `JobListing` cache long term.

### Role Matching

- [x] Add deterministic role matcher module.
- [x] Normalize titles.
- [x] Add role-family expansion for analyst/data/AI/ML/engineering roles.
- [x] Rank by title similarity, role family, skill/domain/location/freshness/source confidence.
- [x] Avoid over-expansion into unrelated analyst roles unless domain matches.

### Sprint 4 Tests

- [x] Add resolver tests:
  - direct source before SerpAPI
  - stale direct source falls back
  - blocked/unknown source skipped
  - unapproved credentialed source skipped
  - broad cap reached returns provider-limited state
- [x] Add usage cap tests:
  - per-user cap
  - global cap
  - query hash does not store raw query
- [x] Add role matcher tests for analyst expansion and over-expansion prevention.
- [x] Add API tests for `/api/search` response compatibility.
- [x] Run affected backend tests and frontend type checks if API types change.
- [x] Fix failures from logs and rerun until green.

## Sprint 5: Access-Mode Providers And Structured Data

Goal: add cautious support for ambiguous/credentialed providers and custom single-job pages.

### SmartRecruiters

- [x] Parse SmartRecruiters career and API URLs.
- [x] Try unauthenticated verification only for public company posting endpoint.
- [x] Mark `access_mode=public` only after explicit verified public mode.
- [x] Keep API-key mode separate from default public search.
- [x] Default uncertain sources to `unknown` and `needs_review`.

### iCIMS

- [x] Parse public iCIMS job-page URLs.
- [x] Do not enable public API search by default.
- [x] Mark official API sources `credentialed` or `unknown` without credentials.
- [x] Allow structured-data extraction from public iCIMS job pages when safe.
- [x] Keep credential support behind a separate future feature flag.

### Structured Data

- [x] Add structured-data adapter for single-job pages.
- [x] Parse JSON-LD `JobPosting`.
- [x] Validate page is a dedicated single-job page.
- [x] Check structured data aligns with visible content.
- [x] Respect robots and SSRF controls.
- [x] Do not crawl arbitrary internal links.

### Sprint 5 Tests

- [x] Test SmartRecruiters public verification success.
- [x] Test SmartRecruiters unknown/needs-review when unauthenticated access fails and no API key exists.
- [x] Test iCIMS defaults to credentialed/unknown.
- [x] Test structured-data single-job success.
- [x] Test structured-data listing page rejection.
- [x] Test robots-disallowed custom page is blocked.
- [x] Run provider tests and search resolver tests.
- [x] Fix failures from logs and rerun until green.

## Sprint 6: Workday User-Private Classification And Admin-Gated Verification

Goal: support Workday carefully without treating observed CXS endpoints as broadly safe by default.

### Workday Parsing

- [x] Parse public Workday job URLs:
  - `{tenant}.wd{n}.myworkdayjobs.com/{locale?}/{site}`
  - `{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
  - `jobs.myworkdaysite.com/recruiting/{tenant}/{site}`
- [x] Parse tenant, server, locale, site, and external path.
- [x] Detect candidate-home/status/private Workday URLs.
- [x] Allow user-private safe public posting classification.
- [x] Keep shared source records `unknown`/`needs_review` until admin approval.

### Workday Verification

- [x] Add `JOB_SEARCH_WORKDAY_ENABLED=false` default.
- [x] Add technical verification using small CXS POST only when enabled.
- [x] Use conservative tenant-level rate limits.
- [x] Do not use Playwright/browser automation/AI fallback for shared Workday verification.
- [x] Record `terms_risk=medium`.
- [x] Require admin approval for shared reuse.
- [x] Allow Workday to be disabled without breaking search.

### Sprint 6 Tests

- [x] Test Workday public URL parsing.
- [x] Test Workday candidate-home/status private classification.
- [x] Test Workday shared source remains needs-review before approval.
- [x] Test disabled Workday path degrades cleanly.
- [x] Test enabled technical verification with mocked CXS response.
- [x] Test 429/timeout/backoff behavior.
- [x] Run Workday tests and resolver tests.
- [x] Fix failures from logs and rerun until green.

## Sprint 7: Gmail Learning Loop And Reprocessing

Goal: safely convert user-owned Gmail/application evidence into private links and consented source candidates.

### Gmail Sync Hook

- [x] After Gmail sync creates/updates `EmailEvent`, classify candidate URLs.
- [x] Write `user_application_links`.
- [x] Create `application_source_links` where application context exists.
- [x] If `source_intelligence=true`, create redacted source discovery event.
- [x] If parser finds safe provider metadata, enqueue source verification candidate.
- [x] Do not block Gmail sync on provider work.

### Reprocessing

- [x] Add `backend/tasks/reprocess_source_intelligence.py`.
- [x] Reprocess existing `applications.job_url` and `email_events.action_url`.
- [x] Reprocess historical Gmail events with parser versioning.
- [x] Respect consent for shared source writes.
- [x] Process private user data only in user scope.
- [x] Make job idempotent.

### Source Discovery

- [x] Add redacted evidence event creation.
- [x] Keep duplicate task delivery from duplicating discovery events.
- [x] Add source poisoning controls:
  - [x] pending/needs_review status by default
  - conflicts to needs_review
  - recruiter agency domains cannot claim hiring company alone
  - company mapping requires employer-owned evidence

### Sprint 7 Tests

- [x] Test Gmail sync creates private link records.
- [x] Test source consent false blocks shared source writes.
- [x] Test source consent true creates redacted discovery event.
- [x] Test admin evidence contains no raw Gmail body, raw subject, query string, or tokens.
- [x] Test reprocessing is idempotent.
- [x] Test source poisoning conflict goes to needs_review.
- [x] Run Gmail sync, consent, source privacy, and reprocessing tests.
- [x] Fix failures from logs and rerun until green.

## Sprint 8: Admin Source Intelligence And User Settings UI

Goal: make governance visible and useful without exposing private user data.

### User Settings

- [x] Add Source Intelligence section to Settings.
- [x] Add consent toggle default off.
- [x] Add plain-language explanation:
  - private links stay private
  - sanitized metadata can improve job-source detection if opted in
  - user can turn it off
- [x] Add private link list:
  - provider
  - link type
  - company domain
  - created at
  - sanitization status
- [x] Do not show raw tokenized URLs by default.
- [x] Add delete private link action.
- [x] Add reprocess links action if backend endpoint exists.

### Admin Dashboard

- [x] Add Source Intelligence tab under AI Ops or a new admin route.
- [x] Add summary cards:
  - verified sources
  - pending review
  - failed/stale sources
  - broad API calls avoided
  - broad API monthly usage
  - private links rejected from sharing
- [x] Add tables:
  - source registry
  - verification runs
  - provider health
  - admin review queue
- [x] Add admin actions:
  - verify
  - approve
  - block
- [x] Require `is_admin` on all admin endpoints.
- [x] Redact all private/Gmail-derived evidence.
- [x] Add audit events for admin actions.

### Frontend Job Search Updates

- [x] Show source-aware states:
  - direct source found
  - broad fallback
  - provider limited
  - stale source
  - blocked source
- [x] Show badges:
  - Company source
  - provider name
  - Fresh today
  - Broad web
  - Stale
- [x] Add Save to Pipeline.
- [x] Add Track this source if appropriate.
- [x] Verify layout across desktop/tablet/mobile and collapsed sidebars.

### Sprint 8 Tests

- [x] Add API tests for admin-only source endpoints.
- [x] Add API tests for user private-link endpoints.
- [x] Add Playwright tests:
  - Settings source section renders and toggles.
  - Private links list does not show raw URL.
  - Admin source dashboard is admin-only.
  - Job Search shows provider-limited state.
  - Job Search shows direct-source badge.
  - Responsive desktop/tablet/mobile layouts do not overflow.
- [x] Run frontend lint:
  - `npm run lint` in `dashboardv2`
- [x] Run frontend smoke tests:
  - `npm run test:smoke` in `dashboardv2`
- [x] Fix failures from logs and rerun until green.

## Sprint 9: Observability, Metrics, And Production Controls

Goal: make source intelligence operable in beta.

### Metrics

- [x] Add Prometheus metrics:
  - `apptrail_job_source_discovered_total`
  - `apptrail_job_source_verified_total`
  - `apptrail_job_source_fetch_duration_seconds`
  - `apptrail_job_source_fetch_errors_total`
  - `apptrail_job_search_requests_total`
  - `apptrail_job_search_results_total`
  - `apptrail_job_search_broad_api_calls_total`
  - `apptrail_job_search_broad_api_calls_avoided_total`
  - `apptrail_private_url_rejected_total`
  - `apptrail_source_review_queue_size`
- [x] Add labels carefully to avoid high-cardinality user/query/url values.
- [x] Add source verification run records for every provider attempt.
- [x] Add audit events for:
  - source approved
  - source blocked
  - verification forced
  - private link deleted
  - consent changed

### Production Config

- [x] Add production readiness checks for:
  - source link encryption key
  - source link hash key
  - broad provider caps
  - Workday flag
  - custom crawl flag
  - source fetch max bytes
  - source fetch timeout
- [x] Add feature flags:
  - `JOB_SEARCH_DIRECT_SOURCES_ENABLED`
  - `JOB_SEARCH_WORKDAY_ENABLED`
  - `JOB_SEARCH_CUSTOM_CRAWL_ENABLED`
  - `JOB_SEARCH_BROAD_PROVIDER_ENABLED`
- [x] Add optional Redis lock/rate limit config if used.
- [x] Document required env vars.

### Live Smoke Tests

- [x] Add optional live smoke runner gated by `RUN_LIVE_JOB_SOURCE_SMOKE=true`.
- [x] Use one known public source per enabled provider.
- [x] Assert endpoint responds or clean empty state.
- [x] Assert no raw private data in logs.
- [x] Do not require live smoke in normal PR CI.

### Sprint 9 Tests

- [x] Add metrics tests that avoid high-cardinality labels.
- [x] Add production readiness tests for env/config.
- [x] Add optional live smoke tests gated by env.
- [x] Run full backend targeted source-intelligence test set.
- [x] Run frontend smoke tests if UI changed.
- [x] Fix failures from logs and rerun until green.

## Final Hardening Pass

- [x] Run `git diff --check`.
- [x] Run backend tests touched by all sprints.
- [x] Run frontend lint and smoke tests if frontend changed.
- [x] Run Postgres migration test or Alembic upgrade test.
- [x] Run optional live smoke only if keys/flags are intentionally configured.
- [x] Search for secrets or private URLs:
  - `rg -n "napi_|vck_|sk-|GOCSPX|api_key=|x-smarttoken|refresh_token|SOURCE_LINK" .`
  - verify any legitimate env-name references do not include values.
- [x] Inspect `git status --short`.
- [x] Confirm `.env`, screenshots, traces, and private docs are untracked/uncommitted.
- [x] Confirm `docs/ai-copilot-search-eval-plan.md` is not staged.
- [x] Review final diff for accidental broad refactors.
- [x] Commit only scoped implementation files.

## Definition Of Done

- [x] `source_intelligence` defaults off.
- [x] Private URLs never land in `Application.job_url`.
- [x] Private URLs are encrypted and HMAC-hashed with key versioning.
- [x] Gmail HTML hrefs are classified before storage.
- [x] Email tracking redirects are never network-fetched.
- [x] Shared source writes require explicit consent.
- [x] Gmail-derived metadata follows limited-use controls.
- [x] Provider adapters use safe fetch controls.
- [x] Direct-source search works without SerpAPI.
- [x] Broad search caps are enforced and observable.
- [x] Workday is disabled by default and admin-gated.
- [x] Admin dashboard is useful and redacted.
- [x] User Settings make consent and private links clear.
- [x] Tests for each sprint are green.
- [x] CI checks are green before PR.
