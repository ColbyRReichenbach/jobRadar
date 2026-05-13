# Production Readiness Audit

Audit date: 2026-04-24
Remediation pass: 2026-04-24
AI feature hardening pass: 2026-04-24

Current status note (2026-05-13): this is a dated readiness audit and remediation record, not a fresh full release certification. The original findings are preserved for traceability. Current code has a single Alembic head at `052_retrieval_foundation`; `/api/ai/metrics` is admin-gated; `/metrics` is protected in production unless `METRICS_BEARER_TOKEN` is configured; application job URLs and Gmail message ids are user-scoped unique constraints. Use `docs/deployment-checklist.md` for the current deployment gate.

## Verdict

The codebase is substantially closer to production-ready after the remediation pass, but a broad production launch still requires infrastructure configuration and a real deployment rehearsal.

The original code-level blockers called out below have been addressed in this branch: Alembic now has a single head, dashboard smoke tests pass, OAuth/CORS/refresh boundaries are stricter, admin/internal APIs require admin authorization, extraction reports are user-owned on create, the scheduled Gmail polling field mismatch is fixed, metrics are protected in production, readiness checks include worker/beat hooks, and dependency audits are clean.

The follow-up AI engineering pass also hardened the product's AI-heavy feature paths: model outputs are normalized before persistence/use, malformed classifications no longer become job updates, blank generated drafts/resumes fall back to deterministic templates/original content, Research Radar LLM failures degrade to deterministic outputs, scraped/public content is explicitly treated as untrusted prompt data, live Research Radar model aliases are adapted into strict internal schemas, and PDF resume parsing now declares its runtime dependency.

Remaining launch work is operational: set the new production environment variables, configure the canonical `https://api.apptrail.com` API domain, deploy API/worker/beat from the same revision, run migrations against production, enable monitoring/alerts, and complete a rollback rehearsal before broad traffic.

## Follow-Up Audit - 2026-04-30

The remediation branch is green on the main local checks, but the current code still has launch-relevant gaps that are not covered by the existing tests. The main risk theme is boundary drift: the product has separate dashboard, extension, admin, and research surfaces, but several contracts still treat those surfaces as more interchangeable than the security and UX docs imply.

### Follow-Up Remediation - 2026-04-30

The second follow-up pass tightens those boundaries while preserving the product-wide intelligence decision:

- Extension API keys now have a narrow mixed-mode surface for job capture, contact lookup/outreach status, company visit/submission tracking, extraction reports, and key validation. Dashboard data, profile/resume, email, settings, export, Radar, and admin surfaces require dashboard JWT sessions.
- Dashboard access tokens now reject refresh-token JWTs when sent as bearer access tokens.
- Production CORS/auth origin checks no longer include localhost unless `ENVIRONMENT=development` or `TESTING=1`.
- Local dev login now requires both `LOCAL_DEV_AUTH=true` and a development/test environment.
- Radar public-web fetching now requires HTTPS public targets and validates DNS plus every redirect target against local/private/reserved/link-local ranges.
- Admin navigation is hidden for non-admin users and admin routes are not mounted for them in the dashboard shell.
- Extension API keys persist in extension local storage again; this is acceptable because backend scope is now limited and dashboard Settings provides rotation/revocation.
- Docker/dashboard/env defaults no longer silently point production builds at localhost or stale provider docs.
- Radar now has explicit runtime launch controls: `RADAR_ENABLED=false` disables `/api/research/*` and scheduled dispatch, while `RADAR_RESEARCH_ENABLED=false` blocks research/hybrid public-web trackers but leaves internal Radar available.
- Radar alert volume is capped by `RADAR_ALERT_MAX_PER_USER_PER_DAY` so a bad run loop cannot flood a user with Radar notifications.

### Additional Follow-Up Pass - 2026-04-30

The next pass found that the product-wide company/ATS intelligence contract still needed stronger anonymization, not just auth separation.

Implemented:

- Product-wide ATS intelligence now requires a minimum number of distinct contributing users before public dashboard reads return metrics.
- Company tech intelligence now requires enough distinct contributing users before exposing product-wide tech signals.
- Aggregate responses use count buckets such as `3-4`, `5-9`, and `10-24` instead of exact cross-user sample sizes or mention counts.
- Company context keeps user-owned applications, contacts, emails, warm paths, and response stats scoped to the requesting user; product-wide tech/ATS sections are now suppressed until aggregate thresholds are met.
- Public URL validation and job parse URL validation now reject non-global IP ranges such as carrier-grade NAT addresses, not just private/loopback/link-local/reserved ranges.

Default anonymization threshold:

- `APPTRAIL_AGGREGATE_MIN_USERS=3` by default.
- Values lower than `2` are ignored; production can raise this for a stricter launch posture.

Default Radar launch posture:

- `RADAR_ENABLED=true` keeps the Radar surface available to beta users.
- `RADAR_RESEARCH_ENABLED` defaults off in production unless explicitly set to `true`; development/test environments default it on when unset.
- `RADAR_ALERT_MAX_PER_USER_PER_DAY=5` by default; set it lower for tighter beta cohorts or `0` to suppress Radar alerts.
- Scheduled Radar dispatch and queued runs honor the same flags as the API.

### P0: Extension API Keys Can Access Broad Dashboard Data APIs

Evidence:

- `backend/dependencies.py` `verify_api_key` accepts either a dashboard JWT or a per-user extension API key and returns the same `user_id` shape for both.
- `backend/main.py` `_require_user_id` says it requires a JWT-authenticated user context, but it only checks that `auth["user_id"]` exists.
- Many sensitive dashboard endpoints use `Depends(verify_api_key)` plus `_require_user_id`, so an extension API key can call them:
  - `GET /api/emails` returns email bodies/snippets/classification data.
  - `PATCH /api/emails/{email_id}` can mutate email state and classification.
  - `GET/PATCH/DELETE /api/profile` exposes and changes parsed resume/profile data.
  - `POST /api/resume/parse` writes resume text into the user profile.
  - `GET /api/export/csv` exports pipeline data.

Impact:

- A copied or compromised extension key has much broader account access than a capture-only extension credential should have.
- This conflicts with the documented "separate trust path" for extension auth.

Required fix:

- Split auth dependencies by capability:
  - dashboard session only for dashboard/data export/profile/email/resume settings endpoints;
  - extension API key only for extension capture/reporting endpoints;
  - explicit mixed-mode only where both are intentionally supported.
- Add tests proving API keys cannot read email bodies, export data, mutate profile/resume data, or call unrelated dashboard endpoints.
- Update endpoint names or docs where API-key access is intentionally product behavior.

### P1: Production CORS Still Trusts Localhost Origins

Evidence:

- `_configured_cors_origins` unconditionally adds `http://localhost:3000`, `http://localhost:5173`, `http://127.0.0.1:3000`, and `http://127.0.0.1:5173`.
- Refresh and auth-code exchange origin checks use the same configured origin set.

Impact:

- In production, a page served from one of those local origins can pass the refresh/exchange origin gate and receive an access token if the browser has a valid `SameSite=None` refresh cookie for the production API.
- This weakens the remediation claim that only configured production/staging origins can use credentialed auth flows.

Required fix:

- Only include localhost origins when `ENVIRONMENT=development` or `TESTING=1`.
- Add tests with `ENVIRONMENT=production` proving localhost origins are rejected by refresh/exchange and CORS.

### P1: Local Development Login Has No Production Guardrail

Evidence:

- `/api/auth/local-login` is disabled only when `LOCAL_DEV_AUTH` is false.
- It does not also require `ENVIRONMENT=development` or `TESTING=1`.

Impact:

- If `LOCAL_DEV_AUTH=true` is accidentally set in production, anyone can mint a session for an arbitrary email address.

Required fix:

- Require both `LOCAL_DEV_AUTH=true` and a non-production environment.
- Add a production-env regression test.

### P1: Public Web Research Fetching Lacks URL/Redirect SSRF Guarding

Evidence:

- Radar search accepts any search-result URL beginning with `http`.
- `fetch_document` fetches that URL with redirects enabled and does not validate scheme, hostname, resolved IPs, or redirect targets.

Impact:

- A search result or redirect chain could make the backend fetch internal/private-network URLs.
- This is especially relevant because tracker text is user-controlled and research runs can fetch many pages per run.

Required fix:

- Reuse the job-parse URL safety checks or add a shared outbound fetch validator.
- Require `https`, reject private/reserved/link-local IPs after DNS resolution, and re-check every redirect target.
- Add tests for direct private IPs, localhost hostnames, DNS-to-private addresses, and public-to-private redirects.

### Product Decision: Product-Wide Company/ATS Intelligence

Decision:

- Keep company tech and ATS intelligence product-wide so every authenticated dashboard user benefits from aggregate company data.
- Treat this surface as anonymized intelligence only: no raw applications, emails, contacts, notes, user identifiers, or per-user records should be exposed through these aggregate contracts.
- Keep user-specific company context scoped to the requesting user for applications, contacts, emails, and warm connections.
- Admin-gate recomputation and operational mutation endpoints.

Boundary:

- `GET /api/companies/{domain}/tech` and `GET /api/intelligence/ats/{platform}` are dashboard-authenticated, product-wide aggregate reads.
- `POST /api/intelligence/ats/compute` is admin-only.
- Extension API keys do not get access to these aggregate dashboard reads.

Follow-up guardrail:

- Add contract tests that assert aggregate endpoints contain only anonymized platform fields and never raw user-owned objects.

### P2: Admin-Only Views Are Visible To Every User

Evidence:

- The sidebar always includes `Classifier Audit` and `Extraction Reports`.
- The app always mounts those components when the tabs are selected; there is no `user.is_admin` gating in the shell.

Impact:

- Normal users see internal/admin surfaces and then hit API errors.
- This is a confusing UX and increases accidental exposure pressure on admin-only endpoints.

Required fix:

- Hide admin navigation unless `user.is_admin` is true.
- Add a friendly 403/unauthorized state in admin components.
- Add smoke coverage for non-admin navigation.

### P2: Extension Auth Persistence Is A UX Trap

Evidence:

- The extension stores `apiKey` only in `chrome.storage.session`.
- Legacy persistent `chrome.storage.local` keys are migrated into session storage and then removed.
- The dashboard tells users the key is shown once.

Impact:

- After a browser restart or session storage loss, the extension can lose the only copy of the API key and require users to rotate/regenerate it.
- This is safer than persistent local storage, but the UX is not explained in setup/settings copy.

Required fix:

- Pick an explicit product stance:
  - persistent extension connection with clear revocation/rotation controls, or
  - session-only extension connection with clear "you will need to reconnect" copy.
- Reflect that stance in Settings, setup, and store privacy copy.

### P2: Production Build And Environment Docs Still Have Stale Defaults

Evidence:

- `dashboardv2/Dockerfile` defaults `VITE_API_URL` to `http://localhost:8000`, so a container production build can silently point at localhost if the build arg is omitted.
- `dashboardv2/package.json` is still named `react-example`.
- `.env.example` now documents Neon/Postgres and `OPENAI_API_KEY`; earlier Anthropic/Supabase environment guidance has been removed.
- `npm audit --omit=dev --audit-level=high` exits cleanly, but still reports a moderate PostCSS advisory in production dependencies.

Impact:

- Production artifacts can be built with a broken API URL.
- New environment setup docs are inconsistent with the current OpenAI-backed code paths.
- Dependency review has a known moderate web-build advisory that is currently below the CI threshold.

Required fix:

- Remove the localhost Docker default or fail the Docker build when `VITE_API_URL` is not supplied for production.
- Rename the package to `apptrail-dashboard`.
- Keep `.env.example` aligned with the active provider stack when deployment providers change.
- Run `npm audit fix` or document why the PostCSS advisory is not exploitable.

## Follow-Up Verification Snapshot

Commands run on 2026-04-30. These are historical results from that remediation pass, not current release-certification results:

| Check | Result |
| --- | --- |
| `pytest -q` | Passed: 395 tests, 4 warnings, 40.56s |
| `npm run lint` in `dashboardv2` | Passed |
| `npm run build` in `dashboardv2` | Passed |
| `npm run test:smoke` in `dashboardv2` | Passed: 9 tests |
| `alembic heads` | Passed: `040 (head)` at the time; current head is `052_retrieval_foundation` |
| `python3 -m compileall -q backend` | Passed |
| `python3 -m pip_audit -r requirements.txt` | Passed: no known vulnerabilities |
| `npm audit --omit=dev --audit-level=high` | Passed: 0 vulnerabilities |
| `git diff --check` | Passed |

## Remediation Status

Implemented:

- Repaired Alembic revision chain and added production-hardening migration `040`.
- Added user-scoped uniqueness for application job URLs and Gmail message ids.
- Added `User.is_admin` plus reusable admin enforcement.
- Restricted browser origins to exact configured origins.
- Added origin checks to refresh and auth-code exchange.
- Protected `/api/ai/metrics` with admin auth and `/metrics` in production with `METRICS_BEARER_TOKEN`.
- Added `/api/live` and `/api/ready`, including optional Celery worker/beat readiness.
- Added Celery beat heartbeat task.
- Fixed scheduled Gmail polling to write `is_human`.
- Implemented `GET /api/contacts`.
- Made dashboard smoke auth deterministic and independent of local `.env`.
- Updated dashboard dependencies so `npm audit --omit=dev --audit-level=high` passes.
- Added CI checks for Python audit, npm audit, and Alembic single-head validation.
- Expanded deployment workflow for migrations, worker, and beat service deploys.
- Added validation/normalization for AI classifier, draft writer, resume parser, and resume tailor outputs.
- Added deterministic Research Radar fallbacks when LLM tasks fail or return invalid payloads.
- Added prompt boundaries that treat tracker fields, email snippets, report sections, and public web content as untrusted data.
- Added Research Radar schema adapters for common live model aliases while preserving strict Pydantic validation.
- Added `pdfplumber` to runtime requirements for PDF resume parsing.
- Added AI hardening regression tests for malformed model payloads and LLM service failures.

## What Was Audited

- Backend: FastAPI app, SQLAlchemy models, Alembic migrations, Celery tasks, auth/session flows, health/metrics, internal/admin endpoints.
- Dashboard: Vite/React app, auth client behavior, package scripts, Playwright smoke tests, dependency audit.
- Extension: manifest permissions, API base handling, content security posture.
- Deployment: GitHub Actions, Dockerfiles, Railway/Vercel assumptions, production checklist, operational docs.
- Test and build signals available locally.

## Verification Snapshot

Commands run during the original audit. These are historical results, not current release-certification results:

| Check | Result |
| --- | --- |
| `pytest -q` | Passed: 372 tests, 4 warnings, 37.87s |
| `pytest -q tests/test_ai_hardening.py` | Passed: 7 tests |
| AI-focused regression suite | Passed: 89 tests, 1 warning |
| Live synthetic OpenAI smoke suite | Passed: 9 AI surfaces, 0 fallbacks |
| `npm run lint` in `dashboardv2` | Passed |
| `npm run build` in `dashboardv2` | Passed |
| `npm run test:smoke` in `dashboardv2` | Passed: 8 tests |
| `alembic heads` | Passed: `040 (head)` at the time; current head is `052_retrieval_foundation` |
| Empty local Postgres `alembic upgrade head` | Passed through then-current `040` |
| `npm audit --omit=dev --audit-level=high` | Passed: 0 vulnerabilities |
| `python3 -m pip_audit -r requirements.txt` | Passed: no known vulnerabilities |
| `git diff --check` | Passed |
| `python3 -m compileall -q backend/services` | Passed |

## Original Blocking Findings And Remediation Notes

The findings below are retained as audit evidence. They describe the original risks and the acceptance criteria used for remediation.

### P0-1: Alembic Migration Graph Is Broken

Evidence:

- `alembic heads` fails before it can inspect the graph:
  - `FAILED: Could not determine revision id from filename 013_add_warm_connections.py`
- `backend/alembic/versions/013_add_warm_connections.py` is empty.
- Additional migration references point at revision ids that do not exist as declared revisions:
  - `014_add_alerts_and_response_days.py` references `down_revision = "013"`.
  - `027_add_linkedin_to_user_profiles.py` references `026_add_company_name_to_contacts`.
  - `030_add_contact_distinct_decisions.py` references `029`.
- A simple revision scan reports multiple heads:
  - `012_add_ats_behaviors.py`
  - `026_add_company_name_to_contacts.py`
  - `029_expand_notification_preferences.py`
  - `039_add_web_research_consent_and_radar_notification_pref.py`
- CI has a migration job that runs `alembic upgrade head`, so this should fail in release validation.

Impact:

- New environments cannot reliably initialize or upgrade the database.
- Production deploys cannot be made repeatable.
- Schema drift risk is high because application code may assume columns/tables that migrations cannot create.

Required fix:

- Repair the Alembic chain before any production release.
- Replace or reconstruct the empty `013_add_warm_connections.py` migration.
- Normalize all `revision` and `down_revision` ids.
- Decide whether the repository should have one linear migration head or explicit merge revisions.
- Add a CI check that runs `alembic heads` and fails unless the expected head count is met.

Acceptance criteria:

- `alembic heads` succeeds and returns the expected head count.
- `alembic upgrade head` succeeds against an empty database.
- `alembic downgrade -1 && alembic upgrade head` succeeds for the latest migration.
- CI migration job is green.

### P0-2: Dashboard Smoke Tests Are Failing

Evidence:

- `npm run test:smoke` fails locally before any release confidence can be established.
- With the local ignored `dashboardv2/.env`, `VITE_LOCAL_DEV_AUTH=true` changes the login surface and all 8 smoke tests fail expecting Google login UI.
- With CI-like auth mode, `VITE_LOCAL_DEV_AUTH=false npm run test:smoke`, 7 of 8 smoke tests still fail.
- The smoke helper mocks `/api/user/me`, but the dashboard auth client returns `null` before calling refresh unless a token or `apptrail-auth-session` hint exists.
  - Relevant client behavior: `dashboardv2/src/lib/api.ts`.
  - Relevant smoke helper: `dashboardv2/tests/smoke.spec.ts`.
- The auth callback smoke test visits `/auth/callback` without a `code`, so it no longer exercises token exchange.

Impact:

- CI cannot reliably prove that the dashboard shell, protected routes, auth redirect, and onboarding flows still work.
- Local ignored env files can silently change auth behavior and invalidate test assumptions.

Required fix:

- Make smoke tests own their auth setup:
  - Seed `apptrail-auth-session` when tests expect authenticated behavior, or provide a dedicated test auth bootstrap.
  - Update callback tests to include a valid mocked `code` flow or test the no-code error state explicitly.
- Make Playwright force a deterministic auth env regardless of developer `.env`.
- Consider adding `.env.test` or explicit env injection in `test:smoke`.

Acceptance criteria:

- `npm run test:smoke` passes from a clean checkout.
- `VITE_LOCAL_DEV_AUTH=false npm run test:smoke` passes.
- CI smoke test cannot be changed by an ignored local `.env`.

### P0-3: OAuth, CORS, and Refresh Token Boundaries Are Too Permissive

Evidence:

- CORS allows credentials and broad origin patterns:
  - Any `chrome-extension://.*`.
  - Any `https://apptrail[a-z0-9-]*.vercel.app`.
- `/api/auth/google` accepts `frontend_origin` or infers from `referer`, stores it in state, and later redirects the one-time auth code to that origin.
- `/api/auth/refresh` returns a bearer access token from the refresh cookie and does not appear to enforce CSRF or exact origin binding.
- `/api/auth/exchange` exchanges an auth code for an access token and sets a refresh cookie.

Impact:

- A malicious or abandoned preview deployment that matches the broad Vercel pattern could receive auth callback codes.
- A malicious Chrome extension origin is within the CORS allow pattern.
- If a browser sends the refresh cookie cross-site to an allowed origin, that origin can receive an access token.

Required fix:

- Replace regex origin trust with an exact allowlist from configuration.
- Treat preview deployments as untrusted by default; only explicitly allow a reviewed preview URL when needed.
- Restrict extension origins to the published extension id.
- Bind OAuth state and callback redirect to a server-side allowlist, not request-supplied origin alone.
- Add CSRF/origin checks to cookie-backed refresh and exchange endpoints.
- Add tests for rejected origins, rejected preview URLs, rejected extension origins, and refresh CSRF behavior.

Acceptance criteria:

- Only configured production/staging dashboard origins can use credentialed CORS.
- Only the configured extension id can use extension CORS.
- Refresh cannot mint an access token from a cross-site request without the required CSRF/origin proof.
- OAuth callback cannot redirect an auth code to an arbitrary matching preview URL.

### P0-4: Admin/Internal Data APIs Are Available To Any Authenticated User

Evidence:

- CSV audit endpoints under `/api/audits/*` use `Depends(verify_api_key)` but no admin/role guard.
- Extraction report admin endpoints use authentication but no admin role guard.
- Extraction report creation attempts to store `user_id`, but `_user` is a dict and the code checks `hasattr(_user, "id")`, so `user_id` is always `None`.
- Listing extraction reports only filters by `user_id` if `None` is not involved; with current inserts, reports are effectively global.
- Audit file endpoints are filesystem-backed and expose list/upload/delete/review behavior to any authenticated caller.

Impact:

- Any authenticated user can access or mutate operational audit data.
- Extraction reports may leak across tenants/users.
- Internal review workflows are not isolated from normal product users.

Required fix:

- Introduce explicit roles/claims for admin-only APIs.
- Add a reusable `require_admin_user` dependency.
- Fix extraction report ownership by reading the authenticated user id from the dict.
- Backfill or quarantine existing reports with `user_id IS NULL`.
- Add tests proving normal users get 403 and admins get access.

Acceptance criteria:

- Normal authenticated users cannot access audit, changelog, extraction report admin, or operational CSV endpoints.
- User-owned reports are scoped by `user_id`.
- Existing unowned report rows are migrated or hidden.

### P0-5: Scheduled Gmail Polling Task Is Broken

Evidence:

- `backend/tasks/poll_gmail.py` constructs `EmailEvent(..., is_automated=...)`.
- `backend/models.py` defines `EmailEvent` fields including `is_human`, but not `is_automated`.
- SQLAlchemy model construction with an unknown keyword will raise at runtime.
- Manual Gmail sync paths use `is_human`, so tests can pass while the Celery polling task fails.

Impact:

- Scheduled email ingestion can fail in production.
- Radar/contact intelligence depending on background Gmail polling may silently stop updating.

Required fix:

- Update the task to use the current model field, likely `is_human`.
- Add a unit test for the Celery poll path that constructs and persists an `EmailEvent`.
- Add worker error monitoring for task exceptions.

Acceptance criteria:

- Gmail polling task can process at least one message fixture without raising.
- Worker logs/metrics expose task failures.

### P0-6: Deployment Automation Does Not Represent The Actual Production System

Evidence:

- `.github/workflows/deploy.yml` deploys the backend API service and dashboard, but does not deploy or verify Celery worker or beat.
- No deploy step runs migrations.
- Existing production checklist still has open items around worker, beat, migrations, rollback, health, and runbooks.
- `docker-compose.yml` describes API, worker, beat, Redis, and Postgres locally, but production workflow only automates a subset.

Impact:

- A "successful" deploy can leave the production system partially updated.
- Background jobs and scheduled Radar/notification flows may be missing or stale.
- Schema/application mismatch can ship.

Required fix:

- Define production topology explicitly:
  - API service.
  - Celery worker service.
  - Celery beat or managed scheduler.
  - Redis broker/result backend.
  - Postgres database.
  - Dashboard.
  - Extension production API host.
- Add migration execution as a controlled deploy stage.
- Add post-deploy smoke checks for API, dashboard, worker, beat, Redis, and database.
- Document rollback and migration rollback procedures.

Acceptance criteria:

- A single release checklist or workflow deploys/verifies all required runtime units.
- Worker and beat version match the API release.
- Migrations are applied exactly once per release and are visible in release logs.

## High Priority Findings

### P1-1: Health Checks Return 200 For Degraded State And Miss Worker/Beat

Evidence:

- `/api/health` checks API, database, and Redis, but not Celery worker, beat, queue lag, or scheduled task drift.
- The endpoint returns a JSON status such as `degraded`, but keeps HTTP 200.

Impact:

- Load balancers and uptime monitors may consider a degraded system healthy.
- Worker/beat outages are invisible to basic readiness checks.

Required fix:

- Split liveness and readiness:
  - Liveness: process is up.
  - Readiness: database, Redis, migrations, worker heartbeat, beat freshness, and queue lag are acceptable.
- Return non-2xx for readiness failures.

Acceptance criteria:

- Readiness fails when Postgres, Redis, worker, or beat is unavailable.
- Monitoring alerts on non-2xx readiness.

### P1-2: Metrics And AI Metrics Are Too Exposed

Status: resolved by the remediation pass. The original evidence is retained below for audit traceability; current code gates `/api/ai/metrics` with `require_admin_user` and blocks public `/metrics` in production unless a bearer token is configured.

Original evidence:

- `/metrics` is unauthenticated.
- `/api/ai/metrics` is available to any authenticated user and appears to expose global AI usage metrics.

Impact:

- Operational metrics can leak traffic, cost, and internal behavior.
- Public metrics endpoints can become scraping or reconnaissance targets.

Required fix:

- Protect `/metrics` with network allowlisting, basic auth, or deployment-level protection.
- Require admin role for AI/global operational metrics.

Acceptance criteria:

- Public internet users cannot read `/metrics`.
- Non-admin users cannot read global AI metrics.

### P1-3: Multi-Tenant Data Model Has Global Uniqueness Where User Scope Is Expected

Status: resolved by the remediation pass. Current `Application` uses `UniqueConstraint("user_id", "job_url")`, and `EmailEvent` uses `UniqueConstraint("user_id", "gmail_message_id")`. The original evidence is retained below for audit traceability.

Original evidence:

- `Application.job_url` is globally unique while application create/update logic is user-scoped.
- This can prevent two users from saving the same job posting URL.
- `EmailEvent.gmail_message_id` is globally unique while `EmailEvent` also has `user_id`; Gmail message ids should be considered within the owning account unless proven globally unique across all connected accounts.

Impact:

- Users can block each other from tracking the same job URL.
- Email ingestion can collide across accounts.

Required fix:

- Replace global unique constraints with scoped constraints such as `(user_id, job_url)` and `(user_id, gmail_message_id)`.
- Ensure nullable legacy `user_id` rows are migrated or handled.

Acceptance criteria:

- Two different users can save the same job URL.
- Two different users can ingest messages with the same provider message id without conflict.
- One user still cannot create duplicate rows where product semantics forbid duplicates.

### P1-4: Extension Production API Host Is Not Release-Aligned

Evidence:

- `extension/manifest.json` host permissions allow `https://api.apptrail.com/*`, localhost, and 127.0.0.1.
- `extension/config.js` only accepts `https://api.apptrail.com` plus local development hosts.
- Deployment docs discuss Railway/comparable backend hosting; if production API is only available on a Railway host, the extension cannot call it.

Impact:

- A Web Store release can pass review but fail to connect to production.
- Changing host permissions after release requires a new extension submission.

Required fix:

- Commit to a canonical production API domain before extension submission.
- Ensure that domain is covered by manifest host permissions, dashboard CORS, backend CORS, and extension config validation.

Acceptance criteria:

- Installed production extension can authenticate and call the production API without code changes.
- Host permissions match the exact deployed API host.

### P1-5: Dependency And Build Reproducibility Gaps

Evidence:

- `requirements.txt` uses lower bounds rather than locked versions.
- `npm audit --omit=dev --audit-level=high` fails with high advisories in `vite` / `picomatch`.
- `vite` appears in dashboard runtime dependencies and devDependencies.
- Python dependency vulnerability audit was skipped because `pip-audit` is not installed.

Impact:

- Backend builds are non-reproducible.
- New installs can pick up untested versions.
- Known high frontend dependency advisories remain unresolved.

Required fix:

- Add a locked backend dependency file or compile a reproducible requirements set.
- Remove `vite` from runtime dependencies if it is build-only.
- Run `npm audit fix` or manually update Vite/picomatch dependency paths.
- Add `pip-audit` or equivalent to CI.

Acceptance criteria:

- Fresh backend install resolves the same dependency set used in CI.
- `npm audit --omit=dev --audit-level=high` passes or documented exceptions exist.
- Python dependency audit runs in CI.

### P1-6: Local Environment Can Invalidate Release Tests

Evidence:

- Ignored `dashboardv2/.env` sets local auth mode and changes smoke test behavior.
- Playwright smoke tests do not force all auth-sensitive env vars.

Impact:

- Developers and CI can see different auth surfaces.
- Local smoke failures are noisy and easy to ignore.

Required fix:

- Make test scripts set deterministic env.
- Add a checked-in `.env.test` or Playwright `webServer.env`.
- Document local auth mode separately from smoke/release auth mode.

Acceptance criteria:

- Smoke tests pass the same way with or without a developer `.env`.

### P1-7: Observability Is Optional Rather Than Release-Gated

Evidence:

- Dashboard Sentry is configured only when `VITE_SENTRY_DSN` is present.
- Backend dependencies include Sentry, but release docs do not make error reporting, alert routing, or sampling policy a launch gate.
- Worker task failure alerting is not clearly defined.

Impact:

- Production failures can be silent or only visible through manual log inspection.
- Background task errors can go unnoticed.

Required fix:

- Make backend, worker, beat, and dashboard error reporting a launch requirement.
- Define alert routing for API 5xx, worker task failure rate, queue lag, scheduler drift, auth errors, and dependency failures.

Acceptance criteria:

- A forced backend exception, dashboard exception, and Celery task exception all appear in the configured alerting system.

## Medium Priority Findings

### P2-1: Contacts API Contract Is Stale Or Incomplete

Evidence:

- `/api/contacts` currently returns an empty list placeholder.
- The richer relationship data appears to live under network/Radar endpoints instead.

Impact:

- API consumers can build against a dead endpoint.
- Dashboard and extension behavior can diverge.

Required fix:

- Remove the endpoint, mark it deprecated, or implement it against the real contacts/network model.

Acceptance criteria:

- Public API docs and implemented behavior match.

### P2-2: Radar Beta Scope Needs Explicit Launch Controls

Status: Remediated in this branch.

Evidence:

- Radar and web research flows are substantial and include opt-in/consent fields.
- Deployment docs already call out warm connections, Radar, web research consent, and notification preference review.

Impact:

- A broad release before UX, consent, privacy, and notification behavior are stable could create trust and compliance issues.

Required fix:

- Keep Radar behind explicit beta controls until data quality, consent copy, notification volume, and kill switches are validated.
- Implemented with `RADAR_ENABLED` and `RADAR_RESEARCH_ENABLED`; API routes, manual runs, queued worker runs, and scheduled dispatch all check those flags.
- Implemented Radar notification volume control with `RADAR_ALERT_MAX_PER_USER_PER_DAY`.

Acceptance criteria:

- Radar can be disabled globally without deploy.
- Users can clearly opt in/out of web research and Radar notifications.
- Notification volume limits are enforced and tested.

### P2-3: Operational Runbooks Are Still Incomplete

Status: Remediated in `docs/deployment-checklist.md`.

Evidence:

- Existing docs acknowledge missing runbooks for rollback, backups, secret rotation, incident response, and scheduled job ownership.

Impact:

- Incidents will depend on ad hoc operator knowledge.

Required fix:

- Add concise runbooks for:
  - Deploy and rollback.
  - Migration failure.
  - Database backup and restore.
  - Redis outage.
  - Worker/beat outage.
  - OAuth credential rotation.
  - Extension release rollback/disable.
- The deployment checklist now includes those runbooks plus a Radar disable/beta rollback procedure.

Acceptance criteria:

- A new operator can recover from common failures using docs alone.

## Release Readiness Path

### Phase 1: Restore The Release Gate

1. Fix Alembic migration graph.
2. Make dashboard smoke tests deterministic and green.
3. Add dependency vulnerability checks to CI.
4. Add `alembic heads` validation to CI.

Exit criteria:

- Backend tests, dashboard lint/build, dashboard smoke, migration upgrade, and dependency audits are green.

### Phase 2: Close Security And Authorization Gaps

1. Replace broad CORS regexes with exact configured origins.
2. Restrict Chrome extension CORS to the published extension id.
3. Add CSRF/origin protection to cookie-backed refresh/exchange flows.
4. Add admin role enforcement for operational APIs.
5. Fix extraction report ownership and backfill existing unowned rows.
6. Protect metrics endpoints.

Exit criteria:

- Normal users cannot access admin/operational data.
- Auth/session tests cover rejected origin and CSRF cases.
- Metrics are not publicly exposed.

### Phase 3: Make Production Topology Real

1. Deploy API, worker, beat, Redis, Postgres, dashboard, and extension against one canonical API domain.
2. Add controlled migration stage.
3. Add readiness checks for database, Redis, worker, beat, migration version, queue lag, and scheduler freshness.
4. Add release rollback process.

Exit criteria:

- A release can be deployed, verified, and rolled back from documented steps.

### Phase 4: Beta Hardening

1. Keep Radar and web research behind beta flags.
2. Validate consent, notification preferences, and kill switches.
3. Add synthetic checks for login, dashboard load, extension API call, Gmail sync, Radar worker task, and notification send.
4. Confirm Sentry/alerting coverage across frontend, API, worker, and beat.

Exit criteria:

- Limited beta users can run the full product flow while operators can detect and mitigate failures quickly.

## Recommended Launch Gates

Do not call the product production-ready until all of these are true:

- Database migrations are repaired and upgrade cleanly from empty database to head.
- Dashboard smoke tests pass in CI and locally without relying on developer env.
- OAuth callback, token exchange, and refresh flows have origin and CSRF tests.
- Admin/internal endpoints require explicit admin authorization.
- Worker and beat are deployed, monitored, and included in readiness.
- Metrics are protected.
- Dependency audits pass or have documented risk acceptance.
- Extension points at the canonical production API domain.
- Rollback, backup/restore, and incident response runbooks exist.

## Residual Risk After Fixes

Even after the blockers are closed, the highest residual risks are:

- Gmail/provider API edge cases and quota behavior under real user load.
- Radar data quality and user trust around inferred relationships.
- Notification fatigue or incorrect prioritization.
- Extension review/update latency if production host or permissions change.

Those are best handled through a constrained beta, explicit feature flags, and active monitoring rather than a broad launch.
