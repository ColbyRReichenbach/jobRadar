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
- `DASHBOARD_URL` set to the exact production dashboard origin
- `CORS_ALLOWED_ORIGINS` for any additional exact dashboard/staging origins
- `CHROME_EXTENSION_ID` for the published extension origin
- `APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY`
- `SOURCE_LINK_ENCRYPTION_KEY`
- `SOURCE_LINK_ENCRYPTION_KEY_VERSION=v1`
- `SOURCE_LINK_HASH_KEY`
- `SOURCE_LINK_HASH_KEY_VERSION=v1`
- `GMAIL_CLASSIFIER_MODE=hybrid_dry_run` for the initial deterministic dry-run release. Change to `hybrid` only after reviewing dry-run artifacts and enabling preflight-gated LLM adjudication.
- `METRICS_BEARER_TOKEN` for Prometheus scraping in production
- `READINESS_REQUIRE_CELERY=true`
- `RADAR_ENABLED=true` for beta users, or `false` to disable all Radar API access and scheduled dispatch without a deploy
- `RADAR_DISPATCH_INTERVAL_SECONDS=900` by default; increase for constrained environments if Radar can tolerate slower scheduled dispatch
- `RADAR_RESEARCH_ENABLED=false` until public-web research and hybrid trackers are approved for the target environment
- `RADAR_ALERT_MAX_PER_USER_PER_DAY=5` or lower for constrained beta cohorts
- `COPILOT_ENABLED=false` until Copilot backend, frontend, evals, security tests, and admin telemetry are green
- `COPILOT_DAILY_COST_CAP_CENTS_PER_USER`
- `COPILOT_GLOBAL_DAILY_COST_CAP_CENTS`
- `COPILOT_MAX_REQUESTS_PER_MINUTE`
- `COPILOT_MAX_CONTEXT_DOCS`
- `COPILOT_MAX_CONTEXT_TOKENS`
- `COPILOT_MAX_MESSAGE_CHARS`
- `COPILOT_MAX_CONVERSATION_MESSAGES`
- `COPILOT_SHADOW_TEST_RATE`
- `COPILOT_EXPERIMENTS_ENABLED=false` until experiment governance and admin review are ready
- `SEARCH_BACKEND=postgres` unless OpenSearch infrastructure is explicitly configured
- `OPENSEARCH_URL` only when `SEARCH_BACKEND=opensearch`
- `SEARCH_OPENSEARCH_FALLBACK_TO_POSTGRES=true` unless intentionally testing fail-closed search behavior
- `AI_TRACE_FULL_PAYLOADS_ENABLED=false`
- `AI_FULL_TRACE_EXPORT_ENABLED=false`
- `AI_TRACE_RETENTION_DAYS`
- `AI_PROMOTION_REPORT_MIN_CALLS`
- `AI_PROMOTION_REPORT_MIN_FEEDBACK`
- `AI_MODEL_PRICING_CONFIG` if default model pricing needs an override
- `AI_MAX_INPUT_TOKENS_PER_REQUEST=12000` for beta, lower if Gmail payloads are too large
- `AI_DAILY_TOKEN_CAP_PER_USER=150000` for beta users
- `AI_GLOBAL_DAILY_TOKEN_CAP=1000000` for the beta environment
- `AI_TASK_DAILY_TOKEN_CAP=500000` per AI task
- `AI_RATE_LIMIT_PER_MINUTE_PER_USER=20`
- `AI_RATE_LIMIT_PER_MINUTE_PER_TASK=120`
- `AI_RATE_LIMIT_PER_MINUTE_GLOBAL=300`
- `AI_QUARANTINE_PROMPT_RISK_THRESHOLD=0.70`
- `AI_ADMIN_ALERTS_ENABLED=true`
- `AI_SEMANTIC_PROMPT_GUARD_ENABLED=false` unless the semantic guard dependency and model are explicitly provisioned
- `POSTGRES_BACKUPS_ENABLED=true`
- `POSTGRES_BACKUP_PROVIDER` set to the provider or plan, for example `Neon automated backups`

### Google auth and Gmail

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `SCHEDULED_DB_JOBS_ENABLED=true` only when scheduled DB-backed worker jobs are required. Set `false` for idle/non-beta environments to let Neon scale to zero.
- `GMAIL_POLLING_ENABLED=true` only when scheduled Gmail polling is required in this environment
- `GMAIL_POLL_INTERVAL_SECONDS=900` by default; increase or disable for idle environments to reduce Neon wakeups

### Product integrations

- `OPENAI_API_KEY` for classification, drafting, resume parsing, and resume tailoring
- `HUNTER_API_KEY` if contact enrichment is enabled
- `SERPAPI_KEY` if job search is enabled
- `JOB_SOURCE_VERIFICATION_BEAT_ENABLED=false` until direct job-source verification is actively needed
- `SOURCE_VERIFICATION_INTERVAL_SECONDS=900` when source verification beat is enabled
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER` if SMS alerts are enabled

### Observability And Readiness

- `SENTRY_DSN` if Sentry is enabled
- `SENTRY_ENVIRONMENT`
- `PROMETHEUS_MULTIPROC_DIR` if you are exporting metrics from multi-process workers
- `HEALTH_CHECK_DATABASE=false` for uptime monitors and platform liveness probes. Enable only when `/api/health` is intentionally used as a deep dependency check.
- `HEALTH_CHECK_REDIS=false` for uptime monitors and platform liveness probes. Enable only when `/api/health` is intentionally used as a deep dependency check.
- `CELERY_BEAT_MAX_AGE_SECONDS` if the default 180 second beat freshness threshold is not appropriate
- `CELERY_READINESS_TIMEOUT_SECONDS` if worker ping needs a longer timeout

## Dashboard Environment Variables

- `VITE_API_URL=https://api.apptrail.com`
- `VITE_CHROME_EXTENSION_URL=https://chromewebstore.google.com/detail/apptrail/<extension-id>` once the extension is published
- `VITE_COPILOT_ENABLED=false` until the Copilot frontend is backed by secured production APIs

`VITE_LOCAL_DEV_AUTH` is for local-only workflows and should stay off in production.

The Chrome extension is configured for `https://api.apptrail.com`. Production backend traffic should be routed through that canonical API domain before Web Store submission.

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

## CI/CD Gates

Pull requests must pass:

- backend tests through `scripts/ci/run_backend_checks.sh`
- Alembic single-head and Postgres migration checks
- dashboard type-check, production build, and Playwright smoke tests through `scripts/ci/run_dashboard_checks.sh`
- targeted AI/security/contract checks through `scripts/ci/run_ai_feature_checks.sh`
- opt-in live OpenAI smoke checks before beta promotion: `RUN_LIVE_OPENAI_TESTS=1 pytest -q tests/test_live_openai_hardening.py`
- dependency audits
- `git diff --check`

Production promotion requires:

- the `CI` workflow succeeded for the release commit
- required Railway, Vercel, API URL, and dashboard URL deployment configuration is present
- migrations run successfully before worker and beat deployment
- post-deploy smoke checks pass through `scripts/ci/run_post_deploy_smoke.sh`
- `/api/health` returns success without touching external dependencies
- `/api/ready` returns success when a deliberate database, Redis, worker, and beat readiness check is needed
- admin-only operational endpoints deny unauthenticated requests
- feature flags are set deliberately for Radar, Copilot, experiments, search backend, and trace access

## Pre-Launch Checks

- `pytest -q` passes on the release commit
- `python3 -m compileall -q backend` passes on the release commit
- dashboard production build succeeds
- dashboard Playwright smoke tests pass
- migrations apply cleanly from the previous production version
- `alembic heads` reports exactly one head
- CI helper scripts pass locally or in CI
- Google sign-in works
- refresh-token flow works
- Gmail connect and manual sync work
- a worker can pick up scheduled jobs
- platform health checks and uptime monitors are pointed at `/api/live` or `/api/health`, not `/api/ready`
- `/api/ready` returns 200 with database, Redis, worker, and beat checks healthy
- `/metrics` is reachable from your monitoring system with `METRICS_BEARER_TOKEN`
- `GET /api/ai/metrics` is admin-only
- Radar beta posture is deliberate: `RADAR_ENABLED`, `RADAR_RESEARCH_ENABLED`, and `RADAR_ALERT_MAX_PER_USER_PER_DAY` match the launch plan
- AI platform posture is deliberate: `COPILOT_ENABLED`, `COPILOT_EXPERIMENTS_ENABLED`, `SEARCH_BACKEND`, `AI_TRACE_FULL_PAYLOADS_ENABLED`, `AI_FULL_TRACE_EXPORT_ENABLED`, and AI budget caps match the launch plan
- production readiness env gate passes: `python3 scripts/deploy/check_production_readiness.py`
- AI safety quarantines and blocks are visible in Admin AI Ops and can be reviewed as confirmed unsafe, false positive, dismissed, or needing reprocessing

## Post-Launch Checks

- create a test account and sign in end to end
- connect Gmail and trigger a sync
- save a job through the dashboard
- save a job through the extension
- verify the worker processes scheduled tasks
- confirm logs, Sentry, and metrics are visible
- confirm AI safety, budget, and rate-limit alerts appear for admin users
- confirm Celery beat heartbeat freshness stays within threshold
- confirm the active Celery beat schedule matches the intended cost posture: `SCHEDULED_DB_JOBS_ENABLED`, Gmail polling, Radar dispatch, and source verification should be disabled or slowed when idle
- confirm non-admin users receive 403 from audit, metrics, and extraction admin endpoints
- confirm flipping `RADAR_ENABLED=false` blocks `/api/research/*` and stops scheduled Radar dispatch in the target environment
- confirm flipping `COPILOT_ENABLED=false` blocks Copilot access after Copilot is implemented
- confirm full AI trace payload access remains disabled unless explicitly approved
- confirm post-deploy smoke checks have logs/artifacts attached to the deployment run

## Incident Runbooks

### Deploy Rollback

1. Stop additional deploys.
2. Promote the last known-good dashboard deployment in Vercel.
3. Redeploy the last known-good Railway API, worker, and beat revisions.
4. Confirm `/api/ready` returns 200 and smoke-check login, job save, Gmail sync, and worker heartbeat.
5. If the release included a database migration, follow the migration rollback section before reopening traffic.

### Migration Failure

1. Leave the failed release out of rotation or roll the API/worker/beat back to the previous revision.
2. Inspect `alembic_version` and migration logs to identify the last applied revision.
3. If a downgrade is supported for the failed migration, run `alembic downgrade -1` against the production database.
4. If downgrade is not safe, restore from the latest verified backup or apply a forward-fix migration.
5. Re-run `/api/ready` and a production smoke check before resuming deploys.

### Database Backup And Restore

1. Verify automated PostgreSQL backups are enabled before launch and record `POSTGRES_BACKUPS_ENABLED=true` plus `POSTGRES_BACKUP_PROVIDER`.
2. Before high-risk migrations, take a manual backup/snapshot.
3. Restore into staging first and run `alembic upgrade head`, `pytest` against staging-compatible config, and dashboard smoke checks.
4. Restore production only after rollback/fix-forward options are rejected.

### Redis Outage

1. Expect auth-code exchange, refresh-token blacklist, rate limits, Celery broker, and worker scheduling to degrade.
2. Check provider status and Redis connectivity from API, worker, and beat services.
3. Rotate `REDIS_URL` to a healthy instance if needed and restart API, worker, and beat.
4. Confirm `/api/ready` returns 200 and Celery beat heartbeat freshness recovers.

### Worker Or Beat Outage

1. Check `/api/ready` for `celery_worker` and `celery_beat` status.
2. Restart the failed Railway worker or beat service.
3. Confirm `record-beat-heartbeat` updates within `CELERY_BEAT_MAX_AGE_SECONDS`.
4. Check failed Celery task logs for Gmail polling, followups, dead apps, ATS metrics, weekly digest, and Radar dispatch.

### Radar Disable Or Beta Rollback

1. Set `RADAR_ENABLED=false` to disable all Radar API access and scheduled dispatch.
2. Set `RADAR_RESEARCH_ENABLED=false` to keep internal Radar available while blocking public-web research and hybrid trackers.
3. Lower `RADAR_ALERT_MAX_PER_USER_PER_DAY` or set it to `0` if Radar alerts are too noisy.
4. Restart/reload the API, worker, and beat services if the platform does not apply environment changes live.
5. Confirm `/api/research/profiles` returns `404` when Radar is disabled, and that Celery beat stops queueing Radar runs.
6. Re-enable only after consent copy, notification volume, and run quality are verified.

### AI Platform Or Copilot Disable

1. Set `COPILOT_ENABLED=false` to disable Copilot access without a deploy.
2. Set `COPILOT_EXPERIMENTS_ENABLED=false` to stop A/B and shadow experiment routing.
3. Set `AI_TRACE_FULL_PAYLOADS_ENABLED=false` and `AI_FULL_TRACE_EXPORT_ENABLED=false` unless full trace access is actively approved.
4. Lower `COPILOT_DAILY_COST_CAP_CENTS_PER_USER` and `COPILOT_GLOBAL_DAILY_COST_CAP_CENTS` if spend rises unexpectedly.
5. Set `SEARCH_BACKEND=postgres` if OpenSearch degrades and the Postgres fallback is acceptable.
6. Confirm admin telemetry still shows model-call, token, cost, fallback, and failure data once Admin AI Ops is implemented.
7. Re-enable only after targeted AI feature tests, security tests, and post-deploy smoke checks pass.

### Secret Rotation

1. Add the new secret value to API, worker, and beat services.
2. Deploy/restart all backend services from the same revision.
3. For `JWT_SECRET`, force sign-out or coordinate a dual-secret migration before rotation.
4. For Google OAuth credentials, update Google Cloud redirect URIs before switching production.
5. For `APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY`, do not rotate without a token re-encryption migration.
6. For `SOURCE_LINK_ENCRYPTION_KEY` and `SOURCE_LINK_HASH_KEY`, do not rotate without a private-link re-encryption and HMAC rehash migration.

### Extension Release Rollback

1. If the issue is API-side, disable or roll back the affected backend behavior first.
2. If the issue is extension-side, submit a rollback build to the Chrome Web Store.
3. Keep `https://api.apptrail.com` stable; changing host permissions requires a new Web Store review.
4. Revoke compromised API keys from affected users if extension credential handling is involved.

## Release Notes To Keep Current

When the production setup changes, update this file first. It is the operational deployment document for the repo. Historical deployment thinking now lives in the archive.
