from __future__ import annotations

import os
import re
from urllib.parse import quote, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult, parse_datetime, text_or_none
from backend.services.job_sources.rate_limiter import ProviderRateLimitExceeded, enforce_provider_rate_limit
from backend.services.source_intelligence.url_classifier import classify_url
from backend.services.url_safety import fetch_public_https


PROVIDER = "workday"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if classified.provider_type != PROVIDER or not classified.provider_key or not classified.normalized_url:
        return None
    parsed = urlparse(classified.normalized_url)
    parts = [part for part in parsed.path.split("/") if part]
    tenant = classified.provider_key
    site = _extract_site(parts)
    locale = _extract_locale(parts)
    server = _extract_server(parsed.netloc)
    cxs_endpoint = _cxs_jobs_endpoint(parsed.netloc, tenant, site) if site else None
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=f"{tenant}:{site}" if site else tenant,
        access_mode="unknown",
        company_name=tenant,
        career_url=classified.normalized_url,
        public_jobs_endpoint=cxs_endpoint,
        source_config={
            "tenant": tenant,
            "site": site,
            "host": parsed.netloc,
            "server": server,
            "locale": locale,
            "cxs_jobs_endpoint": cxs_endpoint,
        },
        verification_status="needs_review",
        terms_risk="medium",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    if not _workday_enabled():
        return VerificationResult(status="blocked", access_mode=config.access_mode, error_type="workday_disabled", terms_risk="medium")
    endpoint = config.public_jobs_endpoint or config.source_config.get("cxs_jobs_endpoint")
    if not endpoint:
        return VerificationResult(status="needs_review", access_mode=config.access_mode, error_type="missing_cxs_endpoint", terms_risk="medium")
    try:
        payload = await _post_jobs(config, endpoint, limit=1, offset=0)
        count = _job_count(payload)
        return VerificationResult(
            status="needs_review",
            access_mode=config.access_mode,
            job_count=count,
            error_type="admin_review_required",
            error_message_redacted="technical_verification_passed",
            terms_risk="medium",
        )
    except ProviderRateLimitExceeded:
        return VerificationResult(status="failed", access_mode=config.access_mode, error_type="rate_limited", terms_risk="medium")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            return VerificationResult(status="failed", access_mode=config.access_mode, http_status=429, error_type="rate_limited", terms_risk="medium")
        return VerificationResult(
            status="failed",
            access_mode=config.access_mode,
            http_status=exc.response.status_code,
            error_type="HTTPStatusError",
            error_message_redacted=str(exc)[:240],
            terms_risk="medium",
        )
    except Exception as exc:
        return VerificationResult(status="failed", access_mode=config.access_mode, error_type=type(exc).__name__, error_message_redacted=str(exc)[:240], terms_risk="medium")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    if not _workday_enabled() or config.access_mode not in {"public", "api_key"}:
        return []
    endpoint = config.public_jobs_endpoint or config.source_config.get("cxs_jobs_endpoint")
    if not endpoint:
        return []
    payload = await _post_jobs(config, endpoint, limit=min(max(query.limit, 1), 50), offset=0, search_text=query.query)
    normalized: list[NormalizedJobPosting] = []
    for item in _job_items(payload):
        posting = _normalize_job(config, item)
        if posting:
            normalized.append(posting)
    return normalized


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    if not _workday_enabled() or config.access_mode not in {"public", "api_key"}:
        return None
    endpoint = _cxs_detail_endpoint(config, external_id_or_path)
    if not endpoint:
        return None
    response = await fetch_public_https(endpoint, timeout=10, headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    return _normalize_job(config, payload)


def _workday_enabled() -> bool:
    return os.getenv("JOB_SEARCH_WORKDAY_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


async def _post_jobs(config: SourceConfig, endpoint: str, *, limit: int, offset: int, search_text: str = "") -> dict:
    await _enforce_workday_limits(config)
    response = await fetch_public_https(
        endpoint,
        timeout=float(os.getenv("SOURCE_FETCH_TIMEOUT_SECONDS", "10")),
        method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        json_body={"limit": limit, "offset": offset, "searchText": search_text, "appliedFacets": {}},
    )
    response.raise_for_status()
    return response.json()


async def _enforce_workday_limits(config: SourceConfig) -> None:
    tenant = config.source_config.get("tenant") or config.provider_key
    await enforce_provider_rate_limit("workday", "global", limit=int(os.getenv("JOB_SOURCE_WORKDAY_GLOBAL_RPM", "30")))
    await enforce_provider_rate_limit(
        "workday",
        f"tenant:{tenant}",
        limit=int(os.getenv("JOB_SOURCE_WORKDAY_TENANT_RPM", "6")),
        min_interval_seconds=float(os.getenv("JOB_SOURCE_WORKDAY_MIN_INTERVAL_SECONDS", "1.5")),
    )


def _extract_site(parts: list[str]) -> str | None:
    if not parts:
        return None
    if "wday" in parts and "cxs" in parts:
        try:
            idx = parts.index("cxs")
            return parts[idx + 2]
        except (ValueError, IndexError):
            return None
    if parts[0] == "recruiting" and len(parts) >= 3:
        return parts[2]
    if re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]) and len(parts) >= 2:
        return parts[1]
    return parts[0]


def _extract_locale(parts: list[str]) -> str | None:
    if parts and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]):
        return parts[0]
    return None


def _extract_server(host: str) -> str | None:
    match = re.search(r"\.(wd\d+)\.myworkdayjobs\.com$", host)
    return match.group(1) if match else None


def _cxs_jobs_endpoint(host: str, tenant: str, site: str | None) -> str | None:
    if not site:
        return None
    return f"https://{host}/wday/cxs/{quote(tenant, safe='')}/{quote(site, safe='')}/jobs"


def _cxs_detail_endpoint(config: SourceConfig, external_path: str) -> str | None:
    host = config.source_config.get("host")
    tenant = config.source_config.get("tenant")
    site = config.source_config.get("site")
    if not host or not tenant or not site or not external_path:
        return None
    path = str(external_path).strip().lstrip("/")
    if path.startswith("job/"):
        path = path.removeprefix("job/")
    return f"https://{host}/wday/cxs/{quote(tenant, safe='')}/{quote(site, safe='')}/job/{path}"


def _job_count(payload: dict) -> int:
    total = payload.get("total")
    if isinstance(total, int):
        return total
    return len(_job_items(payload))


def _job_items(payload: dict) -> list[dict]:
    for key in ("jobPostings", "jobs", "postings"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_job(config: SourceConfig, item: dict) -> NormalizedJobPosting | None:
    title = text_or_none(item.get("title") or item.get("jobTitle"))
    if not title:
        return None
    external_path = text_or_none(item.get("externalPath") or item.get("externalUrl") or item.get("url"))
    req_id = text_or_none(item.get("jobReqId") or item.get("requisitionId") or item.get("id") or external_path)
    description = text_or_none(item.get("jobDescription") or item.get("description") or item.get("jobDescriptionText"))
    canonical_url = _career_job_url(config, external_path) or config.career_url or config.public_jobs_endpoint or ""
    return NormalizedJobPosting(
        external_job_id=req_id,
        title=title,
        company_name=config.company_name or config.source_config.get("tenant") or "Workday employer",
        company_domain=config.company_domain,
        description_text=BeautifulSoup(description or "", "html.parser").get_text(" ", strip=True) or None,
        location_text=_location_text(item),
        remote_status=None,
        employment_type=text_or_none(item.get("timeType") or item.get("workerSubType")),
        department=text_or_none(item.get("jobFamily") or item.get("supervisoryOrganization")),
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        date_posted=parse_datetime(item.get("postedOn") or item.get("startDate")),
        valid_through=parse_datetime(item.get("endDate")),
        canonical_url=canonical_url,
        source_type=PROVIDER,
        source_confidence=0.78,
        redacted_metadata={"provider_key": config.provider_key, "terms_risk": "medium"},
    )


def _location_text(item: dict) -> str | None:
    text = text_or_none(item.get("locationsText") or item.get("location"))
    if text:
        return text
    locations = item.get("locations")
    if isinstance(locations, list):
        names = [text_or_none(value.get("displayName") if isinstance(value, dict) else value) for value in locations]
        return "; ".join(name for name in names if name) or None
    return None


def _career_job_url(config: SourceConfig, external_path: str | None) -> str | None:
    if not external_path:
        return None
    if external_path.startswith("https://"):
        return external_path
    host = config.source_config.get("host")
    site = config.source_config.get("site")
    tenant = config.source_config.get("tenant")
    if not host or not site:
        return None
    path = external_path.strip().lstrip("/")
    if host == "jobs.myworkdaysite.com" and tenant:
        return f"https://{host}/recruiting/{tenant}/{site}/{path}"
    locale = config.source_config.get("locale") or "en-US"
    if not path.startswith("job/"):
        path = f"job/{path}"
    return f"https://{host}/{locale}/{site}/{path}"
