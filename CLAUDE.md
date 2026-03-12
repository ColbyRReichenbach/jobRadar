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
12. Google OAuth working rules:
   - Plain sign-in must NOT send `include_granted_scopes=true`. Only Gmail/Calendar connect flows should use incremental scopes.
   - Preserve Google's original OAuth `state`. If app context is wrapped into `state`, store the original Google `state` inside that wrapper and restore it when rebuilding the callback `Flow`.
   - In the callback, exchange tokens with `flow.fetch_token(authorization_response=...)` using the configured `GOOGLE_REDIRECT_URI` plus the callback query string, not the raw proxied request origin.
   - Set `OAUTHLIB_RELAX_TOKEN_SCOPE=1` so incremental Gmail/Calendar scope widening does not break token exchange.
   - Frontend origin for post-login redirect can be carried in app state, but Gmail/Calendar intent and PKCE data must survive the round-trip exactly or `token_exchange_failed` will occur.
