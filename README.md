# AppTrail

AppTrail is a job-search OS for people who need one place to run the whole process: track applications, save roles from the browser, sync Gmail, follow recruiter conversations, manage contacts, prep for interviews, and research opportunities without losing the thread across tabs, inboxes, and spreadsheets.

The product is built around a simple idea: once a role matters, it should not disappear. The application, the email trail, the people involved, the source page, and the next action should live in the same system.

## What It Does

AppTrail has a few connected pieces:

- A dashboard for the application pipeline, inbox, conversations, network, calendar, job search, Radar, analytics, classifier audit, extraction reports, profile, and settings.
- A Chrome extension that detects supported job pages, extracts job details, opens a side panel for review, saves roles, queues work offline, and can optionally track repeated career-page visits or application-submission signals.
- Gmail sync and classification, so application confirmations, recruiter replies, interview messages, and noisy job alerts can be routed into the right product behavior.
- Contact and recruiter context next to the applications they belong to.
- Resume parsing and tailoring for specific roles.
- Opportunity Radar, a research workflow for surfacing useful signals from the user's existing job-search data.

The important part is that these are not isolated features. Email classification affects application state. Extension captures affect source intelligence. Radar recommendations can become actions. The system is designed around those downstream effects, not just around storing records.

## Who It Is For

AppTrail is for active job searches where volume and follow-through matter. It is useful when:

- you are tracking enough roles that a spreadsheet starts falling apart
- you want Gmail and application state tied together
- you care about recruiter follow-up timing
- you want browser capture without context switching
- you want research and next actions attached to the roles they came from

## Running It Locally

Fastest path:

```bash
make local-open
```

That prepares local env defaults, starts Docker services, runs migrations, brings up the backend, worker, scheduler, and dashboard, then opens the app.

Standard local flow:

```bash
make local-env
make local-up
```

Useful follow-ups:

```bash
make local-logs
make local-down
make local-reset
```

Manual backend flow:

```bash
make local-env
pip install -r requirements.txt
playwright install chromium
alembic upgrade head
uvicorn backend.main:app --reload --port 8000
```

Manual backend commands load `.env.local` when it exists, so local development uses local Postgres instead of the hosted Neon database.

Worker and scheduler:

```bash
celery -A backend.celery_app:celery_app worker --loglevel=info
celery -A backend.celery_app:celery_app beat --loglevel=info
```

Dashboard:

```bash
cd dashboardv2
npm install
npm run dev
```

## Privacy And Control

AppTrail handles sensitive job-search data, so the privacy model is part of the product design, not an afterthought.

- Gmail and enrichment flows are consent-aware.
- Gmail tokens are encrypted at rest.
- The extension uses a user-scoped API key and only syncs saved jobs or opt-in extension activity.
- AI-heavy flows use deterministic logic first where product side effects matter.
- LLM adjudication is reserved for bounded, preflight-safe cases.

Policy docs:

- [Privacy Policy](docs/privacy-policy.md)
- [Security Model](SECURITY.md)

## Active Documentation

- [docs/README.md](docs/README.md): documentation map and retention policy
- [TECHNICAL.md](TECHNICAL.md): architecture, tradeoffs, and implementation details
- [docs/production-readiness-audit.md](docs/production-readiness-audit.md): dated launch-readiness audit and remediation record
- [SECURITY.md](SECURITY.md): auth, secrets, consent, extension security, and operational safeguards
- [docs/deployment-checklist.md](docs/deployment-checklist.md): deployment and rollout checklist
- [docs/privacy-policy.md](docs/privacy-policy.md): product privacy policy
- [docs/radar-research-spec.md](docs/radar-research-spec.md): Radar research implementation spec
- [docs/source-intelligence-job-search-spec.md](docs/source-intelligence-job-search-spec.md): source intelligence and direct job-search reliability spec
- [extension/store/listing.md](extension/store/listing.md): Chrome Web Store listing copy
- [extension/store/SUBMISSION_GUIDE.md](extension/store/SUBMISSION_GUIDE.md): extension submission workflow
- [extension/store/privacy-fields.md](extension/store/privacy-fields.md): Chrome Web Store privacy and permission form copy
- [extension/store/beta-scope.md](extension/store/beta-scope.md): controlled extension beta scope
- [backend/PROMPT_REGISTRY.md](backend/PROMPT_REGISTRY.md): internal prompt registry generated from code
- [evals/](evals/): sanitized eval datasets and labeling guidelines
- [docs/ai-artifacts/](docs/ai-artifacts/): AI evaluation, governance, and model-risk artifacts
- [docs/archive/README.md](docs/archive/README.md): historical plans, audits, and retired working docs

## Extension Release Checks

Run the controlled-beta gate locally:

```bash
bash scripts/release/run_beta_readiness_checks.sh
```

Build the Chrome Web Store submission bundle:

```bash
bash scripts/release/package_chrome_webstore.sh
```

The package script writes the runtime ZIP, store copy, and PNG store assets to `dist/chrome-webstore/`.

To include an installed Chrome extension smoke against a target backend, pass secrets through environment variables rather than writing them to disk:

```bash
APPTRAIL_EXTENSION_API_BASE=https://api.apptrail.com \
APPTRAIL_EXTENSION_API_KEY=... \
APPTRAIL_EXTENSION_EXPECTED_EMAIL=you@example.com \
node scripts/release/smoke_chrome_extension.mjs
```

The smoke opens Chrome with the unpacked extension, validates the key through the setup page, confirms the key is stored in extension storage, and clears it from the temporary profile by default. Set `APPTRAIL_EXTENSION_CREATE_SMOKE_JOB=1` only when you intentionally want to create a disposable pipeline item in the target account.
