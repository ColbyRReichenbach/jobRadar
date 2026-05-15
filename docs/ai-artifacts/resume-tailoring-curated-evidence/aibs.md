---
project_id: aibs_abs_observatory
title: AiBS ABS Observatory
project_tags: Next.js, React, TypeScript, PostgreSQL, SQL views, Python ETL, baseball analytics, data warehousing, live polling, OpenAI, AI policy, governance, rate limiting, audit logs, product analytics, data visualization
---

- [CUR-AIBS-WAREHOUSE] Built a PostgreSQL warehouse with 57 tables across core baseball, product, community, editorial, AI, ops, raw, and modeling schemas.
  evidence_skills: PostgreSQL, SQL, data warehousing, schema design
- [CUR-AIBS-MARTS] Built 42 SQL mart views for challenge classification, pitch challenges, ABS event enrichment, overturn probability, team/umpire summaries, timelines, run/win expectancy, challenge values, impact metrics, pitch-type/zone baselines, decision value, and editorial summaries.
  evidence_skills: SQL views, analytics marts, baseball analytics, data modeling
- [CUR-AIBS-ETL-INGEST] Built Python ETL scripts for MLB ABS schedule/feed ingestion, source snapshots, upserts, play/pitch/challenge extraction, summary refresh, and optional report generation.
  evidence_skills: Python ETL, data ingestion, upserts, feed processing
- [CUR-AIBS-LIVE-POLLING] Implemented polling and backfill scripts for live games, historical games, Savant gamefeed data, called-pitch decisions, historical pitch states, game reports, and warehouse status.
  evidence_skills: live polling, backfills, data ingestion, Python automation
- [CUR-AIBS-DATA-ACCESS] Built a large server-side data module that queries live games, scoreboards, challenges, timelines, team/umpire summaries, decision reports, leaderboards, schedules, heatmaps, pitch breakdowns, and model/report data.
  evidence_skills: server-side data access, SQL queries, analytics APIs, data retrieval
- [CUR-AIBS-DECISION-VALUE] Modeled challenge value and decision quality through run expectancy, win expectancy, count-state baselines, modeled decision rows, recommendation rates, and team decision-value summaries.
  evidence_skills: decision modeling, run expectancy, win expectancy, baseball analytics
- [CUR-AIBS-ANALYTIC-SURFACES] Built analytic surfaces for team challenge value matrices, umpire consequence boards, game timelines, pitch-type breakdowns, opportunity boards, pregame history, postgame audit copy, heatmaps, scatter plots, and leaderboards.
  evidence_skills: data visualization, analytics dashboards, React, Recharts
- [CUR-AIBS-AI-POLICY] Implemented AI policy checks for message length, token limits, response length, tool payload bytes, allowed tools by context, prompt misuse detection, tool-payload sanitation, post-processing, cost estimation, and async queue decisions.
  evidence_skills: AI policy, prompt safety, token budgeting, tool governance, cost controls
- [CUR-AIBS-AI-CHAT] Built an OpenAI-backed chat path that persists conversations, messages, and tool calls, enforces per-user/global rate limits, limits concurrency, checks ownership, writes safety events, applies strikes/suspensions/bans, logs costs, and supports cached tool results.
  evidence_skills: OpenAI, AI chat, rate limiting, audit logs, cost tracking
- [CUR-AIBS-BOUNDED-TOOLS] Restricted AI tools by context such as game, team, umpire, or global scope, and sanitized tool results before feeding them back into AI answers.
  evidence_skills: tool calling, AI governance, scope control, tool-output sanitation
- [CUR-AIBS-GOVERNANCE] Implemented Clerk webhook, CSRF, profile/onboarding, API auth, entitlements, usage ledger, audit logs, rate-limit events, safety events, and AI strike/suspension/ban fields.
  evidence_skills: authentication, authorization, audit logs, governance, rate limiting
- [CUR-AIBS-FRONTEND] Built Next.js pages and components for home, games, teams, umpires, articles, profiles, admin, query visualizer, reports, analytics charts, challenge explorers, editorial/community features, and AI visualizer UI.
  evidence_skills: Next.js, React, TypeScript, frontend architecture, analytics UI
- [CUR-AIBS-OPS-SCRIPTS] Added scripts for repo verification, lint/test, AI evals/health, Playwright e2e/load/visual checks, launch QA, schema setup, backups/restores, migration verification, sample data, reconciliation, historical sync, and polling tests.
  evidence_skills: Playwright, QA automation, operational scripts, migration verification, backups
