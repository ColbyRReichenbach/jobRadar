from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult
from backend.services.source_intelligence.url_classifier import classify_url


PROVIDER = "workday"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if classified.provider_type != PROVIDER or not classified.provider_key or not classified.normalized_url:
        return None
    parsed = urlparse(classified.normalized_url)
    tenant = classified.provider_key
    site = _extract_site(parsed.path)
    cxs_endpoint = f"https://{parsed.netloc}/wday/cxs/{tenant}/{site}/jobs" if site else None
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=f"{tenant}:{site}" if site else tenant,
        access_mode="unknown",
        company_name=tenant,
        career_url=classified.normalized_url,
        public_jobs_endpoint=cxs_endpoint,
        source_config={"tenant": tenant, "site": site, "host": parsed.netloc},
        verification_status="needs_review",
        terms_risk="medium",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    if os.getenv("JOB_SEARCH_WORKDAY_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        return VerificationResult(status="blocked", access_mode=config.access_mode, error_type="workday_disabled", terms_risk="medium")
    return VerificationResult(status="needs_review", access_mode=config.access_mode, error_type="admin_review_required", terms_risk="medium")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    return []


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    return None


def _extract_site(path: str) -> str | None:
    parts = [part for part in path.split("/") if part]
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

