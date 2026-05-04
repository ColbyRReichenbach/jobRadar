from __future__ import annotations

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult, text_or_none
from backend.services.source_intelligence.url_classifier import classify_url
from backend.services.url_safety import fetch_public_https


PROVIDER = "smartrecruiters"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if classified.provider_type != PROVIDER or not classified.provider_key:
        return None
    company = classified.provider_key
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=company,
        access_mode="unknown",
        company_name=company,
        career_url=f"https://careers.smartrecruiters.com/{company}",
        public_jobs_endpoint=f"https://api.smartrecruiters.com/v1/companies/{company}/postings",
        source_config={"company_identifier": company},
        verification_status="needs_review",
        terms_risk="unknown",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    if config.access_mode not in {"public", "api_key"}:
        return VerificationResult(status="needs_review", access_mode=config.access_mode, terms_risk="unknown")
    try:
        response = await fetch_public_https(config.public_jobs_endpoint or _endpoint(config), timeout=10)
        status = response.status_code
        response.raise_for_status()
        jobs = _jobs_from_payload(response.json())
        return VerificationResult(status="verified", access_mode=config.access_mode, job_count=len(jobs), http_status=status, terms_risk="unknown")
    except Exception as exc:
        return VerificationResult(status="failed", access_mode=config.access_mode, error_type=type(exc).__name__, error_message_redacted=str(exc)[:240], terms_risk="unknown")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    if config.access_mode not in {"public", "api_key"}:
        return []
    response = await fetch_public_https(config.public_jobs_endpoint or _endpoint(config), timeout=10)
    response.raise_for_status()
    return [_normalize_job(item, config) for item in _jobs_from_payload(response.json())[: query.limit]]


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    jobs = await fetch_jobs(config, SearchQuery(limit=500))
    key = external_id_or_path.strip("/").split("/")[-1]
    return next((job for job in jobs if job.external_job_id == key or job.canonical_url.rstrip("/").endswith(key)), None)


def _endpoint(config: SourceConfig) -> str:
    return f"https://api.smartrecruiters.com/v1/companies/{config.provider_key}/postings"


def _jobs_from_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        content = payload.get("content") or payload.get("jobs") or []
        return content if isinstance(content, list) else []
    return payload if isinstance(payload, list) else []


def _normalize_job(item: dict, config: SourceConfig) -> NormalizedJobPosting:
    location = item.get("location") or {}
    return NormalizedJobPosting(
        external_job_id=text_or_none(item.get("id") or item.get("uuid")),
        title=text_or_none(item.get("name") or item.get("title")) or "Untitled role",
        company_name=config.company_name or config.provider_key,
        company_domain=config.company_domain,
        description_text=text_or_none(item.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text") if isinstance(item.get("jobAd"), dict) else item.get("description")),
        location_text=text_or_none(location.get("city") if isinstance(location, dict) else location),
        remote_status=None,
        employment_type=text_or_none(item.get("typeOfEmployment", {}).get("label") if isinstance(item.get("typeOfEmployment"), dict) else item.get("typeOfEmployment")),
        department=text_or_none(item.get("department", {}).get("label") if isinstance(item.get("department"), dict) else item.get("department")),
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        date_posted=None,
        valid_through=None,
        canonical_url=text_or_none(item.get("ref") or item.get("postingUrl")) or f"https://jobs.smartrecruiters.com/{config.provider_key}/{item.get('id')}",
        source_type=PROVIDER,
        source_confidence=0.85,
        redacted_metadata={"provider_key": config.provider_key},
    )

