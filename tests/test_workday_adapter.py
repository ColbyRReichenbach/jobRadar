from dataclasses import replace

import httpx
import pytest

from backend.services.job_sources.base import SearchQuery


@pytest.fixture(autouse=True)
def fast_workday_rate_limits(monkeypatch):
    monkeypatch.setenv("JOB_SOURCE_WORKDAY_MIN_INTERVAL_SECONDS", "0")


class FakeResponse:
    def __init__(self, payload, status_code: int = 200, method: str = "POST", url: str = "https://company.wd5.myworkdayjobs.com/wday/cxs/company/site/jobs"):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request(method, url)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request)
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=self.request, response=response)


def test_workday_parser_extracts_tenant_server_locale_and_site():
    from backend.services.job_sources import workday

    config = workday.parse_source_from_url("https://company.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123")

    assert config.provider_key == "company:site"
    assert config.access_mode == "unknown"
    assert config.verification_status == "needs_review"
    assert config.terms_risk == "medium"
    assert config.source_config["tenant"] == "company"
    assert config.source_config["server"] == "wd5"
    assert config.source_config["locale"] == "en-US"
    assert config.public_jobs_endpoint == "https://company.wd5.myworkdayjobs.com/wday/cxs/company/site/jobs"


def test_workday_alternate_host_parser_extracts_recruiting_site():
    from backend.services.job_sources import workday

    config = workday.parse_source_from_url("https://jobs.myworkdaysite.com/recruiting/acme/Public/job/US/Engineer_JR123")

    assert config.provider_key == "acme:Public"
    assert config.source_config["host"] == "jobs.myworkdaysite.com"
    assert config.public_jobs_endpoint == "https://jobs.myworkdaysite.com/wday/cxs/acme/Public/jobs"


def test_workday_candidate_home_classification_is_private():
    from backend.services.source_intelligence.url_classifier import classify_url

    classified = classify_url("https://company.wd5.myworkdayjobs.com/site/candidate-home")

    assert classified.provider_type == "workday"
    assert classified.link_type == "candidate_home"
    assert classified.safe_to_share is False
    assert classified.contains_private_token is True


@pytest.mark.asyncio
async def test_workday_verification_is_admin_gated_after_technical_success(monkeypatch):
    from backend.services.job_sources import workday

    async def fake_fetch(url, **kwargs):
        assert url == "https://company.wd5.myworkdayjobs.com/wday/cxs/company/site/jobs"
        assert kwargs["method"] == "POST"
        assert kwargs["json_body"] == {"limit": 1, "offset": 0, "searchText": "", "appliedFacets": {}}
        return FakeResponse({"total": 2, "jobPostings": [{"title": "Engineer"}]})

    monkeypatch.setenv("JOB_SEARCH_WORKDAY_ENABLED", "true")
    monkeypatch.setattr(workday, "fetch_public_https", fake_fetch)
    config = workday.parse_source_from_url("https://company.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123")

    result = await workday.verify_source(config)

    assert result.status == "needs_review"
    assert result.job_count == 2
    assert result.error_type == "admin_review_required"
    assert result.terms_risk == "medium"


@pytest.mark.asyncio
async def test_workday_fetch_jobs_requires_admin_approved_access(monkeypatch):
    from backend.services.job_sources import workday

    async def fake_fetch(url, **kwargs):
        return FakeResponse({
            "total": 1,
            "jobPostings": [
                {
                    "title": "Data Analyst",
                    "jobReqId": "JR123",
                    "externalPath": "job/Charlotte/Data-Analyst_JR123",
                    "locationsText": "Charlotte, NC",
                    "timeType": "Full time",
                    "jobDescription": "<p>Analyze data</p>",
                }
            ],
        })

    monkeypatch.setenv("JOB_SEARCH_WORKDAY_ENABLED", "true")
    monkeypatch.setattr(workday, "fetch_public_https", fake_fetch)
    parsed = workday.parse_source_from_url("https://company.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123")

    assert await workday.fetch_jobs(parsed, SearchQuery(query="analyst")) == []

    approved = replace(parsed, access_mode="public", verification_status="verified")
    jobs = await workday.fetch_jobs(approved, SearchQuery(query="analyst"))

    assert jobs[0].external_job_id == "JR123"
    assert jobs[0].canonical_url == "https://company.wd5.myworkdayjobs.com/en-US/site/job/Charlotte/Data-Analyst_JR123"
    assert jobs[0].source_type == "workday"


@pytest.mark.asyncio
async def test_workday_verification_records_429_and_timeout(monkeypatch):
    from backend.services.job_sources import workday

    async def rate_limited_fetch(url, **kwargs):
        return FakeResponse({}, status_code=429)

    async def timeout_fetch(url, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setenv("JOB_SEARCH_WORKDAY_ENABLED", "true")
    config = workday.parse_source_from_url("https://company.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123")

    monkeypatch.setattr(workday, "fetch_public_https", rate_limited_fetch)
    rate_result = await workday.verify_source(config)

    monkeypatch.setattr(workday, "fetch_public_https", timeout_fetch)
    timeout_result = await workday.verify_source(config)

    assert rate_result.status == "failed"
    assert rate_result.error_type == "rate_limited"
    assert rate_result.http_status == 429
    assert timeout_result.status == "failed"
    assert timeout_result.error_type == "TimeoutError"


@pytest.mark.asyncio
async def test_workday_tenant_rate_limit_blocks_hot_retries(monkeypatch):
    from backend.services.job_sources import workday

    calls = {"count": 0}

    async def fake_fetch(url, **kwargs):
        calls["count"] += 1
        return FakeResponse({"total": 1, "jobPostings": [{"title": "Engineer"}]})

    monkeypatch.setenv("JOB_SEARCH_WORKDAY_ENABLED", "true")
    monkeypatch.setenv("JOB_SOURCE_WORKDAY_TENANT_RPM", "1")
    monkeypatch.setattr(workday, "fetch_public_https", fake_fetch)
    config = workday.parse_source_from_url("https://ratelimit.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123")

    first = await workday.verify_source(config)
    second = await workday.verify_source(config)

    assert first.status == "needs_review"
    assert second.status == "failed"
    assert second.error_type == "rate_limited"
    assert calls["count"] == 1
