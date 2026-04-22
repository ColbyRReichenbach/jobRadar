# Deployment Checklist

This checklist covers the current deployment shape for AppTrail and the minimum steps to bring up a working production environment.

## Recommended Production Layout

- Dashboard: Vercel
- Backend API: Railway or another container host
- Celery worker: separate service on the same host
- Celery beat: separate service on the same host
- Database: PostgreSQL
- Queue and ephemeral auth state: Redis

That split matches the product design. The dashboard is static-plus-API, while the backend, worker, and scheduler have different runtime profiles and should be deployable independently.

## Local Docker Stack

For local verification, the repo already supports a full Docker workflow:

```bash
make local-env
make local-up
```

Or the one-command startup path:

```bash
make local-open
```

The local stack brings up:

- Postgres
- Redis
- migration job
- backend API
- Celery worker
- Celery beat
- dashboard

## Required Backend Environment Variables

These should be set on the backend API and any worker process unless noted otherwise.

### Core

- `ENVIRONMENT=production`
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `DASHBOARD_URL`
- `APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY`

### Google auth and Gmail

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`

### Product integrations

- `OPENAI_API_KEY` for classification, drafting, resume parsing, and resume tailoring
- `HUNTER_API_KEY` if contact enrichment is enabled
- `SERPAPI_KEY` if job search is enabled
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER` if SMS alerts are enabled

### Observability

- `SENTRY_DSN` if Sentry is enabled
- `SENTRY_ENVIRONMENT`
- `PROMETHEUS_MULTIPROC_DIR` if you are exporting metrics from multi-process workers

## Dashboard Environment Variables

- `VITE_API_URL=https://<backend-domain>`
- `VITE_CHROME_EXTENSION_URL=https://chromewebstore.google.com/detail/apptrail/<extension-id>` once the extension is published

`VITE_LOCAL_DEV_AUTH` is for local-only workflows and should stay off in production.

## Service Start Commands

### Backend API

```bash
gunicorn -c gunicorn.conf.py backend.main:app
```

### Worker

```bash
celery -A backend.celery_app:celery_app worker --loglevel=info
```

### Beat

```bash
celery -A backend.celery_app:celery_app beat --loglevel=info
```

## Deployment Order

1. Provision PostgreSQL and Redis.
2. Set backend secrets and environment variables.
3. Deploy the backend API.
4. Run `alembic upgrade head`.
5. Deploy the worker and beat services against the same code revision.
6. Deploy the dashboard with the correct `VITE_API_URL`.
7. Verify Google OAuth redirect URIs match the deployed backend.
8. Verify extension backend hosts if the extension will talk to production.

## Pre-Launch Checks

- `pytest -q` passes on the release commit
- dashboard production build succeeds
- migrations apply cleanly from the previous production version
- Google sign-in works
- refresh-token flow works
- Gmail connect and manual sync work
- a worker can pick up scheduled jobs
- `/metrics` is reachable from your monitoring system
- `GET /api/ai/metrics` is protected and works for authenticated users

## Post-Launch Checks

- create a test account and sign in end to end
- connect Gmail and trigger a sync
- save a job through the dashboard
- save a job through the extension
- verify the worker processes scheduled tasks
- confirm logs, Sentry, and metrics are visible

## Release Notes To Keep Current

When the production setup changes, update this file first. It is the operational deployment document for the repo. Historical deployment thinking now lives in the archive.
