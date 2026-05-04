from __future__ import annotations

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult, parse_datetime, text_or_none
from backend.services.source_intelligence.url_classifier import classify_url
from backend.services.url_safety import fetch_public_https


PROVIDER = "ashby"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if classified.provider_type != PROVIDER or not classified.provider_key:
        return None
    board = classified.provider_key
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=board,
        access_mode="public",
        company_name=board,
        career_url=f"https://jobs.ashbyhq.com/{board}",
        public_jobs_endpoint=f"https://api.ashbyhq.com/posting-api/job-board/{board}",
        source_config={"board": board},
        verification_status="pending",
        terms_risk="low",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    try:
        response = await fetch_public_https(config.public_jobs_endpoint or _endpoint(config), timeout=10)
        status = response.status_code
        response.raise_for_status()
        jobs = _jobs_from_payload(response.json())
        return VerificationResult(status="verified", access_mode="public", job_count=len(jobs), http_status=status, terms_risk="low")
    except Exception as exc:
        return VerificationResult(status="failed", access_mode="public", error_type=type(exc).__name__, error_message_redacted=str(exc)[:240], terms_risk="low")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    response = await fetch_public_https(config.public_jobs_endpoint or _endpoint(config), timeout=10)
    response.raise_for_status()
    return [_normalize_job(item, config) for item in _jobs_from_payload(response.json())[: query.limit]]


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    jobs = await fetch_jobs(config, SearchQuery(limit=500))
    key = external_id_or_path.strip("/").split("/")[-1]
    return next((job for job in jobs if job.external_job_id == key or job.canonical_url.rstrip("/").endswith(key)), None)


def _endpoint(config: SourceConfig) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{config.provider_key}"


def _jobs_from_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        jobs = payload.get("jobs") or payload.get("postings") or []
        return jobs if isinstance(jobs, list) else []
    return payload if isinstance(payload, list) else []


def _normalize_job(item: dict, config: SourceConfig) -> NormalizedJobPosting:
    location = item.get("location")
    if isinstance(location, dict):
        location_text = location.get("location") or location.get("name")
    else:
        location_text = location
    compensation = item.get("compensation") or {}
    return NormalizedJobPosting(
        external_job_id=text_or_none(item.get("id") or item.get("jobId")),
        title=text_or_none(item.get("title")) or "Untitled role",
        company_name=config.company_name or config.provider_key,
        company_domain=config.company_domain,
        description_text=text_or_none(item.get("descriptionHtml") or item.get("descriptionPlain") or item.get("description")),
        location_text=text_or_none(location_text),
        remote_status=text_or_none(item.get("remote")),
        employment_type=text_or_none(item.get("employmentType")),
        department=text_or_none(item.get("department")),
        salary_min=compensation.get("min") if isinstance(compensation, dict) else None,
        salary_max=compensation.get("max") if isinstance(compensation, dict) else None,
        salary_currency=compensation.get("currency") if isinstance(compensation, dict) else None,
        salary_period=compensation.get("interval") if isinstance(compensation, dict) else None,
        date_posted=parse_datetime(item.get("publishedAt")),
        valid_through=None,
        canonical_url=text_or_none(item.get("jobUrl") or item.get("applyUrl")) or f"https://jobs.ashbyhq.com/{config.provider_key}/{item.get('id')}",
        source_type=PROVIDER,
        source_confidence=0.95,
        redacted_metadata={"provider_key": config.provider_key},
    )
