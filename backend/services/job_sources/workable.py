from __future__ import annotations

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult, parse_datetime, text_or_none
from backend.services.source_intelligence.url_classifier import classify_url
from backend.services.url_safety import fetch_public_https


PROVIDER = "workable"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if classified.provider_type != PROVIDER or not classified.provider_key:
        return None
    account = classified.provider_key
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=account,
        access_mode="public",
        company_name=account,
        career_url=f"https://apply.workable.com/{account}/",
        public_jobs_endpoint=f"https://www.workable.com/api/accounts/{account}?details=true",
        source_config={"account": account},
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
    key = external_id_or_path.strip("/").split("/")[-1].lower()
    return next((job for job in jobs if (job.external_job_id or "").lower() == key or job.canonical_url.lower().rstrip("/").endswith(key)), None)


def _endpoint(config: SourceConfig) -> str:
    return f"https://www.workable.com/api/accounts/{config.provider_key}?details=true"


def _jobs_from_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        jobs = payload.get("jobs") or []
        return jobs if isinstance(jobs, list) else []
    return []


def _normalize_job(item: dict, config: SourceConfig) -> NormalizedJobPosting:
    location = item.get("location") or {}
    if isinstance(location, dict):
        location_text = ", ".join(str(part) for part in [location.get("city"), location.get("region"), location.get("country")] if part)
    else:
        location_text = location
    shortcode = item.get("shortcode") or item.get("code") or item.get("id")
    return NormalizedJobPosting(
        external_job_id=text_or_none(shortcode),
        title=text_or_none(item.get("title")) or "Untitled role",
        company_name=text_or_none(item.get("company")) or config.company_name or config.provider_key,
        company_domain=config.company_domain,
        description_text=text_or_none(item.get("description") or item.get("description_text")),
        location_text=text_or_none(location_text),
        remote_status=text_or_none(item.get("workplace_type") or item.get("remote")),
        employment_type=text_or_none(item.get("employment_type") or item.get("type")),
        department=text_or_none(item.get("department")),
        salary_min=item.get("salary_min"),
        salary_max=item.get("salary_max"),
        salary_currency=text_or_none(item.get("salary_currency")),
        salary_period=text_or_none(item.get("salary_period")),
        date_posted=parse_datetime(item.get("published") or item.get("created_at")),
        valid_through=None,
        canonical_url=text_or_none(item.get("url") or item.get("application_url")) or f"https://apply.workable.com/{config.provider_key}/j/{shortcode}",
        source_type=PROVIDER,
        source_confidence=0.93,
        redacted_metadata={"provider_key": config.provider_key},
    )
