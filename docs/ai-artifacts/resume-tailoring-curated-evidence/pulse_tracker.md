---
project_id: pulse_tracker
title: Pulse Tracker Fitness Platform
project_tags: Next.js, React, TypeScript, Supabase, Upstash Redis, OpenAI, Vercel AI SDK, streaming, Sentry, Zod, Playwright, Vitest, fitness analytics, data privacy, AI guardrails, tool calling
---

- [CUR-PULSE-NEXT-APP] Built a server-first Next.js app with dashboard, workout, analytics, profile, settings, login, onboarding, pulse-transition, admin AI coach, auth callback, and API routes.
  evidence_skills: Next.js, React, TypeScript, app routing, frontend architecture
- [CUR-PULSE-SUPABASE-DATA] Implemented Supabase-backed data access for profiles, logs, sleep logs, readiness logs, PR history, workout library, workout sessions, biometrics, and AI logs.
  evidence_skills: Supabase, data access, user-scoped data, fitness logs
- [CUR-PULSE-ZOD-VALIDATION] Centralized Zod validation for profile, onboarding, logs, biometrics, chat requests, unit conversions, and one-rep-max calculations.
  evidence_skills: Zod, validation, TypeScript, input schemas
- [CUR-PULSE-DETERMINISTIC-CALCS] Built deterministic HR zone, pace zone, one-rep-max, and percentage-based working-weight calculations.
  evidence_skills: deterministic calculations, fitness analytics, HR zones, one-rep-max
- [CUR-PULSE-AI-CHAT-ROUTE] Built a guarded streaming AI chat route that validates/sanitizes messages, enforces rate limits, detects prompt injection, applies sensitive-topic guardrails, calls OpenAI moderation, classifies semantic fitness scope, builds context, enables tools conditionally, streams responses, validates output, logs cost/tokens, and records AI interactions.
  evidence_skills: OpenAI, streaming AI, prompt-injection detection, moderation, rate limiting
- [CUR-PULSE-SENSITIVE-GUARDRAILS] Added guardrails for prompt extraction, credentials, database schema extraction, other users' PII, mental-health crisis, eating-disorder indicators, dangerous exercise, extreme weight cutting, PEDs, medical diagnosis, nutrition, explicit content, illegal activity, and off-topic requests.
  evidence_skills: AI guardrails, privacy controls, safety policy, sensitive-topic detection
- [CUR-PULSE-TOOL-LAYER] Defined user-scoped tools for recent logs, biometrics, last log lookup, exercise PRs, recovery metrics, cardio summary, compliance report, and trend analysis.
  evidence_skills: tool calling, user-scoped tools, fitness analytics, trend analysis
- [CUR-PULSE-PRIVACY-MODE] Disabled AI tools when the user profile is set to private and instructed the assistant not to hallucinate unavailable user data.
  evidence_skills: privacy mode, AI tool gating, hallucination prevention, user consent
- [CUR-PULSE-CONTEXT-ROUTER] Built an AI context router that classifies intent into injury, progress, logistics, or general, supports follow-up carryover, and builds dynamic context with token budgeting.
  evidence_skills: intent classification, context routing, token budgeting, AI orchestration
- [CUR-PULSE-ANALYTICS] Built phase-specific analytics from actual logs, including Foundation, Intensity, Peak Power, Taper, and Mastery phases.
  evidence_skills: fitness analytics, user logs, phase analysis, dashboard metrics
- [CUR-PULSE-DATA-EXPORT] Implemented authenticated user-data export for logs, workout sessions, biometrics, and PR history.
  evidence_skills: data export, authentication, user data privacy
- [CUR-PULSE-SECURITY] Added password checks, auth rate limiting, chat rate limiting, CSP headers, protected-route redirects, health-check secret, output filtering, and Sentry alerting for high-severity AI output issues.
  evidence_skills: security controls, rate limiting, CSP, Sentry, protected routes
- [CUR-PULSE-TESTS] Added unit, security, integration, and e2e tests covering AI security, auth, validation, middleware, guardrails, IP handling, utilities, database mocks, API behavior, AI coach components, login, workout, and chat flows.
  evidence_skills: Vitest, Playwright, security testing, integration testing, e2e testing
