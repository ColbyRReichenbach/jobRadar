# Source Intelligence and Job Search Reliability Spec

## Purpose

Opportunity Radar should learn where companies actually publish jobs from the data users already bring into the product, especially Gmail application emails and tracked applications. The system should then use those learned sources to power job search, Radar trackers, and application creation with lower cost, better freshness, and stronger provenance than a broad web search alone.

This spec defines the implementation for a production-grade source intelligence layer that:

- Extracts reusable company and ATS source metadata from user-owned emails and applications.
- Keeps raw user links private, encrypted, and user-scoped.
- Verifies sources before using them broadly.
- Searches direct ATS/company sources before paid broad providers.
- Falls back to approved broad search APIs only when direct sources are missing or stale.
- Exposes admin observability for source health, privacy decisions, cost, and fallback usage.

## Current App Context

Relevant existing surfaces and modules:

- Gmail sync and diagnostics: `backend/tasks/poll_gmail.py`, `EmailEvent`, `EmailSyncAudit`, `dashboardv2/src/components/Settings.tsx`
- Applications and companies: `Application`, `Company`, `CompanyVisit`, `JobListing`
- Job search provider: `backend/services/job_search.py`, `dashboardv2/src/components/JobSearch.tsx`
- Radar research pipeline: `backend/tasks/run_research_radar.py`, `ResearchProfile`, `ResearchSourceItem`, `OpportunitySignal`
- Security helpers: `backend/services/url_safety.py`
- Consent: `DataConsent`, `/api/consent`, tests in `tests/test_consent.py`
- Admin AI/Ops views: AI Ops, Classifier Audit, Extraction Reports

Current gap: `job_search.py` has a small hardcoded Greenhouse target list and optional SerpAPI fallback. It does not have a source registry, Workday support, URL classification, source verification, private-link handling, or provider-level health.

Codebase review findings that affect implementation order:

- The current application suggestion flow extracts the first URL from `EmailEvent.action_url`, `body`, `snippet`, or `summary` and then writes a normalized value into `Application.job_url`. That path strips tracking parameters but does not reject scheduler, candidate-home, magic-login, token, `candidateId`, or `applicationId` links. Source intelligence must first close this privacy gap before any shared source registry writes.
- The current Gmail body parser strips HTML to display text and does not preserve `href` attributes. Source ingestion must extract candidate URLs from the raw Gmail MIME payload before HTML stripping, then store only classified and sanitized link records.
- `backend/services/url_safety.py` is the right foundation, but existing job parsing paths still use direct `httpx` fetches, redirects, Playwright, and AI fallback. Shared source verification must use the safer fetch wrapper only, and `/api/jobs/parse` should be retrofitted to the same controls.
- Current `Company` identity resolution is sender-domain oriented and intentionally treats ATS domains as platform domains. Source-to-company mapping therefore needs new evidence rules instead of reusing the current company upsert logic as-is.
- Existing tests are mostly SQLite metadata tests. The migration and expression indexes in this spec need Postgres/Alembic verification in CI or a dedicated migration test job.

## Product Principles

1. User data improves the product only through sanitized metadata.
2. Private application, scheduler, status, or tokenized links never become shared data.
3. Direct company/ATS sources are preferred over paid broad search.
4. Broad search providers are fallback and discovery tools, not the primary source of truth.
5. Every learned source needs provenance, confidence, and verification status.
6. Every job result needs source type, freshness, and a canonical URL.
7. The user should see clear failure states instead of silent empty search results.
8. Admins need enough observability to inspect source health without seeing private user tokens.
9. Privacy hardening for existing application and Gmail URL flows ships before shared source intelligence.
10. Official provider APIs and employer-owned career pages are preferred over browser automation, scraped search results, or AI extraction.

## Non-Goals

- Do not direct-scrape Indeed or LinkedIn search result pages.
- Do not bypass bot protection, robots restrictions, or provider terms.
- Do not auto-apply to jobs.
- Do not use raw email body or private links as shared source intelligence.
- Do not make AI decisions that materially affect hiring outcomes. The product recommends and organizes opportunities for the user.

## Source Ingestion Flow

```text
Gmail email / application / manual job URL
  -> extract candidate URLs from raw MIME hrefs, plaintext, and manual fields
  -> classify URL
  -> store raw private link only when needed for the user's own workflow and core/Gmail consent allows
  -> sanitize URL
  -> parse provider metadata
  -> verify public source
  -> resolve company identity with conflict controls
  -> score source confidence
  -> write/update company_job_sources only when source_intelligence consent allows
  -> direct provider search uses approved sources
```

## Data Classification

| Data | Examples | Scope | Storage Rule | Shared? |
| --- | --- | --- | --- | --- |
| Raw email body | Gmail message body, snippets | User-private | Existing `email_events`, user-scoped | No |
| Raw application URL | Candidate home, scheduler, status URL, tracking URL | User-private | Encrypted in `user_application_links.raw_url_encrypted` | No |
| Canonical public job URL | Public Workday job page, Greenhouse posting | User-private plus reusable pointer | Store sanitized URL separately | Only if safe |
| Provider metadata | `workday`, tenant, site, board token | Shared source intelligence | `company_job_sources` | Yes after verification |
| Job posting data | Title, description, location, req ID | Public job data | `job_postings` or expanded `job_listings` | Yes |
| Source evidence | "discovered from Gmail app confirmation" | Metadata only | `source_discovery_events` | Aggregated/redacted only |

## Database Changes

Create Alembic revision `049_add_source_intelligence.py`.

### `company_job_sources`

Shared, reusable public source registry.

`source_config` may contain provider tenant/site/locale/rate-limit metadata. It must not contain credentials, private user URLs, query strings, cookies, headers, or raw email-derived evidence.

```text
id uuid pk
company_id uuid nullable fk companies.id on delete set null
company_name text not null
company_domain text nullable
provider_type text not null
provider_key text nullable
access_mode text not null default 'unknown'
career_url text nullable
public_jobs_endpoint text nullable
source_config json nullable
source_confidence float not null default 0
verification_status text not null default 'pending'
active boolean not null default true
robots_allowed boolean nullable
terms_risk text not null default 'unknown'
discovered_from text not null
verified_by text nullable
evidence_count integer not null default 1
failure_count integer not null default 0
failure_reason text nullable
first_seen_at timestamptz not null
last_seen_at timestamptz not null
last_verified_at timestamptz nullable
stale_at timestamptz nullable
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes and constraints:

```text
unique(provider_type, provider_key, access_mode, coalesce(company_domain, ''), coalesce(career_url, ''))
index(company_domain, provider_type, active)
index(verification_status, active, access_mode, last_verified_at)
index(company_id, active)
```

Implementation note: the `coalesce(...)` uniqueness rule must be implemented as a Postgres expression unique index, or with generated normalized columns such as `company_domain_key` and `career_url_key`. Do not model it as a portable SQLAlchemy `UniqueConstraint` and assume SQLite tests will catch migration failures.

`provider_type` enum values:

```text
greenhouse
lever
ashby
smartrecruiters
workday
workable
icims
custom_career_page
structured_data
broad_search
unknown
```

`verification_status` enum values:

```text
pending
verified
needs_review
stale
blocked
failed
```

`terms_risk` enum values:

```text
low
medium
high
unknown
```

`access_mode` enum values:

```text
public
api_key
partner
credentialed
blocked
unknown
```

Rules:

- `public`: verified with unauthenticated public provider or employer-owned endpoints.
- `api_key`: requires a server-side provider API key approved for Opportunity Radar use.
- `partner`: requires marketplace/partner integration or contract access.
- `credentialed`: requires customer/employer credentials and must not be enabled for broad shared search unless Opportunity Radar has explicit approved access.
- `blocked`: must not be fetched.
- `unknown`: parser identified the source pattern, but access and terms are not verified.

### `user_application_links`

Private, user-scoped URL store.

```text
id uuid pk
user_id uuid not null fk users.id on delete cascade
application_id uuid nullable fk applications.id on delete cascade
email_event_id uuid nullable fk email_events.id on delete set null
raw_url_encrypted text nullable
raw_url_hash text not null
raw_url_hash_version text not null default 'v1'
canonical_public_url text nullable
canonical_public_url_hash text nullable
canonical_public_url_hash_version text nullable
link_type text not null
provider_type text nullable
provider_key text nullable
company_domain text nullable
contains_private_token boolean not null default false
sanitization_status text not null
rejection_reason text nullable
parser_version text nullable
encryption_key_version text nullable
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes and constraints:

```text
unique(user_id, raw_url_hash)
index(user_id, application_id)
index(user_id, link_type, created_at)
index(provider_type, provider_key)
```

`link_type` enum values:

```text
public_job_posting
company_career_page
ats_job_board
application_status
interview_scheduler
assessment
tracking_redirect
magic_login
candidate_home
unknown
```

`sanitization_status` enum values:

```text
safe_public
private_user_only
rejected
needs_review
```

Encryption requirement:

- Use the same app-level encryption pattern used for Gmail tokens, but use a separate source-link encryption key or explicit key-purpose separation.
- Store keyed HMAC-SHA256 hashes for dedupe and lookup, not plain SHA-256 hashes. Plain SHA-256 is vulnerable to offline guessing because many ATS and scheduler URLs are predictable.
- Store key versions for encrypted values and hashes so rotation is possible without breaking dedupe.
- Never log `raw_url_encrypted` or plaintext raw URLs.

Hashing env vars:

```text
SOURCE_LINK_ENCRYPTION_KEY=
SOURCE_LINK_ENCRYPTION_KEY_VERSION=v1
SOURCE_LINK_HASH_KEY=
SOURCE_LINK_HASH_KEY_VERSION=v1
```

### `source_discovery_events`

Audit trail for how a source was learned.

```text
id uuid pk
source_id uuid nullable fk company_job_sources.id on delete set null
user_id uuid nullable fk users.id on delete set null
email_event_id uuid nullable fk email_events.id on delete set null
application_id uuid nullable fk applications.id on delete set null
event_type text not null
provider_type text nullable
company_domain text nullable
confidence_delta float not null default 0
redacted_evidence json nullable
created_at timestamptz not null
```

Important privacy rule: `redacted_evidence` may contain provider type, hostname, message classification, and rule IDs. It must not contain full raw URLs, query strings, tokens, email body, or raw subject text.

### `job_postings`

Either expand `job_listings` or create a new normalized public posting table. Prefer a new table to avoid changing existing saved-job semantics.

```text
id uuid pk
source_id uuid nullable fk company_job_sources.id on delete set null
external_job_id text nullable
dedupe_key text not null
company_name text not null
company_domain text nullable
title text not null
normalized_title text nullable
description_text text nullable
description_hash text nullable
location_text text nullable
remote_status text nullable
employment_type text nullable
department text nullable
salary_min integer nullable
salary_max integer nullable
salary_currency text nullable
salary_period text nullable
date_posted timestamptz nullable
valid_through timestamptz nullable
canonical_url text not null
source_type text not null
source_confidence float not null default 0
active boolean not null default true
inactive_reason text nullable
first_seen_at timestamptz not null
last_seen_at timestamptz not null
last_verified_at timestamptz nullable
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes and constraints:

```text
unique(dedupe_key)
index(company_domain, active, last_seen_at)
index(source_type, active, last_seen_at)
index(normalized_title, active)
index(last_verified_at, active)
```

`dedupe_key` priority:

1. `source_type + provider_key + external_job_id`
2. canonical URL keyed HMAC hash
3. normalized company + normalized title + normalized location + description hash prefix

### `application_source_links`

Connects a user's application to the public posting, shared source, and private link records that support it.

Do not overload `applications.job_url` as the relationship boundary. `Application.job_url` remains a display-safe public URL only. This join table preserves the underlying provenance without placing private links on the application row, search index, export payload, or frontend object by default.

```text
id uuid pk
user_id uuid not null fk users.id on delete cascade
application_id uuid not null fk applications.id on delete cascade
job_posting_id uuid nullable fk job_postings.id on delete set null
company_job_source_id uuid nullable fk company_job_sources.id on delete set null
user_application_link_id uuid nullable fk user_application_links.id on delete set null
relationship_type text not null
confidence float not null default 0
created_from text not null
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes and constraints:

```text
unique(application_id, job_posting_id, relationship_type)
unique(application_id, user_application_link_id, relationship_type)
index(user_id, application_id)
index(company_job_source_id, relationship_type)
```

`relationship_type` enum values:

```text
source_candidate
canonical_posting
private_status_link
private_scheduler_link
manual_user_link
```

Rules:

- A pipeline application may have many supporting links, but only one preferred `canonical_posting` at a time.
- `private_status_link` and `private_scheduler_link` rows may reference `user_application_links`, but their raw URLs remain encrypted and user-scoped.
- `canonical_posting` should reference `job_postings` when available and may update `Application.job_url` with the posting's safe `canonical_url`.
- Deleting an application deletes its source-link relationships but does not delete shared public source records.

### `source_verification_runs`

Provider health and scheduled check history.

```text
id uuid pk
source_id uuid not null fk company_job_sources.id on delete cascade
status text not null
http_status integer nullable
job_count integer nullable
new_job_count integer nullable
inactive_job_count integer nullable
duration_ms integer nullable
error_type text nullable
error_message_redacted text nullable
robots_allowed boolean nullable
started_at timestamptz not null
finished_at timestamptz nullable
```

### `job_search_provider_usage`

Persistent broad-provider cost and cap tracking. Env vars define caps; this table is the source of truth for usage enforcement.

```text
id uuid pk
user_id uuid nullable fk users.id on delete set null
user_key text not null
provider text not null
request_mode text not null
query_hash text not null
month_bucket date not null
request_count integer not null default 1
result_count integer not null default 0
created_at timestamptz not null
updated_at timestamptz not null
```

Indexes and constraints:

```text
unique(user_key, provider, request_mode, query_hash, month_bucket)
index(provider, month_bucket)
index(user_id, provider, month_bucket)
```

`user_key` should be the user UUID string or `global` for global counters. `query_hash` must be a keyed HMAC of normalized query and location, not raw query text, so admin cost views do not expose a user's job-search intent.

## Consent and Privacy Requirements

### Consent

Add a specific consent flag:

```text
source_intelligence
```

Consent copy in Settings:

```text
Use sanitized job-source metadata from my applications to improve company job search. Private application links, scheduling links, and email contents are not shared.
```

Behavior:

- `source_intelligence` consent gates shared source writes only. Private user workflow storage is governed by core product/Gmail consent, retention, and deletion controls.
- If `source_intelligence=false`, still classify links for the user's own application workflow, but do not write shared `company_job_sources` or non-private `source_discovery_events`.
- Existing `web_research` consent controls public web/Radar research. `source_intelligence` controls shared source learning.
- Admin aggregate views must hide metrics below privacy thresholds.

### Gmail Limited-Use Compliance

Gmail-derived source metadata is still derived Google user data, even when sanitized, aggregated, or transformed. The feature must comply with Google's API Services User Data Policy and the Gmail limited-use rules before beta.

Requirements:

- Prominently disclose the source-intelligence use case in the product UI and privacy policy before using Gmail-derived data for shared source learning.
- Obtain explicit user consent for `source_intelligence` before writing shared source records from Gmail-derived data.
- Limit use of Gmail-derived data to visible, user-facing Opportunity Radar features: application tracking, job-source discovery, job search, Radar reports, and source-health improvement.
- Do not sell, transfer, or expose Gmail-derived data to third parties except as required to provide the visible user-facing feature with user consent.
- Human admin access to Gmail-derived evidence is prohibited by default. Admin views may show redacted metadata, aggregate counts, rule IDs, source IDs, and provider health only.
- Allow human review of user-specific Gmail-derived records only for explicit user-authorized support, security abuse investigation, or legal compliance.
- If the use of Gmail-derived data changes, update the privacy policy and prompt users to consent before enabling the new use.
- Treat source-discovery events and company-source confidence generated from Gmail as derived data subject to the same limited-use restrictions.

### Raw URL Privacy

Private URL indicators:

```text
token
auth
session
jwt
candidate
candidateId
applicationId
profileId
magic
invite
interview
schedule
calendly
greenhouse.io/application
workday candidate home
```

Rules:

- Tokenized URL: store encrypted user-private only, mark `contains_private_token=true`.
- Email redirect URL: do not network-fetch tracking or redirect links. Offline-unwrap only known query parameters such as `url`, `u`, `target`, `redirect`, or `q` when the extracted destination can be classified and sanitized safely; otherwise store private/unresolved.
- Scheduler URL: private user-only, never shared.
- Candidate status URL: private user-only, never shared.
- Public job posting URL: may become shared after sanitization and verification.
- `Application.job_url` may contain only a sanitized public posting or career URL. Private links must move to `user_application_links`; if no safe public URL exists, leave `Application.job_url` null.
- `EmailEvent.action_url` and application suggestions must use the classifier before exposing or accepting a URL.

### Logs and AI Telemetry

Never log:

- raw URLs with query strings
- Gmail message body
- tokens
- candidate/application IDs
- scheduler URLs
- plaintext encrypted fields
- headers/cookies from provider requests

Allowed logs:

```text
provider_type=workday
hostname_hash=...
source_id=...
rule_id=private_token_query_param
verification_status=blocked
```

Use OWASP logging guidance: sanitize event data, avoid sensitive data, and prevent log injection through CR/LF stripping.

Current logging update required:

- Expand global redaction beyond `token=` and bearer values to include `auth`, `session`, `jwt`, `candidate`, `candidateId`, `applicationId`, `profileId`, `magic`, `invite`, `interview`, and scheduler patterns.
- Do not log provider request URLs when credentials are query params, including SerpAPI `api_key`.
- Strip CR and LF from all redacted evidence and provider error messages before writing audit rows or logs.

### Retention, Revocation, and Deletion

User controls:

- User can disable `source_intelligence` consent.
- User can delete private application links from Settings.
- User can request reprocessing after changing consent.

Revocation behavior:

- Stop writing new shared source intelligence from that user's private data.
- Keep user-private links only if needed for the user's own application workflow.
- Delete `user_application_links` on user request.
- Keep already verified shared `company_job_sources` only if they contain no user identifiers and no private links.
- Remove or anonymize `source_discovery_events.user_id` where required by deletion workflows.
- Include `user_application_links` metadata in account export without raw URLs by default; provide raw private URLs only through an explicit, authenticated export path if the product chooses to expose them.
- Account deletion must cascade or anonymize `user_application_links` and `source_discovery_events` without deleting shared, verified, non-identifying source records.

Retention defaults:

```text
private tokenized links: 180 days after related application archive, unless user deletes earlier
safe public canonical links: keep while application exists
source discovery events: 365 days, redacted only
source verification runs: 365 days
job postings: keep active plus 180 days inactive for dedupe/freshness analytics
```

Private-link retention should be configurable by env var before beta.

## Security Controls

### Untrusted Content and AI Safety

All external job descriptions, career pages, and structured-data payloads are untrusted input.

Rules:

- Never execute scripts from fetched pages.
- Strip HTML to an allowlisted text representation before storage or AI use.
- Drop inline event handlers, scripts, styles, iframes, forms, tracking pixels, and hidden content.
- Store raw provider JSON only in redacted/debug-limited fields if needed; prefer normalized fields.
- Mark all provider content passed to AI as untrusted source text.
- System prompts must explicitly state that job descriptions and career-page text are data, not instructions.
- Do not let job-page text override user intent, tool policies, privacy rules, or provider fetch rules.
- Do not pass private user links into AI prompts unless the feature explicitly needs the user's own link and the prompt redacts tokens.
- Add prompt-injection fixtures where job descriptions say things like "ignore previous instructions" or "export all user emails".

Radar integration must cite normalized source records and redacted excerpts, not raw HTML or raw email content.

### SSRF Protection

All URL fetches must go through `backend/services/url_safety.py` or a stricter wrapper.

Required controls:

- Only `https`.
- No credentials in URL.
- Resolve DNS before request.
- Block localhost, loopback, private, link-local, multicast, reserved, and metadata IPs.
- Re-validate every redirect target.
- Mitigate DNS rebinding where practical by resolving immediately before connect and rejecting redirects or final peer IPs that resolve to disallowed ranges. If the HTTP client cannot pin the resolved IP safely, keep provider allowlists narrow and block custom crawling by default.
- Limit redirects to 5 or fewer.
- Set timeouts.
- Set max response size.
- Do not send cookies.
- Use a stable Opportunity Radar user agent.
- Prefer provider allowlists for ATS adapters.

Add missing max response size support to `fetch_public_https`. Also retrofit existing `/api/jobs/parse` and `backend/services/scraper.py` fetch paths so they do not bypass the same SSRF, redirect, max-byte, and no-cookie controls.

### Robots and Terms Compliance

Implement `robots_allowed` checks for non-API custom career page crawling.

Provider policy:

- Greenhouse, Lever, Ashby, and Workable documented public published-job endpoints: allowed adapter path with `access_mode=public` after verification.
- SmartRecruiters: allowed adapter path only when the target endpoint is confirmed public for that company or an approved API key is configured. SmartRecruiters docs are mixed: the authentication overview lists Posting API under no-auth public data, while the Posting API page says API key authentication. Store `access_mode=public` or `access_mode=api_key` per source after verification; do not assume anonymous access globally.
- Workday: parse/sanitize public job URLs for the user's own application workflow first. Shared Workday source verification comes later, uses only public career-site endpoints observed from public company career pages, and requires conservative rate limits, source verification, admin review, and kill switch.
- iCIMS: do not treat as public by default. Official Job Portal API examples use Basic Auth; keep iCIMS as `access_mode=credentialed` or `unknown` unless Opportunity Radar has explicit approved access. Public iCIMS job pages may still be handled through structured-data/custom-page extraction if robots and SSRF checks pass.
- Indeed and LinkedIn: no direct scraping. Use approved third-party/broad search provider only.
- Google Cloud Talent Solution: not a public job-discovery source. It may be evaluated later as a search/ranking layer over Opportunity Radar's own normalized `job_postings` corpus.
- Unknown custom career sites: only fetch structured data and public pages if robots allows; otherwise mark `blocked`.

Robots checks apply to custom page crawling and structured-data discovery. They do not replace provider terms review and should not be used as permission to scrape Indeed, LinkedIn, or other explicitly unsupported job-board search pages.

### Source Poisoning Controls

Threat: a malicious email or bad parser result teaches Opportunity Radar that the wrong ATS source belongs to a company.

Controls:

- New shared sources begin as `pending`.
- A source can become `verified` only after a public provider adapter succeeds.
- Sources discovered from one user and one email remain lower confidence until verified independently.
- Conflicting provider/company mappings go to `needs_review`.
- Recruiter agency domains cannot claim the hiring company without a public posting URL or repeated evidence.
- A verified adapter response proves that a source is fetchable; it does not by itself prove the source belongs to the intended company. Company mapping requires identity evidence from the posting, provider board, employer domain, or repeated independent evidence.
- Admin approval is required for low-confidence Workday/custom career-page sources before broad reuse.
- Verification events store rule IDs and redacted evidence so mistakes can be audited.

### Rate Limits

Provider defaults:

```text
GREENHOUSE: 60 requests/min global, 10 requests/min per board
LEVER: 60 requests/min global, 10 requests/min per site
ASHBY: 60 requests/min global, 10 requests/min per board
WORKABLE: 60 requests/min global, 10 requests/min per account
SMARTRECRUITERS: 60 requests/min global, 10 requests/min per company
WORKDAY: 30 requests/min global, 6 requests/min per tenant, 1.5 seconds minimum delay per tenant
ICIMS: credentialed only; default disabled
CUSTOM_CAREER_PAGE: 10 requests/min global, 2 requests/min per domain
BROAD_SEARCH: configurable monthly cap and per-user cap
```

Rate limit implementation:

- Use a durable shared limiter, preferably Redis-backed, because Celery workers and API processes can run in parallel.
- Persist broad-provider usage by user, provider, month, and request mode. Env vars are caps, not the source of truth.
- Provider 429s must write `source_verification_runs`, back off the source, and reduce scheduled verification pressure.

Add env vars:

```text
JOB_SEARCH_DIRECT_SOURCES_ENABLED=true
JOB_SEARCH_WORKDAY_ENABLED=false
JOB_SEARCH_CUSTOM_CRAWL_ENABLED=false
JOB_SEARCH_BROAD_PROVIDER_ENABLED=true
JOB_SEARCH_SERPAPI_MONTHLY_CAP=250
JOB_SEARCH_SERPAPI_USER_MONTHLY_CAP=25
SOURCE_VERIFICATION_MAX_SOURCES_PER_RUN=100
SOURCE_FETCH_MAX_BYTES=1048576
SOURCE_FETCH_TIMEOUT_SECONDS=10
```

Workday starts disabled by default until tests and admin review are complete.

## URL Classifier

New module:

```text
backend/services/source_intelligence/url_classifier.py
```

Responsibilities:

- Extract URLs from raw Gmail MIME `href` attributes before HTML stripping, plus plaintext bodies, `EmailEvent.body`, `snippet`, `summary`, `key_sentence`, `action_url`, and `Application.job_url`.
- Return both display-safe extracted link metadata and private raw-link handling decisions. Do not rely on the existing stripped `EmailEvent.body` as the only source of links.
- Normalize HTML entities and remove punctuation wrappers.
- Classify hostname/path/query.
- Detect private tokens and token-like values.
- Return a typed classification object.

Contract:

```python
@dataclass
class ClassifiedUrl:
    raw_url: str
    normalized_url: str | None
    hostname: str | None
    link_type: str
    provider_type: str | None
    provider_key: str | None
    contains_private_token: bool
    safe_to_share: bool
    rejection_reason: str | None
    rule_ids: list[str]
```

Unit fixtures:

```text
boards.greenhouse.io/acme/jobs/123 -> public_job_posting, greenhouse, safe
jobs.lever.co/acme/abc -> public_job_posting, lever, safe
jobs.ashbyhq.com/acme/abc -> public_job_posting, ashby, safe
company.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123 -> public_job_posting, workday, safe candidate
company.wd5.myworkdayjobs.com/.../candidate-home -> candidate_home, workday, private
calendly.com/recruiter/screen -> interview_scheduler, private
https://example.com?token=abc -> private_user_only
https://example.com?applicationId=abc -> private_user_only
https://example.com?candidateId=abc -> private_user_only
https://example.com?auth=abc&session=xyz -> private_user_only
https://click.email.provider/redirect?... -> tracking_redirect, needs unwrap
```

## URL Sanitizer

New module:

```text
backend/services/source_intelligence/url_sanitizer.py
```

Responsibilities:

- Remove tracking params: `utm_*`, `gh_src`, `source`, `ref`, `trk`, `campaign`, `email`, `mc_cid`, `mc_eid`.
- Reject or privatize token params: `token`, `auth`, `jwt`, `session`, `candidate`, `applicationId`, `magic`, `invite`.
- Offline-unwrap known email redirect parameters only when no network request is required and the destination passes classification/sanitization. Never call, preview, HEAD, or GET tracking redirect URLs because that can mark links as clicked and leak server IP, user-agent, timing, or recruiter-visible engagement signals.
- Normalize host lowercase.
- Remove fragments unless provider requires them.
- Preserve path for public job pages.
- Generate `canonical_public_url`.
- Generate keyed HMAC hashes for dedupe.
- Preserve enough provider path information to re-fetch public job details, but drop query strings unless the provider adapter explicitly allowlists a safe parameter.

Sanitizer must fail closed. If unsure, mark private or needs review.

## Provider Adapters

New package:

```text
backend/services/job_sources/
  __init__.py
  base.py
  greenhouse.py
  lever.py
  ashby.py
  workable.py
  smartrecruiters.py
  workday.py
  icims.py
  structured_data.py
  resolver.py
  verifier.py
  role_matcher.py
  dedupe.py
```

### Base Contract

```python
@dataclass
class SourceConfig:
    provider_type: str
    provider_key: str
    access_mode: str
    company_name: str | None
    company_domain: str | None
    career_url: str | None
    public_jobs_endpoint: str | None
    source_config: dict

@dataclass
class NormalizedJobPosting:
    external_job_id: str | None
    title: str
    company_name: str
    company_domain: str | None
    description_text: str | None
    location_text: str | None
    remote_status: str | None
    employment_type: str | None
    department: str | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: str | None
    date_posted: datetime | None
    valid_through: datetime | None
    canonical_url: str
    source_type: str
    source_confidence: float
    redacted_metadata: dict
```

Each adapter must implement:

```python
parse_source_from_url(url: str) -> SourceConfig | None
verify_source(config: SourceConfig) -> VerificationResult
fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]
fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None
```

### Greenhouse

Supported patterns:

```text
https://boards.greenhouse.io/{board_token}
https://job-boards.greenhouse.io/{board_token}
https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
```

Use official Job Board API GET endpoints. Public GET endpoints do not require auth.

### Lever

Supported patterns:

```text
https://jobs.lever.co/{site}
https://api.lever.co/v0/postings/{site}?mode=json
```

Use public postings JSON endpoint. Normalize categories, location, commitment, team, and hosted URL.

### Ashby

Supported patterns:

```text
https://jobs.ashbyhq.com/{board}
https://api.ashbyhq.com/posting-api/job-board/{board}
```

Use public job posting API. Include compensation if available.

### Workable

Supported patterns:

```text
https://{account}.workable.com/jobs/{shortcode}
https://apply.workable.com/{account}/j/{shortcode}
https://www.workable.com/api/accounts/{account}?details=true
```

Implementation:

- Prefer documented public published-job endpoints where available and verified, using `access_mode=public`.
- Parse account subdomain and job shortcode from Workable hosted URLs.
- Fetch published jobs from `https://www.workable.com/api/accounts/{account}?details=true` only after source verification succeeds.
- Do not use Workable `/spi/v3/jobs` unless Opportunity Radar has an approved API token; that path is `access_mode=api_key`.
- Normalize `url`, `application_url`, department, location, workplace type, salary, and shortcode. Treat candidate application URLs as public only when they are non-tokenized hosted apply URLs.
- Workable should ship before shared Workday verification because it has vendor-documented career-page API support.
- Workable source defaults: `access_mode=public` for verified `www.workable.com/api/accounts/{account}?details=true` published-job endpoints; `access_mode=api_key` for `/spi/v3/jobs`; `terms_risk=low` for verified public endpoints and `unknown` for API-key mode until approved access exists.

### SmartRecruiters

Supported patterns:

```text
https://careers.smartrecruiters.com/{companyIdentifier}
https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings
```

Use Posting API postings only when access is confirmed for that source. SmartRecruiters documentation is mixed: the authentication overview lists Posting API as no-auth public data, while the Posting API page says API key authentication. Implementation should support:

- Public company posting endpoints only after a successful unauthenticated verification run.
- Authenticated API-key mode through a server-side credential if Opportunity Radar obtains approved access.
- `terms_risk=unknown` and `verification_status=needs_review` when a SmartRecruiters URL parses but endpoint access is uncertain.
- SmartRecruiters source defaults: `access_mode=public` only after unauthenticated verification, `access_mode=api_key` only with approved server credentials, otherwise `access_mode=unknown`.

### iCIMS

Supported patterns:

```text
https://jobs.icims.com/jobs/{job_id}/...
https://{company}.icims.com/jobs/{job_id}/...
https://api.icims.com/customers/{customerId}/search/portals/{portalIdOrName}
```

Implementation:

- Do not enable iCIMS as a public API adapter by default. The official Job Portal API examples use Basic Auth.
- Parse public iCIMS job-page URLs for user-owned application records and structured-data extraction.
- Set parsed source records to `access_mode=credentialed` or `access_mode=unknown` unless approved credentials exist.
- If approved credentials are later obtained, implement iCIMS behind a separate feature flag and credential store; never place credentials in `source_config`.
- iCIMS source defaults: `access_mode=credentialed`, `terms_risk=unknown`, `verification_status=needs_review`.

### Workday

Supported public career patterns:

```text
https://{tenant}.wd{n}.myworkdayjobs.com/{locale?}/{site}
https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
https://jobs.myworkdaysite.com/recruiting/{tenant}/{site}
```

Implementation:

- Parse tenant, server, site, and optional locale from public career URLs.
- Verify with a small POST to `/wday/cxs/{tenant}/{site}/jobs` using `limit=1`, `offset=0`, `searchText=""`, `appliedFacets={}`.
- Fetch pages with conservative rate limits.
- Fetch details separately from `/wday/cxs/{tenant}/{site}/job/{externalPath}` when needed.
- Treat Workday as `terms_risk=medium` until validated per source.
- Provide admin kill switch through `JOB_SEARCH_WORKDAY_ENABLED`.
- Do not use Playwright, browser automation, or AI HTML fallback for shared Workday source verification.
- Require admin approval before a Workday source discovered from one user is reused broadly.
- Treat the CXS path as an observed public career-site endpoint, not as an official partner API. Re-check legal/terms risk before beta.
- Phase Workday in two steps: first classify/sanitize public Workday job URLs for user-private application workflows; later enable shared source verification after admin and legal/terms review.
- Workday source defaults: user-private URL classification may mark safe public postings, but shared source records remain `access_mode=unknown` and `verification_status=needs_review` until admin approval promotes them for direct-source use.

Workday edge cases:

- Multiple servers: `wd1`, `wd2`, `wd3`, `wd5`, etc.
- Locale prefix in path.
- Multiple sites per tenant.
- `jobs.myworkdaysite.com` alternate host.
- Listing endpoint lacks full description.
- Job req IDs vary: `JR123`, `JR_123`, `REQ123`, `R-000123`.
- Some jobs are multi-location.
- Some pages expose sitemaps, some do not.

### Structured Data Adapter

For custom career pages:

- Fetch page only if SSRF validation and robots check pass.
- Parse JSON-LD `JobPosting`.
- Extract Schema.org fields: title, description, hiringOrganization, jobLocation, datePosted, validThrough, employmentType, baseSalary.
- Parse `JobPosting` only from dedicated single-job pages. Do not treat listing/search pages with multiple jobs as valid structured-data sources for normalized postings.
- Verify that structured data aligns with visible page content before storing or ranking a posting.
- Do not crawl arbitrary internal links until explicitly enabled.

### Broad Provider Fallback

SerpAPI is a broad discovery fallback, not a canonical source of truth.

Rules:

- Use only after verified direct sources are missing, stale, failed, or blocked.
- Store broad-provider results as discovery candidates or temporary search results, not verified source health.
- If broad results contain direct ATS/company URLs, classify and enqueue those URLs for direct-source verification.
- Enforce global and per-user caps with `job_search_provider_usage`.
- Do not use Google Cloud Talent Solution for public job discovery. Cloud Talent Solution may be evaluated later as a search/ranking layer over Opportunity Radar's own `job_postings` corpus after direct-source ingestion exists.

## Company Identity Resolution

New module:

```text
backend/services/source_intelligence/company_identity.py
```

Input signals:

- Email sender domain.
- Application company text.
- Job posting company name.
- Career page hostname.
- Existing `companies.domain` and `companies.name`.
- Known aliases.

Rules:

- Prefer verified company domain over display name.
- Strip common suffixes: Inc, LLC, Ltd, Corp, Careers, Jobs.
- Do not use the existing sender-domain company resolver as the only proof for ATS source ownership.
- Require at least one employer-owned signal before mapping a shared source to `companies.id`: verified company domain, provider-returned company name that matches an existing company/alias, a public career page linked from the employer domain, or repeated independent public job-posting evidence.
- Maintain `company_aliases` table if needed:

```text
id
company_id
alias
source
confidence
created_at
```

Conflict handling:

- One company may have many source records.
- One source cannot map to multiple unrelated companies without admin review.
- Recruiting agency domains must not overwrite hiring company unless explicit evidence exists.

Examples:

```text
BofA -> Bank of America
Merrill -> Bank of America subsidiary, keep separate alias with review
google.com email with greenhouse.io posting -> company from posting, not Gmail provider
recruiter@agency.com for Bank of America role -> agency contact, hiring company unresolved until job URL confirms
```

## Source Resolver

Replace hardcoded provider logic in `backend/services/job_search.py` with:

```text
backend/services/job_sources/resolver.py
```

Search order:

1. Resolve company/role query.
2. Find verified active `company_job_sources`.
3. Query direct provider adapters with allowed `access_mode` values.
4. If no direct source exists, inspect known company career URL if available.
5. If still missing, use approved broad provider.
6. If broad provider returns direct ATS URLs, classify and enqueue source verification.
7. Cache and return normalized postings.

Allowed default direct-search access modes:

```text
public
api_key only when server-side approved credentials are configured
```

Blocked from default direct search:

```text
unknown
blocked
credentialed without approved credentials
partner without approved integration
```

User-facing provider status:

```json
{
  "mode": "direct_source | direct_plus_broad | broad_only | provider_limited",
  "direct_sources_checked": 2,
  "broad_search_used": false,
  "degraded": false,
  "degraded_reasons": [],
  "source_freshness": "verified_today",
  "cost_saved_estimate": {
    "broad_api_calls_avoided": 1
  }
}
```

## Semantic Role Matching

New module:

```text
backend/services/job_sources/role_matcher.py
```

Purpose: avoid brittle exact keyword search.

Process:

1. Normalize title.
2. Map to role families using deterministic taxonomy.
3. Expand query aliases.
4. Score each posting.
5. Return ranked results with reason codes.

Example query: `analyst`

Controlled expansions:

```text
data analyst
business analyst
BI analyst
reporting analyst
product analyst
analytics engineer
risk analyst
financial analyst
operations analyst
cloud data analyst
```

Avoid over-expansion:

- Do not include unrelated "investment analyst" for a data-only query unless finance domain is selected.
- Do not include senior/principal roles if user has entry-level preference unless "include senior" is enabled.

Ranking features:

```text
title_similarity
role_family_match
skill_overlap
domain_match
location_match
freshness
source_confidence
application_history_match
```

## Gmail and Application Integration

After Gmail sync creates or updates `EmailEvent`:

1. Extract URLs from the raw Gmail MIME payload before `parse_email_body` strips HTML. Preserve `href` URLs as candidate links, but never store them in `EmailEvent.body`.
2. Classify/sanitize.
3. Write `user_application_links`.
4. If consent allows, enqueue `source_discovery_event`.
5. If the link is safe and provider parser succeeds, enqueue source verification.
6. If verified, upsert `company_job_sources`.
7. If email indicates a job application and a public posting is found, suggest application creation with the posting attached.

Do not block Gmail sync on provider fetches. Use background tasks.

Application creation/update:

- If `Application.job_url` exists, classify it before duplicate checks, indexing, export, or persistence.
- If public, attach `source_id` or provider metadata.
- If private, encrypt in `user_application_links` and keep `Application.job_url` null unless a sanitized public canonical URL can be derived.
- Use `application_source_links` to connect the application to private user links, shared company sources, and normalized job postings. Do not use `Application.job_url` as the only source of truth.
- Application suggestions must not use the first URL regex directly. They must choose the safest public job URL from classified candidates, or no URL.

Migration safety:

- Backfill existing `applications.job_url` and `email_events.action_url`.
- For unsafe existing application URLs, create `user_application_links` records and clear or replace `Application.job_url` with a safe canonical public URL.
- Do not fetch during migration.
- Enqueue reprocessing jobs after deploy.

## Background Jobs

Background work must be idempotent. Source verification, historical reprocessing, and broad-provider discovery can all be delivered more than once or run concurrently across API and worker processes.

Shared rules:

- Every queued task must include an idempotency key derived from task type, source/user/application identifiers, parser version, and time bucket when appropriate.
- Use source-level or user-level locks before provider fetches and historical reprocessing. Prefer a durable Redis lock or database advisory lock over in-process locks.
- Use database upserts for `company_job_sources`, `job_postings`, `application_source_links`, and `source_discovery_events`.
- Duplicate task delivery must not duplicate postings, increment evidence counts incorrectly, or downgrade a verified source based on stale work.
- Status transitions must be monotonic unless the worker has a newer `started_at` timestamp or an explicit admin action.
- Provider fetch retries must be bounded and must preserve rate-limit state.

### Source Verification Job

```text
backend/tasks/verify_job_sources.py
```

Schedule:

- Verified active sources: daily if active users depend on them, weekly otherwise.
- Pending sources: process every 15 minutes with cap.
- Failed sources: exponential backoff.
- Stale sources: recheck before broad fallback if user requests that company.

Behavior:

- Runs adapters with strict rate limits.
- Updates `company_job_sources`.
- Writes `source_verification_runs`.
- Marks missing postings inactive after source succeeds but posting disappears.

### Historical Reprocessing Job

```text
backend/tasks/reprocess_source_intelligence.py
```

Use cases:

- New parser support.
- New sanitizer rules.
- Backfill existing users.
- Correct false positives.

Rules:

- Requires user consent for shared source writes.
- Processes private user data only in user scope.
- Records parser version in discovery event.

## API Changes

### Job Search

Current:

```text
GET /api/search
```

Extend response:

```json
{
  "results": [],
  "cached": false,
  "provider_status": {},
  "source_summary": {
    "direct_sources": [],
    "broad_provider_used": false,
    "verified_source_count": 0,
    "stale_source_count": 0,
    "blocked_source_count": 0
  }
}
```

Compatibility:

- Preserve the current `results`, `cached`, and `provider_status` fields so existing `dashboardv2/src/lib/api.ts` and `JobSearch.tsx` callers can roll forward safely.
- Add `source_summary` and richer result fields behind `JOB_SEARCH_DIRECT_SOURCES_ENABLED`, then update frontend types and empty/degraded states.
- Do not mix global public postings with the existing `JobListing` query cache long term. Use `job_postings` for normalized public postings and keep `JobListing` only as a temporary display/cache compatibility layer.

Result shape:

```json
{
  "id": "uuid",
  "title": "Data Scientist",
  "company": "Bank of America",
  "location": "Charlotte, NC",
  "source": "workday",
  "source_label": "Company career site",
  "source_confidence": 0.94,
  "freshness": "seen_today",
  "url": "https://...",
  "posted_at": "2026-05-03T00:00:00Z",
  "description": "...",
  "match_score": 87,
  "match_reasons": ["role_family:data_science", "location:preferred", "freshness:recent"]
}
```

### Admin Source Intelligence

New endpoints:

```text
GET /api/admin/job-sources
GET /api/admin/job-sources/{source_id}
POST /api/admin/job-sources/{source_id}/verify
POST /api/admin/job-sources/{source_id}/approve
POST /api/admin/job-sources/{source_id}/block
GET /api/admin/job-sources/health
GET /api/admin/job-sources/usage
```

Admin responses must redact private evidence.

### User Source Privacy

New endpoints:

```text
GET /api/settings/source-intelligence
PUT /api/settings/source-intelligence
GET /api/settings/source-intelligence/private-links
DELETE /api/settings/source-intelligence/private-links/{id}
```

Private link list should show only:

```text
provider
link_type
company_domain
created_at
sanitization_status
```

Do not show raw tokenized URLs by default.

## Frontend Changes

### Job Search Page

Add source-aware states:

- Direct source found: "Searching verified company career sources."
- Broad fallback: "No verified company source yet. Using broad web search."
- Provider limited: "Broad search is not configured. Add a company career URL or try a known company."
- Stale source: "Known source needs refresh. We are checking it now."
- Blocked source: "This provider is not available through Opportunity Radar."

Add result badges:

```text
Company source
Workday
Workable
Greenhouse
Fresh today
Broad web
Stale
```

Add "Save to Pipeline" and "Track this source" actions.

### Settings

Add `Source Intelligence` section:

- Consent toggle.
- Explanation of private vs shared data.
- Private-link management.
- "Reprocess my application links" button.

### Admin Dashboard

Add `Source Intelligence` tab under AI Ops or a new admin page:

Cards:

- Verified sources
- Pending review
- Failed/stale sources
- Broad API calls avoided
- Broad API monthly usage
- Private links rejected from sharing

Tables:

- Source registry
- Verification runs
- Provider health
- Admin review queue

## Observability and Metrics

Prometheus metrics:

```text
apptrail_job_source_discovered_total{provider_type,discovered_from,status}
apptrail_job_source_verified_total{provider_type,status}
apptrail_job_source_fetch_duration_seconds{provider_type}
apptrail_job_source_fetch_errors_total{provider_type,error_type}
apptrail_job_search_requests_total{mode}
apptrail_job_search_results_total{source_type}
apptrail_job_search_broad_api_calls_total{provider}
apptrail_job_search_broad_api_calls_avoided_total{reason}
apptrail_private_url_rejected_total{rule_id}
apptrail_source_review_queue_size{reason}
```

Admin audit events:

```text
source_approved
source_blocked
source_verification_forced
private_link_deleted
source_intelligence_consent_changed
```

## Testing Plan

### Unit Tests

Add:

```text
tests/test_source_url_classifier.py
tests/test_source_url_sanitizer.py
tests/test_source_email_url_extraction.py
tests/test_company_source_registry.py
tests/test_job_source_resolver.py
tests/test_workday_adapter.py
tests/test_provider_adapters.py
tests/test_role_matcher.py
tests/test_source_privacy.py
tests/test_source_link_crypto.py
```

Coverage:

- URL extraction from HTML/plaintext email bodies.
- URL extraction preserves Gmail HTML `href` links before display-text stripping.
- Private token detection.
- HMAC hash dedupe does not expose plain SHA-256 hashes.
- Redirect URL handling.
- Email tracking redirects are not network-fetched during unwrapping.
- Sanitizer removes tracking params.
- Sanitizer rejects token params.
- Workday parser handles `wd5.myworkdayjobs.com` and `jobs.myworkdaysite.com`.
- Greenhouse/Lever/Ashby/Workable/SmartRecruiters parse known URL patterns.
- iCIMS parser marks source access as `credentialed` or `unknown`, not verified public, without approved credentials.
- Resolver prefers verified direct source over SerpAPI.
- Resolver skips `unknown`, `blocked`, and unapproved `credentialed` sources.
- Resolver falls back when direct source is stale or failed.
- Role matcher expands analyst without flooding unrelated roles.
- Raw private URL never appears in shared source rows.
- Duplicate background task delivery does not duplicate source, posting, or application-link rows.
- Unsafe existing `Application.job_url` values migrate to private link storage or are nulled.
- Logs and telemetry are redacted.

### API Tests

Add:

- `GET /api/search` returns source summary and provider status.
- Search results are user-safe and have no private tokens.
- Admin endpoints require `is_admin`.
- Non-admin cannot see source registry.
- Admin source views do not expose Gmail-derived user evidence beyond redacted/aggregate metadata unless a narrow support/security/legal exception is explicitly recorded.
- Source consent off prevents shared source creation.
- Reprocess endpoint respects consent.
- Application creation/update rejects private job URLs from `Application.job_url` while preserving encrypted user-private records.
- Application source relationships are created through `application_source_links` and do not expose private links in application payloads.
- Account export and account deletion include/anonymize new source-intelligence tables according to retention rules.

### Migration Tests

Add a Postgres migration test or CI job:

- Alembic upgrades through `049_add_source_intelligence.py` on Postgres.
- Expression unique indexes or generated-key columns behave correctly with null `company_domain` and `career_url`.
- Downgrade behavior is explicit, even if destructive downgrade is intentionally unsupported.
- SQLite unit tests may still use simplified constraints, but they are not sufficient acceptance for the migration.

### Integration Tests With Mocked Providers

Use `respx` or equivalent HTTP mocking:

- Greenhouse list jobs.
- Lever postings.
- Ashby job board.
- Workable published jobs endpoint.
- SmartRecruiters postings.
- SmartRecruiters unauthenticated endpoint unavailable and authenticated mode disabled.
- iCIMS credentialed endpoint is skipped when credentials are absent.
- Workday listing and detail calls.
- Provider timeout.
- Provider 429.
- Redirect to private IP rejected.
- Response larger than max bytes rejected.

CI must use mocked providers by default.

### Live Smoke Tests

Manual or scheduled, not required for every PR:

```text
RUN_LIVE_JOB_SOURCE_SMOKE=true
```

Smoke only:

- One Greenhouse public board.
- One Lever public board.
- One Ashby public board.
- One Workable public published-job source.
- One SmartRecruiters company only when public endpoint access or approved API-key mode is configured.
- One Workday public career site if `JOB_SEARCH_WORKDAY_ENABLED=true`.

Assertions:

- Endpoint responds.
- At least one posting or clean empty state.
- No raw private data logged.

### Playwright Tests

Dashboard smoke:

- Job Search shows provider-limited state when broad provider is disabled.
- Job Search shows direct source badge from mocked verified source.
- Settings source intelligence section is collapsible/readable.
- Admin source intelligence page is admin-only.
- Mobile and desktop layouts do not overflow.

## Rollout Plan

### Phase 0: Privacy Retrofit for Existing URL Paths

- Add classifier/sanitizer usage to application creation, application update, application suggestions, extension imports, and `/api/jobs/parse`.
- Extract Gmail HTML `href` URLs before body stripping.
- Move unsafe existing `Application.job_url` values into encrypted `user_application_links` and clear unsafe public fields.
- Expand log redaction for private URL indicators and provider API keys.
- Add max-byte and redirect-safe fetching to all current server-side job URL fetch paths.

Acceptance:

- Private scheduler, candidate, magic-login, token, and status URLs cannot be stored in `Application.job_url`.
- Email-derived application suggestions never surface private URLs.
- Email tracking redirects are not network-fetched; only safe offline destination extraction is allowed.
- Current search indexing and export paths no longer include private job URLs.
- `/api/jobs/parse` fetches use SSRF-safe, max-byte-limited code paths.

### Phase 1: Privacy and Contracts

- Add DB tables.
- Add consent flag.
- Add URL classifier and sanitizer.
- Add private link storage.
- Add tests for privacy and token rejection.

Acceptance:

- Raw tokenized URLs are encrypted or rejected.
- No shared source rows are created without consent.
- Classifier handles common ATS links.

### Phase 2: Direct Provider Adapters

- Add Greenhouse, Lever, Ashby, and Workable public-source adapters.
- Add `access_mode` enforcement in the resolver.
- Replace hardcoded Greenhouse targets with source registry.
- Normalize postings.
- Add mocked integration tests.

Acceptance:

- Verified source search works without SerpAPI.
- Provider outputs share one job contract.
- Workable published jobs can be verified and searched before Workday shared verification.
- Search response includes source summary.

### Phase 3: Access-Mode Providers and Structured Data

- Add SmartRecruiters source-level public verification and approved API-key mode.
- Add iCIMS parser as `credentialed` or `unknown` by default, with no public direct-search use unless approved credentials exist.
- Add structured-data adapter for single-job pages.
- Add broad provider fallback discovery path that classifies returned direct ATS URLs.

Acceptance:

- SmartRecruiters is used only with confirmed public access or approved API-key configuration.
- iCIMS sources are not used as public direct sources by default.
- Structured-data extraction rejects listing pages and mismatched visible content.
- SerpAPI results are treated as fallback/discovery, not canonical source health.

### Phase 4: Workday Adapter

- Add Workday parser and verifier behind feature flag.
- Add conservative rate limits.
- Add admin review for Workday sources.
- Add tests for known URL formats.

Acceptance:

- Workday technical verification can pass from a public company career URL, but shared reuse remains admin-gated until access mode, company identity, and terms risk are approved.
- Workday failures degrade cleanly.
- Workday can be disabled without breaking search.

### Phase 5: Gmail Learning Loop

- Extract URLs after Gmail sync.
- Write private links.
- Enqueue source discovery/verification.
- Create source intelligence from application emails with consent.

Acceptance:

- Gmail sync is not blocked by source verification.
- Source discovery events are redacted.
- Existing users can reprocess historical emails.

### Phase 6: Search Ranking and Cost Controls

- Add role matcher.
- Add direct-first resolver.
- Add broad provider caps and usage tracking.
- Add cost-saved metrics.
- Optionally evaluate Google Cloud Talent Solution only as a ranking/search layer over the internal `job_postings` corpus, not for public job discovery.

Acceptance:

- Direct sources are used before broad search.
- Broad search caps work per user and globally.
- Search explains why broad provider was or was not used.

### Phase 7: Admin and QA

- Add admin source registry.
- Add source health dashboard.
- Add review queue.
- Add Playwright coverage.

Acceptance:

- Admin can approve/block/reverify sources.
- Non-admin users cannot access admin source data.
- UI is responsive across desktop/tablet/mobile.

## Failure Modes and Required Behavior

| Failure | Behavior |
| --- | --- |
| Private token detected | Store encrypted user-private only, do not share |
| Source parser uncertain | Mark `needs_review`, do not use broadly |
| Source fetch timeout | Keep stale results if fresh enough, show degraded state |
| Source returns 429 | Back off, reduce rate, do not retry hot |
| Source disappears | Mark stale after threshold, fallback to broad provider |
| Broad provider cap reached | Show provider-limited state, direct sources still work |
| Robots disallows custom crawl | Mark source blocked, no fetch |
| Company identity conflict | Queue admin review |
| Duplicate job appears across providers | Merge by dedupe key, preserve source provenance |
| User revokes consent | Stop shared writes; keep existing shared metadata only if it is already aggregated and non-identifying; delete private links on request |

## Acceptance Checklist

- [ ] New migrations apply cleanly.
- [ ] Postgres migration test covers expression unique indexes or generated-key uniqueness.
- [ ] No raw private URLs in logs, telemetry, admin views, or shared tables.
- [ ] Gmail-derived metadata follows Google limited-use requirements, including prominent disclosure, explicit consent for shared source learning, and no default human admin access to user evidence.
- [ ] `Application.job_url`, search indexes, and exports contain only safe public URLs.
- [ ] Application-to-source provenance is stored in `application_source_links`, not overloaded into `Application.job_url`.
- [ ] Gmail HTML `href` links are extracted before body stripping and classified before storage.
- [ ] Email tracking redirects are never network-fetched for unwrapping.
- [ ] Private URL hashes use keyed HMAC-SHA256 with key versioning.
- [ ] URL classifier has fixtures for every supported provider and private-link type.
- [ ] SSRF validation applies to every fetch path.
- [ ] Provider adapters normalize to one `NormalizedJobPosting` shape.
- [ ] Direct source search works with SerpAPI disabled.
- [ ] Broad search fallback is capped and observable.
- [ ] Workable public published-job sources are supported before shared Workday verification.
- [ ] SmartRecruiters requires confirmed public access or approved API-key configuration.
- [ ] iCIMS is credentialed/needs-review by default and is not treated as a public direct API source.
- [ ] Workday is feature-flagged, rate-limited, admin-reviewed, and does not use browser automation for source verification.
- [ ] Indeed and LinkedIn direct scraping are explicitly unsupported.
- [ ] Google Cloud Talent Solution is not used for public job discovery.
- [ ] Search UI explains source/fallback/degraded states.
- [ ] Admin source dashboard exists and is admin-only.
- [ ] CI has deterministic mocked provider tests.
- [ ] Live smoke tests are optional and gated by env vars.
- [ ] Background verification and reprocessing tasks are idempotent and guarded by durable locks or equivalent database concurrency controls.

## Implementation Notes

- Keep existing `JobListing` for saved/search display compatibility until the normalized `job_postings` flow is fully wired.
- Do not retrofit every existing search consumer at once. Introduce the resolver behind `JOB_SEARCH_DIRECT_SOURCES_ENABLED`.
- Source intelligence should be reusable by Radar, but Radar should consume normalized jobs and source summaries instead of fetching providers independently.
- Provider implementation order should be Greenhouse, Lever, Ashby, Workable, SmartRecruiters access-mode verification, structured-data/custom pages, Workday, then credentialed partner/provider APIs such as iCIMS only after approved access.
- If a provider adapter needs external network access, it must include tests that prove private redirects and private DNS resolutions are rejected.
- If a URL cannot be confidently sanitized, privacy wins over recall.

## References

- OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- RFC 9309 Robots Exclusion Protocol: https://www.ietf.org/rfc/rfc9309.html
- Google JobPosting structured data: https://developers.google.com/search/docs/appearance/structured-data/job-posting
- Schema.org JobPosting: https://schema.org/JobPosting
- Greenhouse Job Board API: https://developer.greenhouse.io/job-board.html
- Lever Postings API: https://github.com/lever/postings-api
- Ashby Job Postings API: https://developers.ashbyhq.com/docs/public-job-posting-api
- Workable Careers API guidance: https://help.workable.com/hc/en-us/articles/115012771647-Using-the-Workable-API-to-create-a-careers-page
- SmartRecruiters Posting API: https://developers.smartrecruiters.com/docs/posting-api
- SmartRecruiters Authentication: https://developers.smartrecruiters.com/docs/authentication
- iCIMS Job Portal API: https://developer-community.icims.com/applications/applicant-tracking/job-portal
- Indeed Job Sync API: https://docs.indeed.com/job-sync-api/
- Indeed Terms of Service: https://www.indeed.com/legal?co=US
- LinkedIn User Agreement: https://www.linkedin.com/legal/user-agreement
- Google API Services User Data Policy: https://developers.google.com/terms/api-services-user-data-policy
- Google Cloud Talent Solution: https://cloud.google.com/talent-solution/job-search/docs
- SerpAPI Google Jobs API: https://serpapi.com/google-jobs-api
- Workday Talent Acquisition product context: https://www.workday.com/en-us/products/talent-management/talent-acquisition.html
