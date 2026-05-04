from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CompanyJobSource, SourceVerificationRun
from backend.metrics import observe_job_source_verified
from backend.services.job_sources import ashby, greenhouse, icims, lever, smartrecruiters, structured_data, workable, workday
from backend.services.job_sources.base import SourceConfig, VerificationResult


_ADAPTER_BY_TYPE = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
    "smartrecruiters": smartrecruiters,
    "icims": icims,
    "workday": workday,
    "structured_data": structured_data,
    "custom_career_page": structured_data,
}


async def verify_company_job_source(db: AsyncSession, source: CompanyJobSource, *, verified_by: str | None = None) -> VerificationResult:
    adapter = _ADAPTER_BY_TYPE.get(source.provider_type)
    started_at = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    if not adapter:
        result = VerificationResult(status="needs_review", access_mode=source.access_mode, error_type="adapter_missing", terms_risk=source.terms_risk)
    else:
        result = await adapter.verify_source(_source_config(source))
    finished_at = datetime.now(timezone.utc)
    duration_seconds = time.monotonic() - started_monotonic
    duration_ms = int(duration_seconds * 1000)
    observe_job_source_verified(
        provider_type=source.provider_type,
        status=result.status,
        duration_seconds=duration_seconds,
        error_type=result.error_type if result.status in {"failed", "blocked"} else None,
    )
    source.verification_status = result.status
    source.terms_risk = result.terms_risk or source.terms_risk
    source.failure_reason = result.error_type
    source.updated_at = finished_at
    if result.status == "verified":
        source.last_verified_at = finished_at
        source.failure_count = 0
        source.failure_reason = None
        if result.access_mode:
            source.access_mode = result.access_mode
    elif result.status in {"failed", "blocked"}:
        source.failure_count = (source.failure_count or 0) + 1
    if verified_by:
        source.verified_by = verified_by
    db.add(
        SourceVerificationRun(
            source_id=source.id,
            status=result.status,
            http_status=result.http_status,
            job_count=result.job_count,
            duration_ms=duration_ms,
            error_type=result.error_type,
            error_message_redacted=_clean(result.error_message_redacted),
            started_at=started_at,
            finished_at=finished_at,
        )
    )
    await db.flush()
    return result


def _source_config(source: CompanyJobSource) -> SourceConfig:
    return SourceConfig(
        provider_type=source.provider_type,
        provider_key=source.provider_key or "",
        access_mode=source.access_mode,
        company_name=source.company_name,
        company_domain=source.company_domain,
        career_url=source.career_url,
        public_jobs_endpoint=source.public_jobs_endpoint,
        source_config=source.source_config or {},
        verification_status=source.verification_status,
        terms_risk=source.terms_risk,
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).replace("\r", " ").replace("\n", " ")[:240]
