from datetime import date

import pytest
from sqlalchemy import select

from tests.conftest import TEST_USER_ID
from tests.conftest import AUTH_HEADER


def _posting(title="Data Scientist"):
    from backend.services.job_sources.base import NormalizedJobPosting

    return NormalizedJobPosting(
        external_job_id="123",
        title=title,
        company_name="Acme",
        company_domain="acme.com",
        description_text="Build models",
        location_text="Remote",
        remote_status="remote",
        employment_type="Full-time",
        department="Data",
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        date_posted=None,
        valid_through=None,
        canonical_url="https://boards.greenhouse.io/acme/jobs/123",
        source_type="greenhouse",
        source_confidence=0.95,
        redacted_metadata={},
    )


@pytest.mark.asyncio
async def test_resolver_prefers_verified_direct_source(monkeypatch, db_session):
    from backend.models import CompanyJobSource, JobPosting
    from backend.services.job_sources import greenhouse
    from backend.services.job_sources.resolver import resolve_job_search

    db_session.add(CompanyJobSource(
        company_name="Acme",
        company_domain="acme.com",
        provider_type="greenhouse",
        provider_key="acme",
        access_mode="public",
        public_jobs_endpoint="https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
        verification_status="verified",
        discovered_from="unit_test",
    ))
    await db_session.commit()

    async def fake_fetch_jobs(config, query):
        return [_posting()]

    async def fake_broad(query, location):
        raise AssertionError("broad provider should not be used")

    monkeypatch.setattr(greenhouse, "fetch_jobs", fake_fetch_jobs)
    result = await resolve_job_search(db_session, user_id=TEST_USER_ID, query="Acme data", location="Remote", broad_search=fake_broad)
    await db_session.commit()

    assert result.provider_status["mode"] == "direct_source"
    assert result.source_summary.broad_provider_used is False
    assert result.results[0]["source"] == "greenhouse"
    posting = (await db_session.execute(select(JobPosting))).scalar_one()
    assert posting.dedupe_key == "greenhouse:acme:123"


@pytest.mark.asyncio
async def test_resolver_skips_unknown_blocked_and_credentialed_sources(monkeypatch, db_session):
    from backend.models import CompanyJobSource
    from backend.services.job_sources.resolver import resolve_job_search

    db_session.add_all([
        CompanyJobSource(company_name="Acme", provider_type="greenhouse", provider_key="acme", access_mode="unknown", verification_status="verified", discovered_from="unit"),
        CompanyJobSource(company_name="Acme", provider_type="icims", provider_key="jobs", access_mode="credentialed", verification_status="verified", discovered_from="unit"),
        CompanyJobSource(company_name="Acme", provider_type="greenhouse", provider_key="blocked", access_mode="blocked", verification_status="blocked", discovered_from="unit"),
    ])
    await db_session.commit()

    async def fake_broad(query, location):
        return [{"title": "Fallback", "company": "Acme", "url": "https://example.com", "source": "serpapi"}]

    result = await resolve_job_search(db_session, user_id=TEST_USER_ID, query="Acme", location="", broad_search=fake_broad)

    assert result.provider_status["mode"] == "broad_only"
    assert result.source_summary.blocked_source_count == 1
    assert result.source_summary.broad_provider_used is True


@pytest.mark.asyncio
async def test_stale_direct_source_falls_back_to_broad(db_session):
    from backend.models import CompanyJobSource
    from backend.services.job_sources.resolver import resolve_job_search

    db_session.add(CompanyJobSource(
        company_name="Acme",
        provider_type="greenhouse",
        provider_key="acme",
        access_mode="public",
        verification_status="stale",
        discovered_from="unit",
    ))
    await db_session.commit()

    async def fake_broad(query, location):
        return [{"title": "Fallback", "company": "Acme", "url": "https://example.com", "source": "serpapi"}]

    result = await resolve_job_search(db_session, user_id=TEST_USER_ID, query="Acme", location="", broad_search=fake_broad)

    assert result.provider_status["mode"] == "broad_only"
    assert result.source_summary.stale_source_count == 1


@pytest.mark.asyncio
async def test_broad_provider_cap_returns_provider_limited(monkeypatch, db_session):
    from backend.models import JobSearchProviderUsage
    from backend.services.job_sources.resolver import resolve_job_search

    monkeypatch.setenv("JOB_SEARCH_SERPAPI_MONTHLY_CAP", "0")
    db_session.add(JobSearchProviderUsage(
        user_key="global",
        provider="serpapi",
        request_mode="fallback",
        query_hash="already-at-cap",
        month_bucket=date.today().replace(day=1),
    ))
    await db_session.commit()

    async def fake_broad(query, location):
        raise AssertionError("broad provider should not be called after cap")

    result = await resolve_job_search(db_session, user_id=TEST_USER_ID, query="Acme", location="", broad_search=fake_broad)

    assert result.provider_status["mode"] == "provider_limited"
    assert result.provider_status["degraded"] is True


@pytest.mark.asyncio
async def test_broad_provider_user_cap_returns_provider_limited(monkeypatch, db_session):
    from backend.models import JobSearchProviderUsage
    from backend.services.job_sources.resolver import resolve_job_search

    monkeypatch.setenv("JOB_SEARCH_SERPAPI_MONTHLY_CAP", "100")
    monkeypatch.setenv("JOB_SEARCH_SERPAPI_USER_MONTHLY_CAP", "0")
    db_session.add(JobSearchProviderUsage(
        user_id=TEST_USER_ID,
        user_key=str(TEST_USER_ID),
        provider="serpapi",
        request_mode="fallback",
        query_hash="already-at-user-cap",
        month_bucket=date.today().replace(day=1),
    ))
    await db_session.commit()

    async def fake_broad(query, location):
        raise AssertionError("broad provider should not be called after user cap")

    result = await resolve_job_search(db_session, user_id=TEST_USER_ID, query="Acme", location="", broad_search=fake_broad)

    assert result.provider_status["mode"] == "provider_limited"
    assert "user monthly cap" in result.provider_status["degraded_reasons"][0].lower()


@pytest.mark.asyncio
async def test_broad_provider_usage_hashes_query(db_session):
    from backend.models import JobSearchProviderUsage
    from backend.services.job_sources.resolver import record_broad_provider_usage

    await record_broad_provider_usage(
        db_session,
        user_id=TEST_USER_ID,
        provider="serpapi",
        query="secret analyst search",
        location="Charlotte",
        request_mode="fallback",
        result_count=2,
    )
    await db_session.commit()

    rows = (await db_session.execute(select(JobSearchProviderUsage))).scalars().all()
    assert len(rows) == 2
    assert all("secret analyst search" not in row.query_hash for row in rows)
    assert {row.user_key for row in rows} == {"global", str(TEST_USER_ID)}


@pytest.mark.asyncio
async def test_broad_results_enqueue_direct_source_candidates(db_session):
    from backend.models import CompanyJobSource
    from backend.services.job_sources.resolver import resolve_job_search

    async def fake_broad(query, location):
        return [
            {
                "title": "Analyst",
                "company": "Acme",
                "url": "https://boards.greenhouse.io/acme/jobs/123",
                "source": "serpapi",
            }
        ]

    result = await resolve_job_search(db_session, user_id=TEST_USER_ID, query="Acme", location="", broad_search=fake_broad)
    sources = (await db_session.execute(select(CompanyJobSource))).scalars().all()

    assert result.provider_status["mode"] == "broad_only"
    assert sources[0].provider_type == "greenhouse"
    assert sources[0].provider_key == "acme"
    assert sources[0].discovered_from == "broad_search"


@pytest.mark.asyncio
async def test_search_api_returns_source_summary_for_direct_source(monkeypatch, client, db_session):
    from backend.models import CompanyJobSource
    from backend.services.job_sources import greenhouse

    monkeypatch.setenv("JOB_SEARCH_DIRECT_SOURCES_ENABLED", "true")
    db_session.add(CompanyJobSource(
        company_name="Acme",
        company_domain="acme.com",
        provider_type="greenhouse",
        provider_key="acme",
        access_mode="public",
        verification_status="verified",
        discovered_from="unit_test",
    ))
    await db_session.commit()

    async def fake_fetch_jobs(config, query):
        return [_posting()]

    monkeypatch.setattr(greenhouse, "fetch_jobs", fake_fetch_jobs)

    response = await client.get("/api/search?q=Acme data&location=Remote", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data["cached"] is False
    assert data["provider_status"]["mode"] == "direct_source"
    assert data["source_summary"]["verified_source_count"] == 1
    assert data["results"][0]["source"] == "greenhouse"
