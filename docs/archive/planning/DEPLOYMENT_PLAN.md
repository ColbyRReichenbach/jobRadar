# AppTrail — Production Deployment Plan

**Created:** 2026-03-10
**Author:** Production Team Lead Audit
**Status:** Pre-deployment — requires hardening sprints H1-H7 first

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Pre-Deployment Checklist](#2-pre-deployment-checklist)
3. [Infrastructure Setup](#3-infrastructure-setup)
4. [Backend Deployment](#4-backend-deployment)
5. [Dashboard Deployment](#5-dashboard-deployment)
6. [Chrome Extension Deployment](#6-chrome-extension-deployment)
7. [Database & Migrations](#7-database--migrations)
8. [Celery Worker Deployment](#8-celery-worker-deployment)
9. [CI/CD Pipeline](#9-cicd-pipeline)
10. [Monitoring & Alerting](#10-monitoring--alerting)
11. [Security Checklist](#11-security-checklist)
12. [Rollback Procedures](#12-rollback-procedures)
13. [Post-Launch Checklist](#13-post-launch-checklist)

---

## 1. Architecture Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Chrome     │     │  Dashboard   │     │   Landing    │
│  Extension   │     │  (Vercel)    │     │   Page       │
│  (CWS)       │     │  React+Vite  │     │  (optional)  │
└──────┬───────┘     └──────┬───────┘     └──────────────┘
       │                    │
       │    HTTPS only      │
       ▼                    ▼
┌──────────────────────────────────────┐
│        FastAPI Backend               │
│        (Railway / Render)            │
│        uvicorn + gunicorn            │
│        Port: $PORT (auto-assigned)   │
├──────────────────────────────────────┤
│  Auth: JWT (HttpOnly cookie)         │
│  Auth: Per-user API keys (extension) │
│  Rate limiting: slowapi              │
│  Monitoring: Sentry SDK             │
└──────┬──────────────┬────────────────┘
       │              │
       ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────────┐
│ Supabase │   │  Redis   │   │ Celery Worker│
│ Postgres │   │ (Upstash)│   │ (Railway)    │
│          │   │          │   │ Separate svc │
└──────────┘   └──────────┘   └──────────────┘
```

### Service Inventory

| Service | Provider | Tier | Est. Cost/mo |
|---------|----------|------|-------------|
| Backend API | Railway | Starter ($5) | $5-20 |
| Celery Worker | Railway | Starter ($5) | $5-10 |
| Dashboard | Vercel | Free/Pro | $0-20 |
| Database | Supabase | Free/Pro | $0-25 |
| Redis | Upstash | Free/Pay-as-go | $0-10 |
| Extension | Chrome Web Store | One-time $5 | $5 (once) |
| Domain | Any registrar | Annual | $12/yr |
| Sentry | Sentry.io | Free/Team | $0-26 |
| **Total** | | | **$10-110/mo** |

---

## 2. Pre-Deployment Checklist

**These items MUST be completed before any production deployment.**

### Security (from GAP.md Sprint H1)
- [ ] `JWT_SECRET` set as unique random 64-char string (not derived from API key)
- [ ] JWT expiry reduced to 1 hour with refresh token flow
- [ ] Per-user data isolation implemented (user_id on all queries)
- [ ] Per-user API keys generated and hashed in database
- [ ] Token revocation (Redis blacklist) implemented
- [ ] `VITE_API_KEY` removed from frontend bundle
- [ ] HttpOnly cookie auth flow replacing localStorage

### Secrets
- [ ] All secrets stored in Railway/Render environment variables only
- [ ] `.env` file NOT committed to git (verify: `git ls-files .env` returns empty)
- [ ] All development placeholder secrets rotated:
  - [ ] `APPTRAIL_API_KEY` — regenerate with `python3 -c "import secrets; print(secrets.token_hex(32))"`
  - [ ] `JWT_SECRET` — separate from API key, `python3 -c "import secrets; print(secrets.token_hex(32))"`
  - [ ] `ANTHROPIC_API_KEY` — rotate in Anthropic console
  - [ ] `HUNTER_API_KEY` — rotate in Hunter dashboard
  - [ ] `SERPAPI_KEY` — rotate in SerpAPI dashboard
  - [ ] `GMAIL_CLIENT_SECRET` — rotate in Google Cloud Console
  - [ ] `SUPABASE_SERVICE_ROLE_KEY` — rotate in Supabase dashboard
  - [ ] `TWILIO_AUTH_TOKEN` — rotate if using SMS

### Input Validation (from GAP.md Sprint H2)
- [ ] All Pydantic models have `Field(max_length=...)` on string fields
- [ ] LIKE queries escape special characters
- [ ] URL validation blocks private IPs and non-HTTPS schemes
- [ ] Request body size limit middleware added (1MB)

### Extension (from GAP.md Sprint H3)
- [ ] API_BASE configurable, defaults to HTTPS production URL
- [ ] Message origin validation on all handlers
- [ ] All innerHTML replaced with textContent
- [ ] Icons created (16px, 48px, 128px PNG)
- [ ] Privacy policy written and hosted
- [ ] Store listing copy and screenshots prepared

---

## 3. Infrastructure Setup

### 3.1 Domain Setup
```
apptrail.com (or similar)
├── api.apptrail.com     → Railway backend
├── app.apptrail.com     → Vercel dashboard
└── apptrail.com         → Landing page (optional)
```

DNS records:
- `api.apptrail.com` → CNAME to Railway provided domain
- `app.apptrail.com` → CNAME to Vercel provided domain

### 3.2 Supabase Database

1. Create project at supabase.com
2. Note connection string: `postgresql+asyncpg://postgres:[password]@db.[ref].supabase.co:5432/postgres`
3. Enable connection pooling (PgBouncer) — use port `6543` for pooled connections
4. Enable automated backups (7-day retention, default)
5. Set up Row Level Security (RLS) policies if using Supabase client directly

### 3.3 Upstash Redis

1. Create database at upstash.com
2. Note `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`
3. For Celery broker, use standard Redis URL: `rediss://default:[token]@[endpoint]:6379`
4. Enable eviction policy: `allkeys-lru`

---

## 4. Backend Deployment

### 4.1 Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ backend/
COPY alembic.ini .

# Production ASGI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}", "--workers", "2", "--log-level", "info"]
```

### 4.2 Procfile (Railway/Render)

```procfile
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 2 --log-level info
worker: celery -A backend.celery_app worker --loglevel=info --concurrency=4
beat: celery -A backend.celery_app beat --loglevel=info
```

### 4.3 Railway Setup

1. Connect GitHub repo
2. Set root directory: `/` (backend imports from `backend/`)
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 2`
5. Add environment variables (see Section 11)
6. Enable health checks: `GET /api/health`
7. Set memory: 1GB minimum
8. Enable auto-deploy on push to `main`

### 4.4 Environment Variables (Railway)

```
# Required
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=rediss://...
JWT_SECRET=<random-64-char>
APPTRAIL_API_KEY=<random-64-char>
ANTHROPIC_API_KEY=sk-ant-...
DASHBOARD_URL=https://app.apptrail.com

# OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...

# Optional services
HUNTER_API_KEY=...
SERPAPI_KEY=...
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=...

# Monitoring
SENTRY_DSN=https://...@sentry.io/...
LOG_LEVEL=INFO
```

---

## 5. Dashboard Deployment

### 5.1 Vercel Setup

1. Connect GitHub repo
2. Framework: Vite
3. Root directory: `dashboardv2`
4. Build command: `npm run build`
5. Output directory: `dist`
6. Environment variables:
   ```
   VITE_API_URL=https://api.apptrail.com
   ```
7. Custom domain: `app.apptrail.com`
8. Enable auto-deploy on push

### 5.2 Build Verification

```bash
cd dashboardv2
npm install
npm run build
# Verify dist/ contains index.html and assets
npx serve dist -p 3000
# Test locally against production API
```

---

## 6. Chrome Extension Deployment

### 6.1 Pre-Submission Checklist

- [ ] Icons in `extension/images/`:
  - `icon-16.png` (16×16, toolbar)
  - `icon-48.png` (48×48, extensions page)
  - `icon-128.png` (128×128, store listing)
- [ ] `manifest.json` updated:
  - `version`: "1.0.0"
  - `icons`: pointing to image files
  - `homepage_url`: "https://apptrail.com"
  - `content_security_policy`: set
  - `action.default_icon`: set
- [ ] API_BASE configurable (not hardcoded localhost)
- [ ] All XSS vectors (innerHTML) fixed
- [ ] Privacy policy URL hosted and accessible

### 6.2 Packaging Script

```bash
#!/bin/bash
# scripts/package-extension.sh
set -e

VERSION=$(jq -r '.version' extension/manifest.json)
OUTPUT="apptrail-extension-v${VERSION}.zip"

cd extension
zip -r "../${OUTPUT}" . \
  -x "*.DS_Store" \
  -x "__MACOSX/*"

echo "Packaged: ${OUTPUT}"
echo "Size: $(du -h "../${OUTPUT}" | cut -f1)"
echo ""
echo "Submit at: https://chrome.google.com/webstore/devconsole"
```

### 6.3 Chrome Web Store Submission

1. Pay one-time $5 developer fee at https://chrome.google.com/webstore/devconsole
2. Click "New Item"
3. Upload ZIP file
4. Fill in store listing:
   - **Name:** AppTrail — Job Application Tracker
   - **Summary:** Track job applications, detect career pages, and manage your pipeline from any job board.
   - **Category:** Productivity
   - **Language:** English
5. Upload screenshots (1280×800):
   - Screenshot 1: Side panel showing detected job
   - Screenshot 2: Job tracked confirmation with contacts
   - Screenshot 3: Dashboard pipeline view
6. Add privacy policy URL
7. Submit for review (2-3 business days)

### 6.4 Store Listing Copy

```
Title: AppTrail — Job Application Tracker

Summary (132 chars max):
Track job applications automatically. Detect jobs on LinkedIn, Greenhouse,
Lever & more. Organize your entire job search.

Description:
AppTrail automatically detects when you're viewing a job listing and lets you
save it to your pipeline with one click.

Features:
• Auto-detect jobs on LinkedIn, Greenhouse, Lever, Workday, Indeed, and Ashby
• One-click job tracking with company and role detection
• Find relevant contacts at the company
• Track career page visits and get nudges for companies you're interested in
• ATS submission detection (auto-mark as "applied")
• Syncs with the AppTrail dashboard for full pipeline management

Works with:
LinkedIn, Greenhouse, Lever, Workday, Indeed, Ashby, and thousands of
company career pages.

Privacy:
AppTrail only accesses job listing pages. We never read your email,
personal data, or browsing history outside of job boards. See our
full privacy policy at https://apptrail.com/privacy.
```

---

## 7. Database & Migrations

### 7.1 Initial Production Migration

```bash
# Set production DATABASE_URL
export DATABASE_URL="postgresql+asyncpg://..."

# Run all migrations
alembic upgrade head

# Verify
alembic current
# Should show: 019 (head)
```

### 7.2 Future Migrations

1. Create migration locally: `alembic revision --autogenerate -m "description"`
2. Review generated migration file
3. Test locally with PostgreSQL (not SQLite)
4. Commit migration file
5. Deploy — Railway auto-runs on deploy (add to Procfile release phase):

```procfile
release: alembic upgrade head
web: uvicorn backend.main:app ...
```

### 7.3 Backup Strategy

| Item | Method | Frequency | Retention |
|------|--------|-----------|-----------|
| Full backup | Supabase auto-backup | Daily | 7 days (free), 30 days (pro) |
| Point-in-time | Supabase PITR | Continuous | 7 days (pro plan) |
| Manual export | `pg_dump` via script | Weekly | 90 days (S3) |
| Migration rollback | `alembic downgrade -1` | On demand | N/A |

---

## 8. Celery Worker Deployment

### 8.1 Railway Separate Service

1. Create new Railway service in same project
2. Same repo, same branch
3. Start command: `celery -A backend.celery_app worker --loglevel=info --concurrency=4`
4. Same environment variables as backend
5. Memory: 1GB minimum (Playwright scraper needs memory)
6. No health check needed (worker, not web)

### 8.2 Celery Beat (Scheduler)

Option A: Run beat in same worker process:
```
celery -A backend.celery_app worker --beat --loglevel=info --concurrency=4
```

Option B: Separate beat service (recommended for multi-worker):
```
celery -A backend.celery_app beat --loglevel=info
```

### 8.3 Production Celery Config

Add to `celery_app.py`:
```python
celery_app.conf.update(
    worker_concurrency=4,
    worker_max_tasks_per_child=1000,
    task_time_limit=600,       # 10 min hard limit
    task_soft_time_limit=540,  # 9 min soft limit
    worker_prefetch_multiplier=1,  # Prevent task hoarding
)
```

### 8.4 Task Schedule (Production)

| Task | Schedule | Purpose |
|------|----------|---------|
| poll_gmail | Every 15 min | Sync new emails |
| check_followups | Daily at 9am | Flag 7-day-old apps |
| check_dead_apps | Daily at 2am | HTTP check listings |
| compute_ats_metrics | Weekly Sunday | Aggregate ATS stats |
| send_weekly_digest | Weekly Monday 8am | Email digest |

---

## 9. CI/CD Pipeline

### 9.1 GitHub Actions — Test on PR

```yaml
# .github/workflows/test.yml
name: Test
on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ --tb=short -q
        env:
          APPTRAIL_API_KEY: test-key
          ANTHROPIC_API_KEY: test-key
          DATABASE_URL: sqlite+aiosqlite:///:memory:
```

### 9.2 GitHub Actions — Deploy on Merge

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  test:
    # Same as above

  deploy-backend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to Railway
        uses: bervProject/railway-deploy@main
        with:
          railway_token: ${{ secrets.RAILWAY_TOKEN }}
          service: backend

  deploy-dashboard:
    needs: test
    # Vercel auto-deploys from GitHub — no action needed
    # Just ensure Vercel GitHub integration is enabled
```

---

## 10. Monitoring & Alerting

### 10.1 Sentry Setup

```python
# Add to backend/main.py (top of file)
import sentry_sdk
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    traces_sample_rate=0.1,  # 10% of requests traced
    environment=os.getenv("ENVIRONMENT", "production"),
)
```

### 10.2 Health Check Monitoring

Use UptimeRobot (free) or Better Uptime:
- Monitor: `GET https://api.apptrail.com/api/health`
- Interval: 5 minutes
- Alert: Email + SMS on failure
- Expected: `{"status": "ok", "checks": {"database": "ok", "redis": "ok"}}`

### 10.3 Alert Rules

| Alert | Condition | Channel | Severity |
|-------|-----------|---------|----------|
| API Down | Health check fails 3x | SMS + Email | P1 |
| Error spike | >10 errors/min | Email | P2 |
| Slow responses | p95 > 2s for 5 min | Email | P3 |
| Worker queue buildup | >100 pending tasks | Email | P2 |
| DB connections exhausted | Pool at 90% | Email | P2 |
| Disk usage > 80% | Supabase storage | Email | P3 |

---

## 11. Security Checklist

### Pre-Launch

- [ ] All secrets in environment variables (never in code)
- [ ] `.env` not in git history
- [ ] JWT_SECRET is unique random string (not derived from API key)
- [ ] JWT expiry is 1 hour (not 30 days)
- [ ] Refresh token flow implemented
- [ ] CORS restricted to `https://app.apptrail.com` + `chrome-extension://`
- [ ] Rate limiting enabled on all endpoints
- [ ] CSP headers configured on dashboard and extension
- [ ] All innerHTML replaced with safe DOM methods
- [ ] URL validation blocks SSRF
- [ ] Email validation uses EmailStr
- [ ] HTTPS enforced (no HTTP)
- [ ] Per-user data isolation verified
- [ ] Gmail tokens encrypted at rest

### Ongoing

- [ ] Rotate JWT_SECRET every 90 days
- [ ] Rotate API keys on user request
- [ ] Review Sentry for security-related errors weekly
- [ ] Update dependencies monthly (`pip-audit`, `npm audit`)
- [ ] Review Chrome extension permissions on each update

---

## 12. Rollback Procedures

### Backend Rollback

```bash
# Railway: revert to previous deployment
railway rollback

# Or redeploy specific commit
git revert HEAD
git push origin main
```

### Database Rollback

```bash
# Rollback last migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade 018
```

### Extension Rollback

Chrome Web Store doesn't support instant rollback. Options:
1. Submit previous version as new update (2-3 day review)
2. Unpublish extension temporarily
3. Users can sideload previous version

### Dashboard Rollback

```bash
# Vercel: instant rollback in dashboard
# Or via CLI
vercel rollback
```

---

## 13. Post-Launch Checklist

### Day 1
- [ ] Verify health endpoint returns healthy
- [ ] Verify OAuth login flow works end-to-end
- [ ] Verify extension can track a job
- [ ] Verify Gmail sync processes emails
- [ ] Verify Celery workers are running (check flower or logs)
- [ ] Confirm Sentry receiving events
- [ ] Confirm UptimeRobot monitoring active

### Week 1
- [ ] Review error rates in Sentry
- [ ] Check database connection pool usage
- [ ] Verify Celery Beat schedule firing correctly
- [ ] Monitor API response times (p50, p95, p99)
- [ ] Check Redis memory usage
- [ ] Review user feedback from store listing

### Month 1
- [ ] Run `pip-audit` and `npm audit` for vulnerabilities
- [ ] Review and rotate any exposed credentials
- [ ] Test backup restore procedure
- [ ] Review rate limiting effectiveness
- [ ] Assess scaling needs based on user count
- [ ] Plan next feature sprint based on user feedback

---

## Deployment Timeline

```
Week 1: Complete Sprint H1 (Auth) + H2 (Validation)
Week 2: Complete Sprint H3 (Extension) + H4 (Infrastructure)
Week 3: Complete Sprint H5 (Monitoring) + H6 (Frontend)
         Submit extension to Chrome Web Store
Week 4: Sprint H7 (Performance) + Final QA
         Deploy backend + dashboard to production
         Extension approved → goes live
Week 5: Post-launch monitoring + bug fixes
```

**Target launch date:** 4 weeks from start of hardening sprints.
