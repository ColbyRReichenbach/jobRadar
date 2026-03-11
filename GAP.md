# AppTrail — Production Gap Analysis & Hardening Plan

**Audit Date:** 2026-03-10
**Audited by:** Senior domain experts (Security, Frontend, DevOps/SRE)
**Codebase:** 195 passing tests, 20 sprints complete, 67+ API endpoints

---

## Table of Contents

1. [Critical Security Gaps](#1-critical-security-gaps)
2. [Authentication & Authorization Gaps](#2-authentication--authorization-gaps)
3. [Input Validation & Injection Gaps](#3-input-validation--injection-gaps)
4. [Frontend & UX Gaps](#4-frontend--ux-gaps)
5. [Chrome Extension Gaps](#5-chrome-extension-gaps)
6. [Infrastructure & Deployment Gaps](#6-infrastructure--deployment-gaps)
7. [Monitoring & Observability Gaps](#7-monitoring--observability-gaps)
8. [Data Security Gaps](#8-data-security-gaps)
9. [Performance & Scalability Gaps](#9-performance--scalability-gaps)
10. [Store Submission & Distribution Gaps](#10-store-submission--distribution-gaps)
11. [Hardening Sprints](#11-hardening-sprints)

---

## 1. Critical Security Gaps

### GAP-001: JWT Secret Falls Back to Hardcoded Default
- **File:** `backend/dependencies.py:12`
- **Severity:** CRITICAL
- **Finding:** `JWT_SECRET` defaults to `"dev-secret-change-me"` if env vars missing. Tokens can be forged in misconfigured deployments.
- **Fix:** Require `JWT_SECRET` env var, crash on startup if missing.

### GAP-002: 30-Day JWT Token Expiry
- **File:** `backend/dependencies.py:23`
- **Severity:** CRITICAL
- **Finding:** `exp = now + 60*60*24*30` (30 days). Compromised tokens remain valid for a month.
- **Fix:** Reduce to 1 hour. Implement refresh token flow with HttpOnly cookie.

### GAP-003: No Token Revocation
- **File:** `backend/dependencies.py`
- **Severity:** HIGH
- **Finding:** No blacklist/revocation mechanism. Logout doesn't invalidate tokens.
- **Fix:** Add Redis-based token blacklist checked on every request.

### GAP-004: Extension Hardcodes HTTP (Not HTTPS)
- **File:** `extension/background.js:1`, `extension/sidepanel.js:1`, `extension/setup.js:1`
- **Severity:** CRITICAL
- **Finding:** `const API_BASE = "http://localhost:8000"` — production traffic unencrypted.
- **Fix:** Make API_BASE configurable via chrome.storage, default to HTTPS production URL.

---

## 2. Authentication & Authorization Gaps

### GAP-005: No Per-User Data Isolation
- **File:** `backend/main.py` (multiple endpoints)
- **Severity:** CRITICAL
- **Finding:** API key auth returns without identifying the user. All endpoints query data globally — no `WHERE user_id = ?` filtering. Any authenticated user sees all data.
- **Fix:** Extract user_id from JWT/API key context. Add user_id filter to every query.

### GAP-006: Single-User Fallback Queries
- **File:** `backend/main.py:877,1270,1729,2582,2610`
- **Severity:** CRITICAL
- **Finding:** When JWT fails, endpoints fall back to `select(Entity).limit(1)` — returning the first record in the database regardless of user.
- **Fix:** Return 401 on auth failure, never fall back to unscoped queries.

### GAP-007: Missing Resource Ownership Validation
- **File:** `backend/main.py` — PATCH/DELETE endpoints
- **Severity:** CRITICAL
- **Finding:** `update_application()`, `update_contact()`, `update_email()` don't verify the authenticated user owns the resource.
- **Fix:** Add `WHERE user_id = current_user.id` to all mutation queries.

### GAP-008: API Key Not User-Scoped
- **File:** `backend/dependencies.py:46-47`
- **Severity:** HIGH
- **Finding:** Single shared API key for all extension users. Can't distinguish users or revoke individually.
- **Fix:** Generate per-user API keys. Store hashed in database. Look up user on each request.

### GAP-009: No Brute Force Protection on Auth
- **File:** `backend/main.py` — auth endpoints
- **Severity:** MEDIUM
- **Finding:** No rate limiting on login/OAuth endpoints. Attacker can brute-force API keys.
- **Fix:** Rate limit auth endpoints (5 req/min per IP).

---

## 3. Input Validation & Injection Gaps

### GAP-010: SQL Injection via LIKE Patterns
- **File:** `backend/main.py:573,1108-1109,1118-1119,1130,1534-1536,2364`
- **Severity:** HIGH
- **Finding:** User input interpolated into LIKE patterns: `f"%{user_input}%"`. Special SQL chars (`%`, `_`) not escaped.
- **Fix:** Escape LIKE special chars or use full-text search.

### GAP-011: Unbounded String Fields in Pydantic Models
- **File:** `backend/main.py:44-50,1256-1258,1696`
- **Severity:** MEDIUM
- **Finding:** `company: str`, `description_text: Optional[str]`, `body: str` — no `max_length`. Users can submit multi-GB payloads.
- **Fix:** Add `Field(max_length=10000)` to all string fields. Add request body size limit middleware.

### GAP-012: SSRF via Job Parse Endpoint
- **File:** `backend/main.py:71`, `backend/services/scraper.py`
- **Severity:** HIGH
- **Finding:** `/api/jobs/parse` fetches arbitrary URLs. User can target `http://169.254.169.254/` (cloud metadata) or internal services.
- **Fix:** Validate URL scheme (HTTPS only), block private IP ranges, whitelist known job board domains.

### GAP-013: XSS via innerHTML in Extension
- **File:** `extension/sidepanel.js:93,157,166,169,209-213,237,266,293`
- **Severity:** HIGH
- **Finding:** Contact names, company names, and error messages inserted via `innerHTML` without sanitization. If server returns `<img onerror=alert(1)>`, it executes.
- **Fix:** Use `textContent` for user data or sanitize with DOMPurify.

### GAP-014: Email Header Injection
- **File:** `backend/main.py:1694`
- **Severity:** MEDIUM
- **Finding:** `SendEmailPayload.to: str` has no email format validation. Newlines could inject BCC/CC headers.
- **Fix:** Use Pydantic `EmailStr` validator.

---

## 4. Frontend & UX Gaps

### GAP-015: Token Stored in localStorage (XSS Vulnerable)
- **File:** `dashboardv2/src/lib/api.ts:60`, `dashboardv2/src/lib/AuthContext.tsx:46-51`
- **Severity:** CRITICAL
- **Finding:** JWT stored in localStorage, accessible to any XSS attack. OAuth callback passes token in URL hash (visible in browser history, referrer headers).
- **Fix:** Use HttpOnly, Secure, SameSite cookies. Replace URL hash flow with auth code exchange.

### GAP-016: No Global Error Boundary
- **File:** `dashboardv2/src/App.tsx`
- **Severity:** HIGH
- **Finding:** No React ErrorBoundary. Any component crash = white screen.
- **Fix:** Wrap app in ErrorBoundary with fallback UI.

### GAP-017: 401 Responses Not Handled
- **File:** `dashboardv2/src/lib/api.ts`
- **Severity:** HIGH
- **Finding:** Expired tokens cause silent failures. No auto-logout, no redirect to login.
- **Fix:** Intercept 401 responses globally, clear token, redirect to login.

### GAP-018: API Key Exposed in Frontend Bundle
- **File:** `dashboardv2/src/lib/api.ts:4`
- **Severity:** HIGH
- **Finding:** `VITE_API_KEY` bundled into JavaScript. Visible in browser devtools.
- **Fix:** Remove API key fallback from frontend. Use JWT-only auth for dashboard.

### GAP-019: No Content Security Policy
- **File:** `dashboardv2/index.html`
- **Severity:** HIGH
- **Finding:** No CSP meta tag. Allows inline scripts, external script injection.
- **Fix:** Add strict CSP header.

### GAP-020: Silent Fallback to Mock Data
- **File:** `dashboardv2/src/App.tsx:40-45`
- **Severity:** MEDIUM
- **Finding:** API failure silently falls back to mock data without warning user.
- **Fix:** Show error banner when API is unreachable.

### GAP-021: No Optimistic Update Rollback
- **File:** `dashboardv2/src/components/KanbanBoard.tsx:88-96`
- **Severity:** MEDIUM
- **Finding:** Drag-drop updates UI immediately but doesn't rollback on API failure.
- **Fix:** Store previous state, restore on error.

### GAP-022: Missing Accessibility
- **File:** Multiple components
- **Severity:** MEDIUM
- **Finding:** Icon-only buttons lack aria-labels, modals don't trap focus, no keyboard navigation for kanban.
- **Fix:** Add aria-labels, focus trapping, keyboard handlers.

---

## 5. Chrome Extension Gaps

### GAP-023: No Message Origin Validation
- **File:** `extension/background.js:18-28`, `extension/content.js:4-10`
- **Severity:** CRITICAL
- **Finding:** `chrome.runtime.onMessage` handlers don't validate sender. Malicious pages can send fake messages to trigger API calls.
- **Fix:** Check `sender.id === chrome.runtime.id` on every message.

### GAP-024: API Key Stored Unencrypted
- **File:** `extension/setup.js:23`
- **Severity:** HIGH
- **Finding:** API key stored in `chrome.storage.local` as plaintext. Accessible to other extensions.
- **Fix:** Use `chrome.storage.session` (clears on close) or encrypt before storing.

### GAP-025: No Extension CSP
- **File:** `extension/manifest.json`
- **Severity:** HIGH
- **Finding:** No `content_security_policy` in manifest. Allows eval() and inline scripts.
- **Fix:** Add `"content_security_policy": { "extension_pages": "script-src 'self'; object-src 'self'" }`.

### GAP-026: Overly Broad Host Permissions
- **File:** `extension/manifest.json:11-21`
- **Severity:** HIGH
- **Finding:** Extension requests full access to LinkedIn, Indeed, all Workday sites. Can read all page data.
- **Fix:** Use `optional_host_permissions` for non-essential domains. Minimize to only what's needed.

### GAP-027: No Offline/Error Handling
- **File:** `extension/sidepanel.js:44-57`
- **Severity:** HIGH
- **Finding:** If backend is down, extension shows generic error. No offline state, no retry queue.
- **Fix:** Distinguish network errors from auth errors. Queue failed syncs for retry.

### GAP-028: Setup Page Shows API Key in Plaintext
- **File:** `extension/setup.html:27-29`
- **Severity:** MEDIUM
- **Finding:** `<input type="text" id="apiKey">` — key visible while typing.
- **Fix:** Use `type="password"` with show/hide toggle.

---

## 6. Infrastructure & Deployment Gaps

### GAP-029: No Containerization
- **Severity:** CRITICAL
- **Finding:** No Dockerfile, docker-compose.yml, or Procfile anywhere in the project.
- **Fix:** Create Dockerfile for backend (Python 3.10 + uvicorn), dashboard (Node 18 + Vite build), docker-compose for local dev.

### GAP-030: No CI/CD Pipeline
- **Severity:** CRITICAL
- **Finding:** No `.github/workflows/`, no CI config of any kind. Tests are manual-only.
- **Fix:** Create GitHub Actions: test on PR, build+deploy on merge to main.

### GAP-031: No Database Connection Pooling
- **File:** `backend/database.py:10-12`
- **Severity:** HIGH
- **Finding:** `create_async_engine()` has no `pool_size`, `pool_recycle`, `pool_pre_ping` settings. Default pool will exhaust under load.
- **Fix:** Add `pool_size=20, max_overflow=10, pool_recycle=3600, pool_pre_ping=True`.

### GAP-032: No Production ASGI Server Config
- **Severity:** HIGH
- **Finding:** No gunicorn/uvicorn production config. No worker count, no keepalive, no access logging.
- **Fix:** Create `gunicorn.conf.py` or uvicorn CLI args in Procfile.

### GAP-033: No Celery Worker Production Config
- **File:** `backend/celery_app.py`
- **Severity:** HIGH
- **Finding:** No `worker_concurrency`, no `task_time_limit`, no `worker_max_tasks_per_child`. Tasks can hang forever.
- **Fix:** Add production worker settings.

---

## 7. Monitoring & Observability Gaps

### GAP-034: Shallow Health Check
- **File:** `backend/main.py:188-190`
- **Severity:** HIGH
- **Finding:** `/api/health` only returns `{status: ok}`. No database connectivity check, no Redis check.
- **Fix:** Add DB ping, Redis ping, return degraded status if subsystem down.

### GAP-035: No Structured Logging
- **Severity:** HIGH
- **Finding:** Uses stdlib `logging.getLogger()` with unstructured text output. Can't aggregate, search, or alert on logs.
- **Fix:** Add `structlog` with JSON output, request ID tracking.

### GAP-036: No Error Tracking (APM)
- **Severity:** HIGH
- **Finding:** No Sentry, Datadog, or any error tracking. Errors only visible in console output.
- **Fix:** Integrate Sentry SDK. Configure alerting on error rate.

### GAP-037: No Request Metrics
- **Severity:** MEDIUM
- **Finding:** No request duration, status code, or endpoint metrics collected.
- **Fix:** Add Prometheus middleware or Datadog APM.

---

## 8. Data Security Gaps

### GAP-038: Gmail Tokens Stored Unencrypted
- **File:** `backend/models.py:230-231`
- **Severity:** HIGH
- **Finding:** `GmailToken.access_token` and `refresh_token` stored as plain text in database. DB breach = full Gmail access.
- **Fix:** Encrypt at rest using `cryptography.fernet` or similar.

### GAP-039: API Keys in URL Query Parameters
- **File:** `backend/services/hunter.py:34`, `backend/services/job_search.py:36`
- **Severity:** MEDIUM
- **Finding:** Hunter and SerpAPI keys passed as `?api_key=...` in URL. Logged in reverse proxies, CDNs.
- **Fix:** Use Authorization headers where API supports it.

### GAP-040: Sensitive Data in Error Logs
- **File:** `backend/main.py:732`
- **Severity:** MEDIUM
- **Finding:** `logging.exception("OAuth token exchange failed")` logs full traceback including token data.
- **Fix:** Log sanitized error messages only.

---

## 9. Performance & Scalability Gaps

### GAP-041: No Rate Limiting
- **File:** `backend/main.py` (all endpoints)
- **Severity:** HIGH
- **Finding:** No rate limiting anywhere. Users can spam `/api/emails/send`, `/api/search`, `/api/jobs/parse`.
- **Fix:** Add `slowapi` middleware. Set per-endpoint limits.

### GAP-042: Unbounded Query Results
- **File:** `backend/main.py` — list endpoints
- **Severity:** MEDIUM
- **Finding:** `list_applications()`, `list_emails()`, `list_network()` return all records. 10K+ records = OOM.
- **Fix:** Add `limit`/`offset` query params with max page size (100).

### GAP-043: No List Virtualization
- **File:** `dashboardv2/src/components/EmailFeed.tsx`
- **Severity:** MEDIUM
- **Finding:** Email list renders all items in DOM. 1000+ emails = jank.
- **Fix:** Use `react-window` or `@tanstack/react-virtual`.

### GAP-044: N+1 Query in Email Sync
- **File:** `backend/main.py:982-990`
- **Severity:** HIGH
- **Finding:** For each email, loads ALL applications into memory to match by domain. O(emails * applications).
- **Fix:** Use single SQL query with domain matching.

### GAP-045: Polling Instead of Push
- **File:** `dashboardv2/src/App.tsx:57`
- **Severity:** LOW
- **Finding:** 30s polling interval. Multiple tabs = multiple polling loops.
- **Fix:** Consider SSE or WebSocket for real-time updates. Add exponential backoff on failures.

---

## 10. Store Submission & Distribution Gaps

### GAP-046: Missing Extension Icons
- **File:** `extension/manifest.json:51`
- **Severity:** CRITICAL (blocks store submission)
- **Finding:** `"icons": {}` — empty. Chrome Web Store requires 16x16, 48x48, 128x128 PNG icons.
- **Fix:** Design and add icon files to `extension/images/`.

### GAP-047: No Privacy Policy
- **Severity:** CRITICAL (blocks store submission)
- **Finding:** Chrome Web Store requires a privacy policy URL for extensions handling user data.
- **Fix:** Write privacy policy, host at apptrail domain.

### GAP-048: Missing Store Listing Assets
- **Severity:** HIGH
- **Finding:** No screenshots, no promotional images, no store description.
- **Fix:** Capture 2-3 screenshots of extension in use. Write store listing copy.

### GAP-049: Missing Manifest Fields
- **File:** `extension/manifest.json`
- **Severity:** MEDIUM
- **Finding:** No `homepage_url`, no `short_name`, no `action.default_icon`.
- **Fix:** Add required/recommended manifest fields.

### GAP-050: No Extension Packaging Script
- **Severity:** MEDIUM
- **Finding:** No script to zip extension for store upload. Manual process error-prone.
- **Fix:** Add `scripts/package-extension.sh`.

---

## 11. Hardening Sprints

### Sprint H1: Auth & Security Hardening (CRITICAL — Do First)
**Goal:** Eliminate all authentication and authorization vulnerabilities.
**Estimated effort:** 16 hours

| # | Task | Gaps Addressed | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Require JWT_SECRET env var, remove hardcoded fallback, crash on missing | GAP-001 | Done | Enforced in `backend/dependencies.py`; test-only fallback retained under `TESTING=1` |
| 2 | Reduce JWT expiry to 1h, implement refresh token in HttpOnly cookie | GAP-002, GAP-015 | Done | Access token is 1 hour; refresh token cookie flow added |
| 3 | Add Redis-based token blacklist (checked on verify_api_key) | GAP-003 | Partial | In-memory blacklist exists; Redis-backed revocation still needs implementation |
| 4 | Add user_id to all database queries (per-user data isolation) | GAP-005, GAP-006, GAP-007 | Done | Core user-owned routes now require JWT ownership checks and are regression tested |
| 5 | Generate per-user API keys (hashed in DB, lookup user on request) | GAP-008 | Done | User-scoped hashed API keys now back extension auth and can be issued/rotated from dashboard settings |
| 6 | Rate limit auth endpoints (5 req/min per IP) | GAP-009 | Done | Auth/OAuth endpoints now enforce a 5 req/min per-IP limit; current implementation is in-memory per process |
| 7 | Replace localStorage token with HttpOnly secure cookie flow | GAP-015 | Done | Dashboard no longer stores auth tokens in localStorage or URL hash; session bootstrap now relies on the refresh cookie |
| 8 | Remove VITE_API_KEY from frontend bundle | GAP-018 | Done | Dashboard no longer references `VITE_API_KEY`; extension now uses per-user API keys instead |

### Sprint H2: Input Validation & Injection Hardening
**Goal:** Close all injection and validation vulnerabilities.
**Estimated effort:** 10 hours

| # | Task | Gaps Addressed | Status | Notes |
|---|------|----------------|--------|-------|
| 1 | Escape LIKE special chars in all search queries | GAP-010 | Done | Shared escaping now treats `%` and `_` literally across backend `LIKE` filters |
| 2 | Add `Field(max_length=...)` to all Pydantic string fields | GAP-011 | Done | Request models now enforce bounded string lengths, including long text and resume payload fields |
| 3 | Add request body size limit middleware (1MB default) | GAP-011 | Done | Global request middleware now rejects payloads larger than 1MB with HTTP 413 |
| 4 | Validate URLs: HTTPS only, block private IPs, whitelist job boards | GAP-012 | Done | `/api/jobs/parse` now rejects non-HTTPS, private/local address targets, and unsupported hosts before any fetch occurs |
| 5 | Replace all `innerHTML` with `textContent` in extension | GAP-013 | Done | `extension/sidepanel.js` now builds status cards, contact rows, links, and nudges with DOM APIs instead of HTML string injection |
| 6 | Use Pydantic `EmailStr` for email fields | GAP-014 | Done | Email inputs now use `EmailStr` validation on send-email, interview, network detail, and draft-generation routes; `email-validator` added to requirements |
| 7 | Add CSP to dashboard index.html | GAP-019 | Done | `dashboardv2/index.html` now sets a CSP that restricts scripts to self, blocks plugin/object injection, and explicitly whitelists current fonts, images, API calls, and local dev websocket traffic |
| 8 | Add CSP to extension manifest.json | GAP-025 | Not Started |  |

### Sprint H3: Extension Security & Store Readiness
**Goal:** Secure extension and prepare for Chrome Web Store submission.
**Estimated effort:** 12 hours

| # | Task | Gaps Addressed |
|---|------|----------------|
| 1 | Make API_BASE configurable (chrome.storage), default to HTTPS prod URL | GAP-004 |
| 2 | Add sender origin validation to all message handlers | GAP-023 |
| 3 | Move API key to chrome.storage.session or encrypt | GAP-024 |
| 4 | Reduce host_permissions, use optional_host_permissions | GAP-026 |
| 5 | Add offline detection, retry queue, error states | GAP-027 |
| 6 | Change API key input to type="password" | GAP-028 |
| 7 | Design and add extension icons (16, 48, 128px) | GAP-046 |
| 8 | Write privacy policy | GAP-047 |
| 9 | Create store listing (description, screenshots) | GAP-048 |
| 10 | Add missing manifest fields (homepage_url, short_name, action.default_icon) | GAP-049 |
| 11 | Create extension packaging script | GAP-050 |

### Sprint H4: Infrastructure & Deployment
**Goal:** Containerize, automate CI/CD, configure production database.
**Estimated effort:** 16 hours

| # | Task | Gaps Addressed |
|---|------|----------------|
| 1 | Create backend Dockerfile (Python 3.10 + uvicorn) | GAP-029 |
| 2 | Create dashboard Dockerfile (Node 18 + Vite static) | GAP-029 |
| 3 | Create docker-compose.yml (backend, dashboard, postgres, redis) | GAP-029 |
| 4 | Create Procfile for Railway/Render | GAP-029 |
| 5 | Create GitHub Actions: test on PR | GAP-030 |
| 6 | Create GitHub Actions: build+deploy on merge | GAP-030 |
| 7 | Add connection pooling to database.py | GAP-031 |
| 8 | Create gunicorn.conf.py / uvicorn production config | GAP-032 |
| 9 | Add Celery worker production settings (concurrency, timeouts) | GAP-033 |

### Sprint H5: Monitoring, Logging & Observability
**Goal:** Production-grade observability.
**Estimated effort:** 10 hours

| # | Task | Gaps Addressed |
|---|------|----------------|
| 1 | Enhance /api/health with DB + Redis checks | GAP-034 |
| 2 | Add structlog with JSON output + request ID tracking | GAP-035 |
| 3 | Integrate Sentry SDK for error tracking | GAP-036 |
| 4 | Add Prometheus/metrics middleware | GAP-037 |
| 5 | Sanitize error logs (remove token/credential data) | GAP-040 |

### Sprint H6: Frontend Resilience & UX Hardening
**Goal:** Handle all error states, improve reliability.
**Estimated effort:** 8 hours

| # | Task | Gaps Addressed |
|---|------|----------------|
| 1 | Add React ErrorBoundary with fallback UI | GAP-016 |
| 2 | Add global 401 interceptor with auto-logout | GAP-017 |
| 3 | Replace silent mock data fallback with error banner | GAP-020 |
| 4 | Add optimistic update rollback on API failure | GAP-021 |
| 5 | Add aria-labels, focus trapping, keyboard navigation | GAP-022 |

### Sprint H7: Performance & Data Security
**Goal:** Rate limiting, query optimization, data encryption.
**Estimated effort:** 12 hours

| # | Task | Gaps Addressed |
|---|------|----------------|
| 1 | Add slowapi rate limiting middleware | GAP-041 |
| 2 | Add limit/offset pagination to all list endpoints | GAP-042 |
| 3 | Add react-window virtualization for email list | GAP-043 |
| 4 | Fix N+1 email sync query (single SQL with domain match) | GAP-044 |
| 5 | Encrypt Gmail tokens at rest (Fernet) | GAP-038 |
| 6 | Move API keys from URL params to headers where possible | GAP-039 |

---

## Sprint Execution Order

```
Sprint H1 (Auth)     ━━━━━━━━━━━━━━━━ 16h  ← DO FIRST (blocks everything)
Sprint H2 (Validation) ━━━━━━━━━━━━ 10h  ← Can parallel with H3
Sprint H3 (Extension)  ━━━━━━━━━━━━━ 12h  ← Can parallel with H2
Sprint H4 (Infra)      ━━━━━━━━━━━━━━━━ 16h  ← After H1
Sprint H5 (Monitoring)  ━━━━━━━━━━━━ 10h  ← After H4
Sprint H6 (Frontend)    ━━━━━━━━ 8h    ← Can parallel with H5
Sprint H7 (Perf/Data)   ━━━━━━━━━━━━ 12h  ← After H5

Total: ~84 hours
Critical path: H1 → H4 → H5 → H7 = 54 hours
With parallelism: ~60 hours (1.5 weeks at 40h/week)
```

---

## Risk Matrix

| Risk | Probability | Impact | Mitigation Sprint |
|------|------------|--------|-------------------|
| Token theft via XSS | HIGH | CRITICAL | H1 |
| Unauthorized data access | HIGH | CRITICAL | H1 |
| SQL injection | MEDIUM | HIGH | H2 |
| Extension XSS | MEDIUM | HIGH | H2, H3 |
| DDoS / rate abuse | HIGH | MEDIUM | H7 |
| Production crash (no monitoring) | HIGH | HIGH | H5 |
| Store rejection (missing assets) | CERTAIN | MEDIUM | H3 |
| Data breach (unencrypted tokens) | LOW | CRITICAL | H7 |
| Deployment failure (no CI/CD) | MEDIUM | MEDIUM | H4 |
