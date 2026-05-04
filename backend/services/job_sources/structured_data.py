from __future__ import annotations

from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig, VerificationResult


PROVIDER = "structured_data"


def parse_source_from_url(url: str) -> SourceConfig | None:
    return None


async def verify_source(config: SourceConfig) -> VerificationResult:
    return VerificationResult(status="needs_review", access_mode=config.access_mode, error_type="not_implemented", terms_risk="unknown")


async def fetch_jobs(config: SourceConfig, query: SearchQuery) -> list[NormalizedJobPosting]:
    return []


async def fetch_job_detail(config: SourceConfig, external_id_or_path: str) -> NormalizedJobPosting | None:
    return None

