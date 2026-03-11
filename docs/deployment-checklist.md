# Deployment Checklist

## Chosen Stack

- Dashboard: Vercel
- Backend web API: Railway
- Celery worker: Railway
- Celery beat: Railway
- PostgreSQL: Railway managed Postgres
- Redis: Railway managed Redis

## Railway Services

Create one Railway project with these services:

1. `web`
   - Source: this repo
   - Runtime: `backend/Dockerfile`
   - Start command: `gunicorn -c gunicorn.conf.py backend.main:app`

2. `worker`
   - Source: this repo
   - Runtime: `backend/Dockerfile`
   - Start command: `celery -A backend.celery_app:celery_app worker --loglevel=info`

3. `beat`
   - Source: this repo
   - Runtime: `backend/Dockerfile`
   - Start command: `celery -A backend.celery_app:celery_app beat --loglevel=info`

4. `postgres`
   - Railway managed Postgres

5. `redis`
   - Railway managed Redis

## Vercel Project

Create one Vercel project for `dashboardv2/`.

- Root directory: `dashboardv2`
- Framework preset: Vite
- Required env var:
  - `VITE_API_URL=https://<your-backend-domain>`

## Required Backend Environment Variables

Set these on all Railway runtime services unless noted otherwise.

### Required

- `ENVIRONMENT=production`
- `JWT_SECRET=<strong-random-secret>`
- `DATABASE_URL=<Railway Postgres asyncpg URL>`
- `REDIS_URL=<Railway Redis URL>`
- `DASHBOARD_URL=https://<your-vercel-domain>`
- `GMAIL_CLIENT_ID=<google-oauth-client-id>`
- `GMAIL_CLIENT_SECRET=<google-oauth-client-secret>`
- `GOOGLE_REDIRECT_URI=https://<your-backend-domain>/api/auth/google/callback`
- `APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY=<valid-fernet-key>`
- `ANTHROPIC_API_KEY=<anthropic-key>`

### Required if you use these features

- `SERPAPI_KEY=<serpapi-key>`
- `HUNTER_API_KEY=<hunter-key>`
- `TWILIO_ACCOUNT_SID=<twilio-sid>`
- `TWILIO_AUTH_TOKEN=<twilio-auth-token>`
- `TWILIO_FROM_NUMBER=<twilio-number>`

### Recommended

- `RATE_LIMIT_STORAGE_URI=<same as REDIS_URL>`
- `WEB_CONCURRENCY=2`
- `DB_POOL_SIZE=10`
- `DB_MAX_OVERFLOW=20`
- `DB_POOL_TIMEOUT_SECONDS=30`
- `DB_POOL_RECYCLE_SECONDS=1800`
- `CELERY_CONCURRENCY=4`
- `CELERY_PREFETCH_MULTIPLIER=1`
- `CELERY_MAX_TASKS_PER_CHILD=100`
- `CELERY_SOFT_TIME_LIMIT_SECONDS=300`
- `CELERY_TIME_LIMIT_SECONDS=600`
- `CELERY_RESULT_EXPIRES_SECONDS=3600`

### Optional Observability

- `SENTRY_DSN=<sentry-dsn>`
- `SENTRY_ENVIRONMENT=production`
- `SENTRY_TRACES_SAMPLE_RATE=0.1`
- `APP_VERSION=<git-sha-or-release-tag>`
- `PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus`

## Variables You Do Not Need For This Stack

- `APPTRAIL_API_KEY`
  - Legacy/testing fallback only. Production extension auth is now per-user.
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
  - The current production plan uses Railway Postgres, not Supabase.

## Generate Missing Secrets

### JWT secret

```bash
openssl rand -hex 32
```

### Gmail token encryption key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Google OAuth Setup

In Google Cloud Console, update the OAuth client to include:

- Authorized redirect URI:
  - `https://<your-backend-domain>/api/auth/google/callback`

Local development can keep:

- `http://localhost:8000/api/auth/google/callback`

## GitHub Secrets For Existing Deploy Workflow

The repo already has a deploy workflow in `.github/workflows/deploy.yml`.

Set these GitHub Actions secrets if you want push-to-main deploys:

### Railway

- `RAILWAY_API_TOKEN`
- `RAILWAY_PROJECT_ID`
- `RAILWAY_ENVIRONMENT`
- `RAILWAY_SERVICE`

Note: the current workflow deploys one Railway service. If you want full CI deploy automation for `web`, `worker`, and `beat`, expand the workflow to deploy each service explicitly.

### Vercel

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

## Deployment Order

1. Create Railway project and add Postgres + Redis.
2. Create Railway `web`, `worker`, and `beat` services from this repo.
3. Set all Railway env vars.
4. Assign a public Railway domain to the `web` service.
5. Create the Vercel project for `dashboardv2/`.
6. Set `VITE_API_URL` in Vercel to the Railway backend URL.
7. Deploy Vercel and note the final dashboard URL.
8. Update Railway `DASHBOARD_URL` to the final Vercel URL.
9. Update Google OAuth redirect URI to the Railway backend callback URL.
10. Run database migrations:
    - via Railway release command, or
    - manually: `alembic upgrade head`
11. Smoke test:
    - `GET /api/health`
    - Google sign-in
    - Gmail connect
    - Calendar connect
    - manual Gmail sync
    - create one application
    - generate one resume draft
    - extension API key generation

## Recommended First Production Domain Layout

- Dashboard: `https://app.apptrail.com`
- Backend API: `https://api.apptrail.com`

That keeps OAuth, CORS, and `VITE_API_URL` clear and predictable.

## Notes

- Keep `worker` and `beat` separate from `web`. Do not run Celery inside the API process.
- Start with Railway managed Postgres/Redis first. You can swap to external managed providers later if needed.
- If you want to close GAP-003 next, use the Railway Redis instance as the shared revocation/rate-limit store.
