import pytest

from backend.services.job_sources.base import SearchQuery, SourceConfig


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_greenhouse_adapter_verifies_and_normalizes(monkeypatch):
    from backend.services.job_sources import greenhouse

    async def fake_fetch(url, **kwargs):
        assert "boards-api.greenhouse.io/v1/boards/acme/jobs" in url
        return FakeResponse({
            "jobs": [
                {
                    "id": 123,
                    "title": "Data Scientist",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                    "location": {"name": "Remote"},
                    "departments": [{"name": "Data"}],
                    "content": "<p>Build models</p>",
                }
            ]
        })

    monkeypatch.setattr(greenhouse, "fetch_public_https", fake_fetch)
    config = greenhouse.parse_source_from_url("https://boards.greenhouse.io/acme/jobs/123")

    assert config.provider_key == "acme"
    verification = await greenhouse.verify_source(config)
    jobs = await greenhouse.fetch_jobs(config, SearchQuery(query="data"))

    assert verification.status == "verified"
    assert jobs[0].title == "Data Scientist"
    assert jobs[0].source_type == "greenhouse"


@pytest.mark.asyncio
async def test_lever_adapter_verifies_and_normalizes(monkeypatch):
    from backend.services.job_sources import lever

    async def fake_fetch(url, **kwargs):
        assert "api.lever.co/v0/postings/acme" in url
        return FakeResponse([
            {
                "id": "post-1",
                "text": "Backend Engineer",
                "hostedUrl": "https://jobs.lever.co/acme/post-1",
                "descriptionPlain": "Build APIs",
                "categories": {"location": "New York", "team": "Engineering", "commitment": "Full-time"},
            }
        ])

    monkeypatch.setattr(lever, "fetch_public_https", fake_fetch)
    config = lever.parse_source_from_url("https://jobs.lever.co/acme/post-1")

    verification = await lever.verify_source(config)
    jobs = await lever.fetch_jobs(config, SearchQuery(query="engineer"))

    assert verification.job_count == 1
    assert jobs[0].employment_type == "Full-time"
    assert jobs[0].department == "Engineering"


@pytest.mark.asyncio
async def test_ashby_adapter_verifies_and_normalizes(monkeypatch):
    from backend.services.job_sources import ashby

    async def fake_fetch(url, **kwargs):
        assert "api.ashbyhq.com/posting-api/job-board/acme" in url
        return FakeResponse({
            "jobs": [
                {
                    "id": "job-1",
                    "title": "Product Analyst",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/job-1",
                    "location": {"name": "Remote"},
                    "department": "Product",
                }
            ]
        })

    monkeypatch.setattr(ashby, "fetch_public_https", fake_fetch)
    config = ashby.parse_source_from_url("https://jobs.ashbyhq.com/acme/job-1")

    verification = await ashby.verify_source(config)
    jobs = await ashby.fetch_jobs(config, SearchQuery(query="analyst"))

    assert verification.status == "verified"
    assert jobs[0].location_text == "Remote"


@pytest.mark.asyncio
async def test_workable_adapter_verifies_and_normalizes(monkeypatch):
    from backend.services.job_sources import workable

    async def fake_fetch(url, **kwargs):
        assert "www.workable.com/api/accounts/acme?details=true" in url
        return FakeResponse({
            "jobs": [
                {
                    "shortcode": "ABC123",
                    "title": "ML Engineer",
                    "url": "https://apply.workable.com/acme/j/ABC123",
                    "location": {"city": "Charlotte", "region": "NC", "country": "US"},
                    "department": "AI",
                    "workplace_type": "hybrid",
                }
            ]
        })

    monkeypatch.setattr(workable, "fetch_public_https", fake_fetch)
    config = workable.parse_source_from_url("https://apply.workable.com/acme/j/ABC123")

    verification = await workable.verify_source(config)
    jobs = await workable.fetch_jobs(config, SearchQuery(query="ml"))

    assert verification.job_count == 1
    assert jobs[0].remote_status == "hybrid"
    assert jobs[0].location_text == "Charlotte, NC, US"


def test_access_mode_provider_parsers_are_conservative():
    from backend.services.job_sources import icims, smartrecruiters, workday

    smart = smartrecruiters.parse_source_from_url("https://careers.smartrecruiters.com/acme")
    icims_config = icims.parse_source_from_url("https://jobs.icims.com/jobs/123/engineer")
    wd = workday.parse_source_from_url("https://company.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123")

    assert smart.access_mode == "unknown"
    assert smart.verification_status == "needs_review"
    assert icims_config.access_mode == "credentialed"
    assert wd.access_mode == "unknown"
    assert wd.terms_risk == "medium"


@pytest.mark.asyncio
async def test_smartrecruiters_unknown_access_is_not_fetched(monkeypatch):
    from backend.services.job_sources import smartrecruiters

    async def fake_fetch(url, **kwargs):
        raise AssertionError("unknown SmartRecruiters access must not fetch")

    monkeypatch.setattr(smartrecruiters, "fetch_public_https", fake_fetch)
    config = smartrecruiters.parse_source_from_url("https://careers.smartrecruiters.com/acme")

    result = await smartrecruiters.verify_source(config)
    jobs = await smartrecruiters.fetch_jobs(config, SearchQuery())

    assert result.status == "needs_review"
    assert jobs == []


@pytest.mark.asyncio
async def test_provider_verify_records_timeout_and_429(monkeypatch):
    from backend.services.job_sources import greenhouse, lever

    async def timeout_fetch(url, **kwargs):
        raise TimeoutError("timed out")

    async def rate_limited_fetch(url, **kwargs):
        return FakeResponse({"jobs": []}, status_code=429)

    monkeypatch.setattr(greenhouse, "fetch_public_https", timeout_fetch)
    timeout_result = await greenhouse.verify_source(greenhouse.parse_source_from_url("https://boards.greenhouse.io/acme"))

    monkeypatch.setattr(lever, "fetch_public_https", rate_limited_fetch)
    rate_result = await lever.verify_source(lever.parse_source_from_url("https://jobs.lever.co/acme"))

    assert timeout_result.status == "failed"
    assert timeout_result.error_type == "TimeoutError"
    assert rate_result.status == "failed"
    assert rate_result.error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_source_registry_upserts_are_idempotent(db_session):
    from backend.services.job_sources.base import NormalizedJobPosting
    from backend.services.job_sources.registry import upsert_company_job_source, upsert_job_posting
    from backend.services.job_sources import greenhouse

    config = greenhouse.parse_source_from_url("https://boards.greenhouse.io/acme/jobs/123")
    source_a = await upsert_company_job_source(db_session, config, discovered_from="unit_test")
    source_b = await upsert_company_job_source(db_session, config, discovered_from="unit_test")

    posting = NormalizedJobPosting(
        external_job_id="123",
        title="Data Scientist",
        company_name="Acme",
        company_domain="acme.com",
        description_text="Build models",
        location_text="Remote",
        remote_status=None,
        employment_type=None,
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
    job_a = await upsert_job_posting(db_session, source=source_a, posting=posting)
    job_b = await upsert_job_posting(db_session, source=source_b, posting=posting)
    await db_session.commit()

    assert source_a.id == source_b.id
    assert job_a.id == job_b.id
    assert job_a.dedupe_key == "greenhouse:acme:123"
    assert "api_key" not in str(source_a.source_config).lower()
