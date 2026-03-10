# CLAUDE.md
1. Run pytest before marking any backend task complete. Fix failures before stopping.
2. Never use rm -rf without explicit confirmation. The pre-tool hook blocks it.
3. All credentials come from environment variables. Never hardcode secrets.
4. Update IMPLEMENTATION_PLAN.md task status as each task completes.
5. Use async/await throughout FastAPI. No synchronous blocking calls.
6. All Supabase schema changes require an Alembic migration. Never ALTER TABLE directly.
7. Import with_retry() from backend/utils/retry.py for every external API call.
8. All Playwright scrapers use randomized 2-4s delay and realistic User-Agent.
9. Read docs/PRD.md Section 12 before writing any service that calls an external API.
10. If a test fails 5+ times with the same approach, try a fundamentally different implementation.
11. Use uptash-redis package with UPTASH_REDIS_REST_URL and UPTASH_REDIS_REST_TOKEN env vars.2