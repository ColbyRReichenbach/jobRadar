# AppTrail Project Memory

## Project Structure
- `backend/` - FastAPI app (Python 3.10)
- `dashboardv2/` - React + Vite + Tailwind + motion/react + TanStack Query
- `tests/` - pytest with aiosqlite for test DB
- `IMPLEMENTATION_PLAN.md` - 4-phase build plan (all phases complete)
- `SPRINTS.md` - 20 sprints for next phase of development

## Phase Status
- Phase 1: COMPLETE (all 11 tasks done, 7 tests passing)
- Phase 2: COMPLETE (9 tasks done, 6 new tests, 13 total passing)
- Phase 3: COMPLETE (9 tasks done, 14 new tests, 27 total passing)
- Phase 4: COMPLETE (11 tasks done, 8 new tests + 1 E2E, 35 total passing)
- Phase 5A: COMPLETE (Email Intelligence — 24 new tests, 59 total passing)
- Sprint 1 (Dead UI Fixes): COMPLETE
- Sprint 2 (Company Entity): COMPLETE - 5 new tests
- Sprint 3 (Role Taxonomy): COMPLETE - 8 new tests
- Sprint 4 (Tech Stack Extraction): COMPLETE - 9 new tests
- Total tests after Sprint 1-4: 81 passing in 2.91s
- Sprint 5 (Resume Intelligence): COMPLETE - 10 new tests
- Sprint 6 (Onboarding Flow): COMPLETE - 4 new tests
- Sprint 7 (Dead Application Detection): COMPLETE - 6 new tests
- Sprint 8 (ATS Decode Ring): COMPLETE - 5 new tests
- Total tests after Sprint 5-8: 106 passing in 4.87s

## Key Architecture Decisions
- SQLAlchemy models use Python-level `default=` (not `server_default=text()`) for SQLite test compatibility
- Alembic migration chain: 001→002→003→004→005→006→007→008→009→010→011→012
- Tests use `sqlite+aiosqlite:///:memory:` via conftest.py fixtures
- Company as first-class entity with domain-based upsert from job URLs
- Role taxonomy via keyword/alias matching (no LLM) with RoleUmbrella model
- Tech stack extraction via regex pattern matching from job descriptions
- Relationship naming: `company_ref` on Application/EmailEvent/Contact to avoid conflict with `company` text field
- `_serialize_app()` checks `'umbrella' in app_row.__dict__` to avoid MissingGreenlet lazy load errors

## Sprint 2-4 New Models & Services
- `Company` model: domain (unique), name, logo_url, industry, size, ats_platform
- `RoleUmbrella` model: name (unique), aliases (JSON), typical_skills (JSON), parent_id (self-FK)
- `CompanyTechProfile` model: company_id (FK), tech_name, category, mention_count
- `backend/services/company_service.py` - upsert_company from domain
- `backend/services/role_classifier.py` - classify_role with global cache + clear_cache()
- `backend/services/tech_extractor.py` - extract_tech_stack (~100 technologies)
- `scripts/seed_umbrellas.py` - 54 umbrella categories

## New Endpoints (Sprint 2-8)
- GET /api/companies, GET /api/companies/{domain}, GET /api/companies/{domain}/tech
- GET /api/umbrellas, GET /api/jobs?umbrella_id=
- POST /api/resume/parse, GET /api/profile, GET /api/jobs/{id}/match
- POST /api/profile/preferences, GET /api/profile/preferences (JWT required)
- GET /api/intelligence/ats/{platform}, POST /api/intelligence/ats/compute

## Sprint 5-8 New Models & Services
- `UserProfile` model: skills, education, experience_years, tools, certifications
- `UserRoleInterest` model: user_id + umbrella_id many-to-many
- `AtsBehavior` model: platform + metric_name unique, metric_value, sample_size
- Application: added match_score, listing_alive, listing_last_checked, listing_died_at
- User: added onboarding fields (onboarding_complete, preferred_locations, etc)
- `resume_parser.py` - PDF + Haiku LLM with fallback to tech_extractor
- `match_scorer.py` - score_match() with transferable skills detection
- `check_dead_apps.py` - Celery daily task, polite delays, platform-specific signals
- `ats_intelligence.py` - compute_ats_metrics() + get_platform_profile() with insights

## Auth System
- Dual auth: JWT (dashboard) + API key (extension)
- OAuth flow via Google → callback → JWT in URL hash
- Test header: `{"Authorization": "Bearer test-api-key-for-testing"}`

## Test Configuration
- `tests/conftest.py` - sets env vars, creates in-memory SQLite, provides `client` and `db_session` fixtures
- Role classifier tests need `clear_cache()` autouse fixture
- `_seed_umbrellas()` helper for role tests
