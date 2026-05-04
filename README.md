# AppTrail

AppTrail is a job search operating system for people who want one place to run the whole process. It combines a web dashboard, a Chrome extension, Gmail sync, recruiter contact tracking, resume tooling, interview prep, and an opportunity research workflow called Radar.

The product is built around a simple idea: once a role matters to you, it should not disappear into a spreadsheet, an inbox, or a pile of open tabs. AppTrail keeps the application, the related email, the people involved, and the next action in the same system.

## What AppTrail Does

- Tracks jobs you save from the browser extension or add from the dashboard
- Organizes the pipeline by stage, company, and status
- Pulls hiring-related email into the product and classifies it automatically
- Keeps recruiter and contact information next to the application it belongs to
- Stores interview notes, interview history, and follow-up context
- Parses and tailors resumes for specific roles
- Searches for new roles and highlights which ones are worth attention
- Runs Opportunity Radar to surface useful signals from the data you already have

## Main Surfaces

### Dashboard

The dashboard is the working surface for the product. It includes:

- Pipeline board
- Inbox
- Conversations
- Network
- Calendar
- Job Search
- Opportunity Radar
- Analytics
- Classifier Audit
- Extraction Reports
- Profile and Settings

### Chrome Extension

The extension handles capture while you browse. It can:

- detect supported job pages across major ATS platforms
- open a side panel with extracted job details
- let you edit and save a role without leaving the tab
- optionally track repeated career-page visits after you enable that setting
- optionally detect common application submission pages as review signals
- queue activity locally when the browser is offline and sync later

### Background Services

The backend and worker processes handle the long-running parts of the product:

- Gmail sync
- email classification
- recruiter/contact enrichment
- job parsing
- notifications
- recurring maintenance jobs

## Who It Is For

AppTrail is designed for an active job search where volume and follow-through matter. It is especially useful when:

- you are tracking many applications at once
- you want email and application state tied together
- you care about follow-up timing
- you want a browser-based workflow instead of a spreadsheet

## Running It Locally

### Fastest path

```bash
make local-open
```

That command prepares a local environment file, starts Docker services, runs migrations, brings up the backend, worker, scheduler, and dashboard, then opens the app in the browser.

### Standard local flow

```bash
make local-env
make local-up
```

Useful follow-up commands:

```bash
make local-logs
make local-down
make local-reset
```

### Manual development flow

If you want to run services separately:

```bash
pip install -r requirements.txt
playwright install chromium
alembic upgrade head
uvicorn backend.main:app --reload --port 8000
```

In another terminal:

```bash
celery -A backend.celery_app:celery_app worker --loglevel=info
celery -A backend.celery_app:celery_app beat --loglevel=info
```

And for the dashboard:

```bash
cd dashboardv2
npm install
npm run dev
```

## Privacy And Control

AppTrail has explicit consent controls for data processing and third-party enrichment. The extension only runs on supported job-related pages, uses a user-scoped API key stored locally until you clear it, and syncs only saved jobs or opt-in extension activity.

For policy details, see:

- [Privacy Policy](docs/privacy-policy.md)
- [Security Model](SECURITY.md)

## Active Documentation

- [TECHNICAL.md](TECHNICAL.md): architecture, tradeoffs, and implementation details
- [docs/radar-research-spec.md](docs/radar-research-spec.md): full implementation spec for the next Radar research system
- [docs/production-readiness-audit.md](docs/production-readiness-audit.md): current launch-readiness audit with blocking and non-blocking production gaps
- [SECURITY.md](SECURITY.md): auth, secrets, consent, extension security, and operational safeguards
- [docs/deployment-checklist.md](docs/deployment-checklist.md): deployment and rollout checklist
- [docs/privacy-policy.md](docs/privacy-policy.md): product privacy policy
- [extension/store/listing.md](extension/store/listing.md): Chrome Web Store listing copy
- [extension/store/SUBMISSION_GUIDE.md](extension/store/SUBMISSION_GUIDE.md): extension submission workflow
- [backend/PROMPT_REGISTRY.md](backend/PROMPT_REGISTRY.md): internal prompt registry generated from code
- [docs/archive/README.md](docs/archive/README.md): historical plans, audits, and retired working docs
