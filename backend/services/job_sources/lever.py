from __future__ import annotations

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult, text_or_none
from backend.services.source_intelligence.url_classifier import classify_url
from backend.services.url_safety import fetch_public_https


PROVIDER = "lever"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if classified.provider_type != PROVIDER or not classified.provider_key:
        return None
    site = classified.provider_key
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=site,
        access_mode="public",
        company_name=site,
        career_url=f"https://jobs.lever.co/{site}",
        public_jobs_endpoint=f"https://api.lever.co/v0/postings/{site}?mode=json",
        source_config={"site": site},
        verification_status="pending",
        terms_risk="low",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    try:
        response = await fetch_public_https(config.public_jobs_endpoint or _endpoint(config), timeout=10)
        status = response.status_code
        response.raise_for_status()
        jobs = response.json()
        return VerificationResult(status="verified", access_mode="public", job_count=len(jobs), http_status=status, terms_risk="low")
    except Exception as exc:
        return VerificationResult(status="failed", access_mode="public", error_type=type(exc).__name__, error_message_redacted=str(exc)[:240], terms_risk="low")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    response = await fetch_public_https(config.public_jobs_endpoint or _endpoint(config), timeout=10)
    response.raise_for_status()
    return [_normalize_job(item, config) for item in response.json()[: query.limit]]


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    posting_id = external_id_or_path.strip("/").split("/")[-1]
    response = await fetch_public_https(f"https://api.lever.co/v0/postings/{config.provider_key}/{posting_id}?mode=json", timeout=10)
    response.raise_for_status()
    return _normalize_job(response.json(), config)


def _endpoint(config: SourceConfig) -> str:
    return f"https://api.lever.co/v0/postings/{config.provider_key}?mode=json"


def _normalize_job(item: dict, config: SourceConfig) -> NormalizedJobPosting:
    categories = item.get("categories") or {}
    return NormalizedJobPosting(
        external_job_id=text_or_none(item.get("id")),
        title=text_or_none(item.get("text")) or "Untitled role",
        company_name=config.company_name or config.provider_key,
        company_domain=config.company_domain,
        description_text=text_or_none(item.get("descriptionPlain") or item.get("description")),
        location_text=text_or_none(categories.get("location")),
        remote_status=None,
        employment_type=text_or_none(categories.get("commitment")),
        department=text_or_none(categories.get("team")),
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        date_posted=None,
        valid_through=None,
        canonical_url=text_or_none(item.get("hostedUrl") or item.get("applyUrl")) or f"https://jobs.lever.co/{config.provider_key}/{item.get('id')}",
        source_type=PROVIDER,
        source_confidence=0.95,
        redacted_metadata={"provider_key": config.provider_key},
    )

