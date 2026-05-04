import json

import pytest


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_structured_data_adapter_extracts_single_visible_job(monkeypatch):
    from backend.services.job_sources import structured_data

    job = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Data Scientist",
        "description": "<p>Build models</p>",
        "hiringOrganization": {"name": "Acme"},
        "jobLocation": {"address": {"addressLocality": "Charlotte", "addressRegion": "NC", "addressCountry": "US"}},
        "datePosted": "2026-05-01T00:00:00Z",
        "employmentType": "FULL_TIME",
    }
    html = f"<html><body><h1>Data Scientist</h1><script type='application/ld+json'>{json.dumps(job)}</script></body></html>"

    async def fake_fetch(url, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse("User-agent: *\nAllow: /")
        return FakeResponse(html)

    monkeypatch.setenv("JOB_SEARCH_CUSTOM_CRAWL_ENABLED", "true")
    monkeypatch.setattr(structured_data, "fetch_public_https", fake_fetch)

    config = structured_data.parse_source_from_url("https://careers.acme.com/jobs/data-scientist")
    verification = await structured_data.verify_source(config)
    postings = await structured_data.fetch_jobs(config, structured_data.SearchQuery())

    assert verification.status == "verified"
    assert postings[0].title == "Data Scientist"
    assert postings[0].location_text == "Charlotte, NC, US"


@pytest.mark.asyncio
async def test_structured_data_adapter_rejects_listing_pages(monkeypatch):
    from backend.services.job_sources import structured_data

    html = "<html><body><h1>Jobs</h1><script type='application/ld+json'>" + json.dumps([
        {"@type": "JobPosting", "title": "Data Scientist", "hiringOrganization": {"name": "Acme"}},
        {"@type": "JobPosting", "title": "Engineer", "hiringOrganization": {"name": "Acme"}},
    ]) + "</script></body></html>"

    async def fake_fetch(url, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse("User-agent: *\nAllow: /")
        return FakeResponse(html)

    monkeypatch.setenv("JOB_SEARCH_CUSTOM_CRAWL_ENABLED", "true")
    monkeypatch.setattr(structured_data, "fetch_public_https", fake_fetch)

    config = structured_data.parse_source_from_url("https://careers.acme.com/jobs")

    assert await structured_data.fetch_job_detail(config, config.career_url) is None


@pytest.mark.asyncio
async def test_structured_data_adapter_rejects_hidden_only_title(monkeypatch):
    from backend.services.job_sources import structured_data

    job = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Invisible Engineer",
        "hiringOrganization": {"name": "Acme"},
    }
    html = f"<html><body><h1>Open roles</h1><script type='application/ld+json'>{json.dumps(job)}</script></body></html>"

    async def fake_fetch(url, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse("User-agent: *\nAllow: /")
        return FakeResponse(html)

    monkeypatch.setenv("JOB_SEARCH_CUSTOM_CRAWL_ENABLED", "true")
    monkeypatch.setattr(structured_data, "fetch_public_https", fake_fetch)

    config = structured_data.parse_source_from_url("https://careers.acme.com/jobs/invisible-engineer")

    assert await structured_data.fetch_job_detail(config, config.career_url) is None


@pytest.mark.asyncio
async def test_structured_data_adapter_obeys_robots(monkeypatch):
    from backend.services.job_sources import structured_data

    async def fake_fetch(url, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse("User-agent: *\nDisallow: /jobs")
        raise AssertionError("job page must not be fetched when robots disallows it")

    monkeypatch.setenv("JOB_SEARCH_CUSTOM_CRAWL_ENABLED", "true")
    monkeypatch.setattr(structured_data, "fetch_public_https", fake_fetch)

    config = structured_data.parse_source_from_url("https://careers.acme.com/jobs/data-scientist")
    verification = await structured_data.verify_source(config)

    assert verification.status == "blocked"
    assert verification.error_type == "robots_disallowed"


@pytest.mark.asyncio
async def test_structured_data_adapter_obeys_disabled_flag(monkeypatch):
    from backend.services.job_sources import structured_data

    monkeypatch.setenv("JOB_SEARCH_CUSTOM_CRAWL_ENABLED", "false")
    config = structured_data.parse_source_from_url("https://careers.acme.com/jobs/data-scientist")

    verification = await structured_data.verify_source(config)

    assert verification.status == "blocked"
    assert verification.error_type == "custom_crawl_disabled"
