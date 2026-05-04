# Source Intelligence Implementation TODO

This checklist implements `docs/source-intelligence-job-search-spec.md` in order. Each sprint must end with tests green. If any test or check fails, inspect the failing logs, make the smallest targeted fix, and rerun the same test set until green before moving on.

## Branch and Change Control

- [ ] Start from the intended feature branch after current dirty work is committed or intentionally set aside.
- [ ] Do not commit `.env`, secrets, screenshots, generated browser artifacts, or private interview-planning docs.
- [ ] Keep `docs/ai-copilot-search-eval-plan.md` local only unless explicitly approved.
- [ ] Add `docs/source-intelligence-job-search-spec.md` and this TODO doc only when the implementation branch is ready for documentation changes.
- [ ] Use small commits by sprint or logical vertical:
  - `source-intel: add privacy data contracts`
  - `source-intel: harden application urls`
  - `source-intel: add url classifier`
  - `source-intel: add provider adapters`
  - `source-intel: add admin source dashboard`
- [ ] Before every commit, run `git diff --check` and inspect `git status --short`.

## Required Defaults

- [ ] `source_intelligence` consent defaults to `false` for existing and new users.
- [ ] Private user workflow URL classification can run under existing core/Gmail consent.
- [ ] Shared source writes require explicit `source_intelligence=true`.
- [ ] Workday shared source verification defaults disabled.
- [ ] Custom career-page crawling defaults disabled.
- [ ] Broad search fallback obeys global and per-user caps.
- [ ] Email tracking redirects are never network-fetched.

## Sprint 0: Privacy Retrofit For Existing URL Paths

Goal: close current privacy gaps before adding shared source intelligence.

### Backend Discovery

- [ ] Inspect all current places that read, normalize, store, export, index, or display job/application URLs:
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
- [ ] Identify every current use of first-URL regex extraction.
- [ ] Identify every server-side URL fetch path and whether it bypasses `backend/services/url_safety.py`.
- [ ] Identify current log redaction helpers and AI telemetry redaction paths.

### URL Safety Retrofit

- [ ] Extend `backend/services/url_safety.py` with max response byte enforcement.
- [ ] Ensure safe fetch behavior:
  - HTTPS only.
  - No URL credentials.
  - Reject localhost/private/link-local/reserved/metadata IPs.
  - Validate redirects before following.
  - No cookies.
  - Stable Opportunity Radar user agent.
  - Timeout required.
  - Max bytes required.
- [ ] Retrofit `/api/jobs/parse` to use the safe fetch wrapper.
- [ ] Remove or disable Playwright/browser automation from shared source verification paths.
- [ ] Ensure AI fallback cannot fetch or summarize private/tokenized links.

### Existing Application URL Hardening

- [ ] Add preliminary URL classifier/sanitizer call before saving `Application.job_url`.
- [ ] Ensure private URLs are never saved into `Application.job_url`.
- [ ] Ensure private URLs are not indexed into `SearchDocument`.
- [ ] Ensure private URLs are not included in export payloads.
- [ ] Ensure application suggestions do not choose the first URL blindly.
- [ ] Ensure application suggestions choose the safest public posting URL or no URL.
- [ ] Ensure `EmailEvent.action_url` is classified before being exposed or accepted.

### Tracking Redirect Rule

- [ ] Implement offline-only redirect parameter extraction for known parameters:
  - `url`
  - `u`
  - `target`
  - `redirect`
  - `q`
- [ ] Never issue HEAD/GET/preview requests to email tracking redirect URLs.
- [ ] If destination cannot be extracted offline and safely classified, mark as private/unresolved.

### Logging Redaction

- [ ] Expand redaction for:
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
- [ ] Strip CR/LF from redacted evidence and provider error messages.
- [ ] Do not log provider request URLs when credentials are query params.

### Sprint 0 Tests

- [ ] Add/update unit tests proving private URLs cannot be stored in `Application.job_url`.
- [ ] Add tests for scheduler, candidate-home, magic-login, token, `candidateId`, and `applicationId` URLs.
- [ ] Add tests proving email tracking redirects are not network-fetched.
- [ ] Add tests proving `/api/jobs/parse` rejects private/local/oversized/redirect-to-private URLs.
- [ ] Add tests proving search indexing and exports contain only safe public URLs.
- [ ] Run targeted backend tests for URL privacy and job parsing.
- [ ] Run existing relevant tests:
  - `pytest tests/test_public_url_safety.py`
  - `pytest tests/test_search_security.py`
  - any application suggestion tests touched
- [ ] Fix failures from logs and rerun until green.

## Sprint 1: Data Contracts, Consent, And Private Link Storage

Goal: create durable, secure data contracts without enabling shared source writes by default.

### Migration

- [ ] Add Alembic revision `049_add_source_intelligence.py`.
- [ ] Add `company_job_sources`.
- [ ] Add `user_application_links`.
- [ ] Add `source_discovery_events`.
- [ ] Add `job_postings`.
- [ ] Add `application_source_links`.
- [ ] Add `source_verification_runs`.
- [ ] Add `job_search_provider_usage`.
- [ ] Add `source_intelligence` consent flag to the existing consent model.
- [ ] Implement Postgres expression unique index or generated normalized key columns for `company_job_sources`.
- [ ] Avoid relying only on SQLite behavior for migration correctness.

### Models

- [ ] Add SQLAlchemy models for all new tables.
- [ ] Add relationships where useful:
  - application to application source links
  - application source link to user application link
  - application source link to job posting
  - company job source to source verification runs
- [ ] Ensure cascade/delete behavior matches the spec.
- [ ] Add created/updated timestamp defaults using existing repo conventions.

### Crypto

- [ ] Add source-link encryption helper with key-purpose separation from Gmail tokens.
- [ ] Add keyed HMAC-SHA256 helper for URL hashes.
- [ ] Add key version fields and helpers.
- [ ] Add env var validation for:
  - `SOURCE_LINK_ENCRYPTION_KEY`
  - `SOURCE_LINK_ENCRYPTION_KEY_VERSION`
  - `SOURCE_LINK_HASH_KEY`
  - `SOURCE_LINK_HASH_KEY_VERSION`
- [ ] In tests, provide deterministic test keys without using `.env`.
- [ ] Never log plaintext raw URLs, encrypted values, or HMAC keys.

### Consent API And UI

- [ ] Update `/api/consent` to include `source_intelligence`.
- [ ] Default `source_intelligence=false`.
- [ ] Update Settings UI with a Source Intelligence consent section.
- [ ] Explain private vs shared data in user-facing language.
- [ ] Add private-link management placeholder or basic list endpoint depending on implementation scope.
- [ ] Update privacy policy copy if the repo maintains user-facing policy docs.

### Gmail Limited-Use Compliance

- [ ] Add a visible UI disclosure for Gmail-derived source intelligence.
- [ ] Ensure shared source writes require explicit consent.
- [ ] Ensure admin views show only redacted/aggregate Gmail-derived metadata by default.
- [ ] Add support/security/legal exception language or audit reason field before any user-specific admin access.

### Sprint 1 Tests

- [ ] Add migration tests for Postgres or a CI migration job.
- [ ] Add SQLite-safe model metadata tests only as supplementary coverage.
- [ ] Add crypto tests:
  - encryption round trip
  - HMAC deterministic with same key
  - HMAC changes with key version/key
  - no plain SHA-256 behavior
- [ ] Add consent tests:
  - default false
  - update true/false
  - shared source write blocked when false
- [ ] Add API tests for admin redaction behavior.
- [ ] Run:
  - `pytest tests/test_consent.py`
  - new source crypto/privacy tests
  - migration test job if available
- [ ] Fix failures from logs and rerun until green.

## Sprint 2: URL Classifier, Sanitizer, And Email Href Extraction

Goal: create deterministic URL handling that all later source intelligence uses.

### Classifier Module

- [ ] Add `backend/services/source_intelligence/url_classifier.py`.
- [ ] Implement `ClassifiedUrl` dataclass.
- [ ] Extract URLs from:
  - raw Gmail MIME HTML hrefs
  - raw Gmail plaintext bodies
  - `EmailEvent.action_url`
  - `EmailEvent.body`
  - `EmailEvent.snippet`
  - `EmailEvent.summary`
  - `EmailEvent.key_sentence`
  - `Application.job_url`
  - manual job URL fields
- [ ] Normalize HTML entities and punctuation wrappers.
- [ ] Classify link types:
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
- [ ] Detect private indicators in path/query/fragment.
- [ ] Detect provider type and provider key when possible.

### Sanitizer Module

- [ ] Add `backend/services/source_intelligence/url_sanitizer.py`.
- [ ] Remove tracking params:
  - `utm_*`
  - `gh_src`
  - `source`
  - `ref`
  - `trk`
  - `campaign`
  - `email`
  - `mc_cid`
  - `mc_eid`
- [ ] Reject or privatize token params:
  - `token`
  - `auth`
  - `jwt`
  - `session`
  - `candidate`
  - `candidateId`
  - `applicationId`
  - `magic`
  - `invite`
- [ ] Normalize host and path.
- [ ] Drop fragments unless explicitly allowlisted.
- [ ] Preserve provider path information needed for public detail fetches.
- [ ] Generate canonical public URL and keyed HMACs.
- [ ] Fail closed to `private_user_only`, `rejected`, or `needs_review`.

### Gmail Integration

- [ ] Modify Gmail sync to extract raw MIME hrefs before HTML stripping.
- [ ] Preserve extracted candidate links as classified private records, not as raw email body text.
- [ ] Keep existing display-safe email body behavior.
- [ ] Write `user_application_links` records for classified links when allowed.
- [ ] Do not block Gmail sync on source verification.

### Application Integration

- [ ] Use classifier/sanitizer in application create/update.
- [ ] Create `application_source_links` for private and public supporting records.
- [ ] Set `Application.job_url` only when a safe public canonical URL exists.
- [ ] Update application suggestions to pick safest public posting URL.
- [ ] Ensure duplicate application logic still works when private URLs are excluded from `Application.job_url`.

### Sprint 2 Tests

- [ ] Add `tests/test_source_url_classifier.py`.
- [ ] Add `tests/test_source_url_sanitizer.py`.
- [ ] Add `tests/test_source_email_url_extraction.py`.
- [ ] Add fixtures for:
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
- [ ] Add tests proving Gmail hrefs are extracted before HTML stripping.
- [ ] Add tests proving no tracking redirect network request is made.
- [ ] Add application create/update API tests for private URL rejection.
- [ ] Run all new classifier/sanitizer tests and affected email/application tests.
- [ ] Fix failures from logs and rerun until green.

## Sprint 3: Provider Base Contracts And Public Adapters

Goal: implement direct-source search for low-risk public providers before Workday.

### Base Package

- [ ] Add `backend/services/job_sources/`.
- [ ] Add `base.py` with:
  - `SourceConfig`
  - `SearchQuery`
  - `VerificationResult`
  - `NormalizedJobPosting`
  - adapter interface
- [ ] Add provider-safe HTTP client wrapper using `url_safety`.
- [ ] Add provider response normalization helpers.
- [ ] Add provider-specific redaction helpers.

### Greenhouse Adapter

- [ ] Parse `boards.greenhouse.io/{board}` and `job-boards.greenhouse.io/{board}`.
- [ ] Verify public board through official job board API.
- [ ] Fetch jobs.
- [ ] Normalize title, company, location, URL, updated date, department if present.
- [ ] Use `access_mode=public`.

### Lever Adapter

- [ ] Parse `jobs.lever.co/{site}`.
- [ ] Verify postings endpoint.
- [ ] Fetch postings with JSON mode.
- [ ] Normalize categories, location, commitment, team, hosted URL.
- [ ] Use `access_mode=public`.

### Ashby Adapter

- [ ] Parse `jobs.ashbyhq.com/{board}`.
- [ ] Verify public posting API.
- [ ] Fetch jobs.
- [ ] Normalize compensation where present.
- [ ] Use `access_mode=public`.

### Workable Adapter

- [ ] Parse account from `apply.workable.com/{account}` and `{account}.workable.com`.
- [ ] Verify `www.workable.com/api/accounts/{account}?details=true`.
- [ ] Fetch public published jobs only.
- [ ] Normalize URL, application URL, department, location, workplace type, salary, shortcode.
- [ ] Do not use `/spi/v3/jobs` without approved API key.
- [ ] Use `access_mode=public` for verified published-job endpoint.

### Registry Writes

- [ ] Add source registry upsert helper.
- [ ] Add job posting upsert helper.
- [ ] Add dedupe key generation.
- [ ] Add `application_source_links` upsert helper.
- [ ] Make all upserts idempotent.

### Sprint 3 Tests

- [ ] Add mocked integration tests with `respx` or existing repo equivalent.
- [ ] Test each adapter parse/verify/fetch/normalize flow.
- [ ] Test provider timeout and 429 behavior.
- [ ] Test redirect to private IP rejection.
- [ ] Test oversized response rejection.
- [ ] Test redacted metadata contains no tokens/raw private URLs.
- [ ] Run:
  - provider adapter tests
  - `pytest tests/test_public_url_safety.py`
  - affected job search tests
- [ ] Fix failures from logs and rerun until green.

## Sprint 4: Source Resolver, Search API, And Cost Caps

Goal: replace hardcoded search behavior with direct-first resolver behind a feature flag.

### Resolver

- [ ] Add `backend/services/job_sources/resolver.py`.
- [ ] Resolve query into company/role/location terms.
- [ ] Find verified active sources for company/domain.
- [ ] Query adapters only for allowed access modes:
  - `public`
  - `api_key` only when approved server credentials exist
- [ ] Skip:
  - `unknown`
  - `blocked`
  - unapproved `credentialed`
  - unapproved `partner`
- [ ] Fall back to broad provider only when direct sources are missing/stale/failed/blocked.
- [ ] If broad provider returns ATS/company URLs, classify and enqueue verification candidates.
- [ ] Return provider status and source summary.

### Broad Provider Usage

- [ ] Add persistent usage enforcement using `job_search_provider_usage`.
- [ ] Add keyed HMAC query hashes.
- [ ] Enforce global monthly cap.
- [ ] Enforce per-user monthly cap.
- [ ] Track request mode and result count.
- [ ] Show clear provider-limited response when capped or disabled.

### Search API

- [ ] Preserve existing `/api/search` response fields:
  - `results`
  - `cached`
  - `provider_status`
- [ ] Add `source_summary`.
- [ ] Add richer result fields behind `JOB_SEARCH_DIRECT_SOURCES_ENABLED`.
- [ ] Keep frontend compatibility while adding new fields.
- [ ] Do not mix global `job_postings` with old `JobListing` cache long term.

### Role Matching

- [ ] Add deterministic role matcher module.
- [ ] Normalize titles.
- [ ] Add role-family expansion for analyst/data/AI/ML/engineering roles.
- [ ] Rank by title similarity, role family, skill/domain/location/freshness/source confidence.
- [ ] Avoid over-expansion into unrelated analyst roles unless domain matches.

### Sprint 4 Tests

- [ ] Add resolver tests:
  - direct source before SerpAPI
  - stale direct source falls back
  - blocked/unknown source skipped
  - unapproved credentialed source skipped
  - broad cap reached returns provider-limited state
- [ ] Add usage cap tests:
  - per-user cap
  - global cap
  - query hash does not store raw query
- [ ] Add role matcher tests for analyst expansion and over-expansion prevention.
- [ ] Add API tests for `/api/search` response compatibility.
- [ ] Run affected backend tests and frontend type checks if API types change.
- [ ] Fix failures from logs and rerun until green.

## Sprint 5: Access-Mode Providers And Structured Data

Goal: add cautious support for ambiguous/credentialed providers and custom single-job pages.

### SmartRecruiters

- [ ] Parse SmartRecruiters career and API URLs.
- [ ] Try unauthenticated verification only for public company posting endpoint.
- [ ] Mark `access_mode=public` only after successful unauthenticated verification.
- [ ] Support `access_mode=api_key` only with approved server credential.
- [ ] Default uncertain sources to `unknown` and `needs_review`.

### iCIMS

- [ ] Parse public iCIMS job-page URLs.
- [ ] Do not enable public API search by default.
- [ ] Mark official API sources `credentialed` or `unknown` without credentials.
- [ ] Allow structured-data extraction from public iCIMS job pages when safe.
- [ ] Keep credential support behind a separate future feature flag.

### Structured Data

- [ ] Add structured-data adapter for single-job pages.
- [ ] Parse JSON-LD `JobPosting`.
- [ ] Validate page is a dedicated single-job page.
- [ ] Check structured data aligns with visible content.
- [ ] Respect robots and SSRF controls.
- [ ] Do not crawl arbitrary internal links.

### Sprint 5 Tests

- [ ] Test SmartRecruiters public verification success.
- [ ] Test SmartRecruiters unknown/needs-review when unauthenticated access fails and no API key exists.
- [ ] Test iCIMS defaults to credentialed/unknown.
- [ ] Test structured-data single-job success.
- [ ] Test structured-data listing page rejection.
- [ ] Test robots-disallowed custom page is blocked.
- [ ] Run provider tests and search resolver tests.
- [ ] Fix failures from logs and rerun until green.

## Sprint 6: Workday User-Private Classification And Admin-Gated Verification

Goal: support Workday carefully without treating observed CXS endpoints as broadly safe by default.

### Workday Parsing

- [ ] Parse public Workday job URLs:
  - `{tenant}.wd{n}.myworkdayjobs.com/{locale?}/{site}`
  - `{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
  - `jobs.myworkdaysite.com/recruiting/{tenant}/{site}`
- [ ] Parse tenant, server, locale, site, and external path.
- [ ] Detect candidate-home/status/private Workday URLs.
- [ ] Allow user-private safe public posting classification.
- [ ] Keep shared source records `unknown`/`needs_review` until admin approval.

### Workday Verification

- [ ] Add `JOB_SEARCH_WORKDAY_ENABLED=false` default.
- [ ] Add technical verification using small CXS POST only when enabled.
- [ ] Use conservative tenant-level rate limits.
- [ ] Do not use Playwright/browser automation/AI fallback for shared Workday verification.
- [ ] Record `terms_risk=medium`.
- [ ] Require admin approval for shared reuse.
- [ ] Allow Workday to be disabled without breaking search.

### Sprint 6 Tests

- [ ] Test Workday public URL parsing.
- [ ] Test Workday candidate-home/status private classification.
- [ ] Test Workday shared source remains needs-review before approval.
- [ ] Test disabled Workday path degrades cleanly.
- [ ] Test enabled technical verification with mocked CXS response.
- [ ] Test 429/timeout/backoff behavior.
- [ ] Run Workday tests and resolver tests.
- [ ] Fix failures from logs and rerun until green.

## Sprint 7: Gmail Learning Loop And Reprocessing

Goal: safely convert user-owned Gmail/application evidence into private links and consented source candidates.

### Gmail Sync Hook

- [ ] After Gmail sync creates/updates `EmailEvent`, classify candidate URLs.
- [ ] Write `user_application_links`.
- [ ] Create `application_source_links` where application context exists.
- [ ] If `source_intelligence=true`, enqueue redacted source discovery event.
- [ ] If parser finds safe provider metadata, enqueue source verification candidate.
- [ ] Do not block Gmail sync on provider work.

### Reprocessing

- [ ] Add `backend/tasks/reprocess_source_intelligence.py`.
- [ ] Reprocess existing `applications.job_url` and `email_events.action_url`.
- [ ] Reprocess historical Gmail events with parser versioning.
- [ ] Respect consent for shared source writes.
- [ ] Process private user data only in user scope.
- [ ] Make job idempotent.

### Source Discovery

- [ ] Add redacted evidence event creation.
- [ ] Add evidence count updates without double counting duplicate task delivery.
- [ ] Add source poisoning controls:
  - pending status by default
  - conflicts to needs_review
  - recruiter agency domains cannot claim hiring company alone
  - company mapping requires employer-owned evidence

### Sprint 7 Tests

- [ ] Test Gmail sync creates private link records.
- [ ] Test source consent false blocks shared source writes.
- [ ] Test source consent true creates redacted discovery event.
- [ ] Test admin evidence contains no raw Gmail body, raw subject, query string, or tokens.
- [ ] Test reprocessing is idempotent.
- [ ] Test source poisoning conflict goes to needs_review.
- [ ] Run Gmail sync, consent, source privacy, and reprocessing tests.
- [ ] Fix failures from logs and rerun until green.

## Sprint 8: Admin Source Intelligence And User Settings UI

Goal: make governance visible and useful without exposing private user data.

### User Settings

- [ ] Add Source Intelligence section to Settings.
- [ ] Add consent toggle default off.
- [ ] Add plain-language explanation:
  - private links stay private
  - sanitized metadata can improve job-source detection if opted in
  - user can turn it off
- [ ] Add private link list:
  - provider
  - link type
  - company domain
  - created at
  - sanitization status
- [ ] Do not show raw tokenized URLs by default.
- [ ] Add delete private link action.
- [ ] Add reprocess links action if backend endpoint exists.

### Admin Dashboard

- [ ] Add Source Intelligence tab under AI Ops or a new admin route.
- [ ] Add summary cards:
  - verified sources
  - pending review
  - failed/stale sources
  - broad API calls avoided
  - broad API monthly usage
  - private links rejected from sharing
- [ ] Add tables:
  - source registry
  - verification runs
  - provider health
  - admin review queue
- [ ] Add admin actions:
  - verify
  - approve
  - block
- [ ] Require `is_admin` on all admin endpoints.
- [ ] Redact all private/Gmail-derived evidence.
- [ ] Add audit events for admin actions.

### Frontend Job Search Updates

- [ ] Show source-aware states:
  - direct source found
  - broad fallback
  - provider limited
  - stale source
  - blocked source
- [ ] Show badges:
  - Company source
  - provider name
  - Fresh today
  - Broad web
  - Stale
- [ ] Add Save to Pipeline.
- [ ] Add Track this source if appropriate.
- [ ] Verify layout across desktop/tablet/mobile and collapsed sidebars.

### Sprint 8 Tests

- [ ] Add API tests for admin-only source endpoints.
- [ ] Add API tests for user private-link endpoints.
- [ ] Add Playwright tests:
  - Settings source section renders and toggles.
  - Private links list does not show raw URL.
  - Admin source dashboard is admin-only.
  - Job Search shows provider-limited state.
  - Job Search shows direct-source badge.
  - Responsive desktop/tablet/mobile layouts do not overflow.
- [ ] Run frontend lint and smoke tests:
  - `npm run lint` in `dashboardv2`
  - `npm run test:smoke` in `dashboardv2`
- [ ] Fix failures from logs and rerun until green.

## Sprint 9: Observability, Metrics, And Production Controls

Goal: make source intelligence operable in beta.

### Metrics

- [ ] Add Prometheus metrics:
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
- [ ] Add labels carefully to avoid high-cardinality user/query/url values.
- [ ] Add source verification run records for every provider attempt.
- [ ] Add audit events for:
  - source approved
  - source blocked
  - verification forced
  - private link deleted
  - consent changed

### Production Config

- [ ] Add production readiness checks for:
  - source link encryption key
  - source link hash key
  - broad provider caps
  - Workday flag
  - custom crawl flag
  - source fetch max bytes
  - source fetch timeout
- [ ] Add feature flags:
  - `JOB_SEARCH_DIRECT_SOURCES_ENABLED`
  - `JOB_SEARCH_WORKDAY_ENABLED`
  - `JOB_SEARCH_CUSTOM_CRAWL_ENABLED`
  - `JOB_SEARCH_BROAD_PROVIDER_ENABLED`
- [ ] Add optional Redis lock/rate limit config if used.
- [ ] Document required env vars.

### Live Smoke Tests

- [ ] Add optional live smoke runner gated by `RUN_LIVE_JOB_SOURCE_SMOKE=true`.
- [ ] Use one known public source per enabled provider.
- [ ] Assert endpoint responds or clean empty state.
- [ ] Assert no raw private data in logs.
- [ ] Do not require live smoke in normal PR CI.

### Sprint 9 Tests

- [ ] Add metrics tests that avoid high-cardinality labels.
- [ ] Add production readiness tests for env/config.
- [ ] Add optional live smoke tests gated by env.
- [ ] Run full backend targeted source-intelligence test set.
- [ ] Run frontend smoke tests if UI changed.
- [ ] Fix failures from logs and rerun until green.

## Final Hardening Pass

- [ ] Run `git diff --check`.
- [ ] Run backend tests touched by all sprints.
- [ ] Run frontend lint and smoke tests if frontend changed.
- [ ] Run Postgres migration test or Alembic upgrade test.
- [ ] Run optional live smoke only if keys/flags are intentionally configured.
- [ ] Search for secrets or private URLs:
  - `rg -n "napi_|vck_|sk-|GOCSPX|api_key=|x-smarttoken|refresh_token|SOURCE_LINK" .`
  - verify any legitimate env-name references do not include values.
- [ ] Inspect `git status --short`.
- [ ] Confirm `.env`, screenshots, traces, and private docs are untracked/uncommitted.
- [ ] Confirm `docs/ai-copilot-search-eval-plan.md` is not staged.
- [ ] Review final diff for accidental broad refactors.
- [ ] Commit only scoped implementation files.

## Definition Of Done

- [ ] `source_intelligence` defaults off.
- [ ] Private URLs never land in `Application.job_url`.
- [ ] Private URLs are encrypted and HMAC-hashed with key versioning.
- [ ] Gmail HTML hrefs are classified before storage.
- [ ] Email tracking redirects are never network-fetched.
- [ ] Shared source writes require explicit consent.
- [ ] Gmail-derived metadata follows limited-use controls.
- [ ] Provider adapters use safe fetch controls.
- [ ] Direct-source search works without SerpAPI.
- [ ] Broad search caps are enforced and observable.
- [ ] Workday is disabled by default and admin-gated.
- [ ] Admin dashboard is useful and redacted.
- [ ] User Settings make consent and private links clear.
- [ ] Tests for each sprint are green.
- [ ] CI checks are green before PR.
