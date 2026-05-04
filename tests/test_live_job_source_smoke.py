import os

import pytest

from backend.services.job_sources.base import SearchQuery


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_JOB_SOURCE_SMOKE", "false").lower() not in {"1", "true", "yes", "on"},
    reason="Live job-source smoke tests are opt-in.",
)


@pytest.mark.asyncio
async def test_live_greenhouse_smoke():
    from backend.services.job_sources import greenhouse

    config = greenhouse.parse_source_from_url(os.getenv("LIVE_GREENHOUSE_BOARD_URL", "https://boards.greenhouse.io/airbnb"))
    result = await greenhouse.verify_source(config)

    assert result.status in {"verified", "failed"}
    if result.status == "verified":
        jobs = await greenhouse.fetch_jobs(config, SearchQuery(limit=3))
        assert isinstance(jobs, list)


@pytest.mark.asyncio
async def test_live_lever_smoke():
    from backend.services.job_sources import lever

    config = lever.parse_source_from_url(os.getenv("LIVE_LEVER_SITE_URL", "https://jobs.lever.co/netlify"))
    result = await lever.verify_source(config)

    assert result.status in {"verified", "failed"}
    if result.status == "verified":
        jobs = await lever.fetch_jobs(config, SearchQuery(limit=3))
        assert isinstance(jobs, list)


@pytest.mark.asyncio
async def test_live_ashby_smoke():
    from backend.services.job_sources import ashby

    url = os.getenv("LIVE_ASHBY_BOARD_URL")
    if not url:
        pytest.skip("LIVE_ASHBY_BOARD_URL not configured")
    config = ashby.parse_source_from_url(url)
    result = await ashby.verify_source(config)

    assert result.status in {"verified", "failed"}


@pytest.mark.asyncio
async def test_live_workable_smoke():
    from backend.services.job_sources import workable

    url = os.getenv("LIVE_WORKABLE_SOURCE_URL")
    if not url:
        pytest.skip("LIVE_WORKABLE_SOURCE_URL not configured")
    config = workable.parse_source_from_url(url)
    result = await workable.verify_source(config)

    assert result.status in {"verified", "failed"}


@pytest.mark.asyncio
async def test_live_smartrecruiters_smoke():
    from dataclasses import replace
    from backend.services.job_sources import smartrecruiters

    url = os.getenv("LIVE_SMARTRECRUITERS_SOURCE_URL")
    if not url:
        pytest.skip("LIVE_SMARTRECRUITERS_SOURCE_URL not configured")
    config = replace(smartrecruiters.parse_source_from_url(url), access_mode=os.getenv("LIVE_SMARTRECRUITERS_ACCESS_MODE", "public"))
    result = await smartrecruiters.verify_source(config)

    assert result.status in {"verified", "failed", "needs_review"}


@pytest.mark.asyncio
async def test_live_workday_smoke(monkeypatch):
    from backend.services.job_sources import workday

    url = os.getenv("LIVE_WORKDAY_SOURCE_URL")
    if not url or os.getenv("JOB_SEARCH_WORKDAY_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("LIVE_WORKDAY_SOURCE_URL and JOB_SEARCH_WORKDAY_ENABLED=true are required")
    monkeypatch.setenv("JOB_SOURCE_WORKDAY_MIN_INTERVAL_SECONDS", "0")
    config = workday.parse_source_from_url(url)
    result = await workday.verify_source(config)

    assert result.status in {"needs_review", "failed", "blocked"}
