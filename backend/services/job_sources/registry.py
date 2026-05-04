from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ApplicationSourceLink, CompanyJobSource, JobPosting
from backend.services.job_sources.base import NormalizedJobPosting, SourceConfig
from backend.services.job_sources.dedupe import dedupe_key_for_posting


async def upsert_company_job_source(
    db: AsyncSession,
    config: SourceConfig,
    *,
    discovered_from: str,
    company_id: uuid.UUID | None = None,
    verification_status: str | None = None,
) -> CompanyJobSource:
    now = datetime.now(timezone.utc)
    existing = (
        await db.execute(
            select(CompanyJobSource).where(
                CompanyJobSource.provider_type == config.provider_type,
                CompanyJobSource.provider_key == config.provider_key,
                CompanyJobSource.access_mode == config.access_mode,
                (CompanyJobSource.company_domain == config.company_domain if config.company_domain else CompanyJobSource.company_domain.is_(None)),
                (CompanyJobSource.career_url == config.career_url if config.career_url else CompanyJobSource.career_url.is_(None)),
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.company_name = config.company_name or existing.company_name
        existing.company_id = company_id or existing.company_id
        existing.public_jobs_endpoint = config.public_jobs_endpoint or existing.public_jobs_endpoint
        existing.source_config = _safe_source_config(config.source_config)
        existing.verification_status = verification_status or config.verification_status or existing.verification_status
        existing.terms_risk = config.terms_risk or existing.terms_risk
        existing.last_seen_at = now
        existing.updated_at = now
        return existing

    source = CompanyJobSource(
        company_id=company_id,
        company_name=config.company_name or config.provider_key,
        company_domain=config.company_domain,
        provider_type=config.provider_type,
        provider_key=config.provider_key,
        access_mode=config.access_mode,
        career_url=config.career_url,
        public_jobs_endpoint=config.public_jobs_endpoint,
        source_config=_safe_source_config(config.source_config),
        verification_status=verification_status or config.verification_status,
        terms_risk=config.terms_risk,
        discovered_from=discovered_from,
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(source)
    await db.flush()
    return source


async def upsert_job_posting(
    db: AsyncSession,
    *,
    source: CompanyJobSource,
    posting: NormalizedJobPosting,
) -> JobPosting:
    now = datetime.now(timezone.utc)
    dedupe_key = dedupe_key_for_posting(posting, provider_key=source.provider_key)
    existing = (await db.execute(select(JobPosting).where(JobPosting.dedupe_key == dedupe_key))).scalar_one_or_none()
    values = {
        "source_id": source.id,
        "external_job_id": posting.external_job_id,
        "company_name": posting.company_name,
        "company_domain": posting.company_domain,
        "title": posting.title,
        "normalized_title": _normalize_title(posting.title),
        "description_text": posting.description_text,
        "description_hash": _description_hash(posting.description_text),
        "location_text": posting.location_text,
        "remote_status": posting.remote_status,
        "employment_type": posting.employment_type,
        "department": posting.department,
        "salary_min": posting.salary_min,
        "salary_max": posting.salary_max,
        "salary_currency": posting.salary_currency,
        "salary_period": posting.salary_period,
        "date_posted": posting.date_posted,
        "valid_through": posting.valid_through,
        "canonical_url": posting.canonical_url,
        "source_type": posting.source_type,
        "source_confidence": posting.source_confidence,
        "active": True,
        "inactive_reason": None,
        "last_seen_at": now,
        "last_verified_at": now,
        "updated_at": now,
    }
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing

    row = JobPosting(dedupe_key=dedupe_key, first_seen_at=now, created_at=now, **values)
    db.add(row)
    await db.flush()
    return row


async def upsert_application_source_link(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    relationship_type: str,
    job_posting_id: uuid.UUID | None = None,
    company_job_source_id: uuid.UUID | None = None,
    user_application_link_id: uuid.UUID | None = None,
    confidence: float = 0,
    created_from: str,
) -> ApplicationSourceLink:
    stmt = select(ApplicationSourceLink).where(
        ApplicationSourceLink.application_id == application_id,
        ApplicationSourceLink.relationship_type == relationship_type,
    )
    if job_posting_id:
        stmt = stmt.where(ApplicationSourceLink.job_posting_id == job_posting_id)
    if user_application_link_id:
        stmt = stmt.where(ApplicationSourceLink.user_application_link_id == user_application_link_id)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.confidence = max(existing.confidence or 0, confidence)
        existing.company_job_source_id = company_job_source_id or existing.company_job_source_id
        existing.updated_at = datetime.now(timezone.utc)
        return existing
    row = ApplicationSourceLink(
        user_id=user_id,
        application_id=application_id,
        job_posting_id=job_posting_id,
        company_job_source_id=company_job_source_id,
        user_application_link_id=user_application_link_id,
        relationship_type=relationship_type,
        confidence=confidence,
        created_from=created_from,
    )
    db.add(row)
    await db.flush()
    return row


def _safe_source_config(config: dict | None) -> dict:
    blocked = {"token", "api_key", "authorization", "cookie", "headers", "query", "raw_url"}
    return {key: value for key, value in (config or {}).items() if key.lower() not in blocked}


def _normalize_title(title: str | None) -> str | None:
    if not title:
        return None
    return " ".join(title.lower().split())


def _description_hash(description: str | None) -> str | None:
    if not description:
        return None
    import hashlib

    return hashlib.sha256(description.encode("utf-8")).hexdigest()

