from __future__ import annotations

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult
from backend.services.source_intelligence.url_classifier import classify_url


PROVIDER = "icims"


def parse_source_from_url(url: str) -> SourceConfig | None:
    classified = classify_url(url)
    if classified.provider_type != PROVIDER or not classified.provider_key:
        return None
    return SourceConfig(
        provider_type=PROVIDER,
        provider_key=classified.provider_key,
        access_mode="credentialed",
        company_name=classified.provider_key,
        career_url=classified.normalized_url,
        public_jobs_endpoint=None,
        source_config={"parsed_public_page": True},
        verification_status="needs_review",
        terms_risk="unknown",
    )


async def verify_source(config: SourceConfig) -> VerificationResult:
    return VerificationResult(status="needs_review", access_mode="credentialed", error_type="credentialed_access_required", terms_risk="unknown")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    return []


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    return None
