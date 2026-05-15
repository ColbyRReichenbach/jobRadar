---
project_id: apptrail
title: AppTrail Job Search OS
project_tags: Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, Celery, Gmail API, Google OAuth, OpenAI, LangGraph, retrieval, search indexing, browser extension, React, TypeScript, AI governance, privacy, model evaluation, product analytics
---

- [CUR-APPTRAIL-FASTAPI-SCHEMA] Built a FastAPI backend with async SQLAlchemy, Alembic migrations, and 64 ORM classes covering applications, contacts, emails, interviews, jobs, source intelligence, research radar, copilot, and AI governance.
  evidence_skills: FastAPI, SQLAlchemy, Alembic, PostgreSQL, backend architecture, data modeling
- [CUR-APPTRAIL-SERVICE-LAYER] Split product logic into domain services for AI orchestration, safety, email classification, draft writing, resume parsing, resume tailoring, research radar, search, source intelligence, job sources, ATS intelligence, and contact enrichment.
  evidence_skills: service architecture, domain services, AI orchestration, backend modularity
- [CUR-APPTRAIL-CELERY-GMAIL] Implemented Celery over Redis with scheduled jobs for Gmail polling, follow-up checks, dead-application checks, ATS metrics, weekly digests, research radar dispatch, heartbeat, and job-source verification.
  evidence_skills: Celery, Redis, scheduled jobs, background workers, Gmail polling
- [CUR-APPTRAIL-GMAIL-SYNC] Built Gmail and Google sync support as part of the job-search workflow, including email classification and downstream application/interview suggestions.
  evidence_skills: Gmail API, Google OAuth, email classification, workflow automation
- [CUR-APPTRAIL-JOB-CAPTURE] Built a Chrome Manifest V3 extension that extracts job title, company, location, description, salary, and application URLs from job boards through structured data, ATS APIs, platform-specific selectors, and generic fallbacks.
  evidence_skills: Chrome extension, Manifest V3, job extraction, structured data, ATS parsing
- [CUR-APPTRAIL-EXTENSION-PLATFORMS] Supported extraction from LinkedIn, Greenhouse, Lever, Workday, Ashby, Indeed, Glassdoor, ZipRecruiter, Wellfound, SmartRecruiters, iCIMS, Jobvite, BambooHR, Rippling, and generic pages.
  evidence_skills: browser extension, ATS integrations, web scraping, platform selectors
- [CUR-APPTRAIL-RESEARCH-RADAR-GRAPH] Implemented a bounded LangGraph research workflow with explicit nodes for tracker context, brief normalization, planning, search, document fetching, evidence extraction, dedupe/ranking, report writing, verification, persistence, alerting, and rescheduling.
  evidence_skills: LangGraph, AI workflow orchestration, retrieval, evidence extraction, ranking
- [CUR-APPTRAIL-AI-ORCHESTRATOR] Built task configuration for email classification, draft writing, resume tailoring, resume parsing, job extraction, research brief normalization, search planning, evidence extraction, report writing, report verification, source intelligence, and copilot behavior.
  evidence_skills: AI orchestration, task configuration, prompt routing, model governance
- [CUR-APPTRAIL-AI-COST-TRACE] Recorded AI model calls, token usage, prompt versions, costs, task metadata, and trace access for AI operations and governance.
  evidence_skills: AI telemetry, cost tracking, token usage, trace logging, governance
- [CUR-APPTRAIL-AI-SAFETY] Implemented AI safety controls that redact secrets and PII, detect prompt-injection patterns, estimate tokens, enforce user/global/task caps, rate-limit calls, record safety decisions, and support allow, allow-redacted, block, and quarantine outcomes.
  evidence_skills: PII redaction, prompt-injection detection, AI safety, rate limiting, privacy controls
- [CUR-APPTRAIL-CONSENT-CHECKS] Added consent checks for AI processing, third-party enrichment, web research, and source intelligence.
  evidence_skills: consent management, privacy governance, AI processing controls
- [CUR-APPTRAIL-ADMIN-AI] Built admin AI surfaces for promotion reports, telemetry, runs, artifacts, experiments, model cards, trace access logs, and safety-decision review.
  evidence_skills: AI ops, model cards, telemetry UI, experiment tracking, admin dashboards
- [CUR-APPTRAIL-SEARCH-INDEXING] Implemented search indexing as a supported product capability for job-search context and downstream copilot/retrieval workflows.
  evidence_skills: search indexing, retrieval, document indexing, copilot context
- [CUR-APPTRAIL-DASHBOARD-WORKSTATION] Built a React/Vite dashboard with jobs, analytics, conversations, network, calendar, radar, settings, classifier audit, extraction reports, AI ops, source intelligence admin, profile, resume tailor, and copilot surfaces.
  evidence_skills: React, Vite, TypeScript, product dashboard, frontend architecture
- [CUR-APPTRAIL-ANALYTICS-AUDIT] Built analytics and audit surfaces including classifier audits, extraction reports, AI ops, model cards, promotion reports, ATS intelligence, source usage/health, research feedback stats, and dashboard analytics.
  evidence_skills: analytics dashboards, audit UI, AI ops, classifier evaluation, product analytics
- [CUR-APPTRAIL-SECURITY-AUTH] Implemented JWT authentication, refresh tokens as HttpOnly cookies, Redis-backed token blacklist with memory fallback, API-key hashing, and dashboard/API-key authentication paths.
  evidence_skills: JWT authentication, Redis, API key hashing, backend security
- [CUR-APPTRAIL-OBSERVABILITY] Added Prometheus metrics, Sentry integration, Playwright smoke tests, Docker/deploy scripts, and GitHub workflows for operational readiness.
  evidence_skills: Prometheus, Sentry, Playwright, Docker, CI/CD, observability
