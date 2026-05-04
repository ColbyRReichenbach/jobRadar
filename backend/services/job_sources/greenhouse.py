from __future__ import annotations

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult, text_or_none
from backend.services.source_intelligence.url_classifier import classify_url
from backend.services.url_safety import fetch_public_https


PROVIDER = "greenhouse"


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
        career_url=f"https://boards.greenhouse.io/{board}",
        public_jobs_endpoint=f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true",
        source_config={"board_token": board},
        verification_status="pending",
        terms_risk="low",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    try:
        response = await fetch_public_https(_jobs_endpoint(config, content=False), timeout=10)
        status = response.status_code
        response.raise_for_status()
        jobs = response.json().get("jobs", [])
        return VerificationResult(status="verified", access_mode="public", job_count=len(jobs), http_status=status, terms_risk="low")
    except Exception as exc:
        return VerificationResult(status="failed", access_mode="public", error_type=type(exc).__name__, error_message_redacted=str(exc)[:240], terms_risk="low")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    response = await fetch_public_https(_jobs_endpoint(config, content=True), timeout=10)
    response.raise_for_status()
    jobs = response.json().get("jobs", [])
    return [_normalize_job(item, config) for item in jobs[: query.limit]]


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    job_id = external_id_or_path.strip("/").split("/")[-1]
    response = await fetch_public_https(f"https://boards-api.greenhouse.io/v1/boards/{config.provider_key}/jobs/{job_id}", timeout=10)
    response.raise_for_status()
    return _normalize_job(response.json(), config)


def _jobs_endpoint(config: SourceConfig, *, content: bool) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{config.provider_key}/jobs?content={'true' if content else 'false'}"


def _normalize_job(item: dict, config: SourceConfig) -> NormalizedJobPosting:
    location = item.get("location") or {}
    departments = item.get("departments") or []
    absolute_url = item.get("absolute_url") or f"https://boards.greenhouse.io/{config.provider_key}/jobs/{item.get('id')}"
    return NormalizedJobPosting(
        external_job_id=text_or_none(item.get("id")),
        title=text_or_none(item.get("title")) or "Untitled role",
        company_name=config.company_name or config.provider_key,
        company_domain=config.company_domain,
        description_text=text_or_none(item.get("content")),
        location_text=text_or_none(location.get("name") if isinstance(location, dict) else location),
        remote_status=None,
        employment_type=None,
        department=text_or_none(departments[0].get("name")) if departments and isinstance(departments[0], dict) else None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        date_posted=None,
        valid_through=None,
        canonical_url=absolute_url,
        source_type=PROVIDER,
        source_confidence=0.95,
        redacted_metadata={"provider_key": config.provider_key},
    )
