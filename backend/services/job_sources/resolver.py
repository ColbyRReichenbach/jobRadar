from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CompanyJobSource, JobSearchProviderUsage
from backend.metrics import (
    observe_job_search_broad_api_call,
    observe_job_search_broad_api_call_avoided,
    observe_job_search_request,
    observe_job_search_results,
)
from backend.services.job_sources import ashby, greenhouse, lever, workable
from backend.services.job_sources.base import NormalizedJobPosting, SearchQuery, SourceConfig
from backend.services.job_sources.registry import upsert_company_job_source, upsert_job_posting
from backend.services.job_sources.role_matcher import rank_postings
from backend.services.source_intelligence.discovery import parse_source_config
from backend.services.source_intelligence.url_sanitizer import source_link_hash


BroadSearchFn = Callable[[str, str], Awaitable[list[dict]]]


ADAPTERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
}

ALLOWED_ACCESS_MODES = {"public"}


@dataclass(frozen=True)
class SourceSummary:
    direct_sources: list[dict] = field(default_factory=list)
    broad_provider_used: bool = False
    verified_source_count: int = 0
    stale_source_count: int = 0
    blocked_source_count: int = 0

    def to_dict(self) -> dict:
        return {
            "direct_sources": self.direct_sources,
            "broad_provider_used": self.broad_provider_used,
            "verified_source_count": self.verified_source_count,
            "stale_source_count": self.stale_source_count,
            "blocked_source_count": self.blocked_source_count,
        }


@dataclass(frozen=True)
class SearchResolution:
    results: list[dict]
    provider_status: dict
    source_summary: SourceSummary


def direct_sources_enabled() -> bool:
    return os.getenv("JOB_SEARCH_DIRECT_SOURCES_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


async def resolve_job_search(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    location: str,
    broad_search: BroadSearchFn,
) -> SearchResolution:
    sources = await _matching_sources(db, query)
    direct_results: list[NormalizedJobPosting] = []
    direct_source_payloads: list[dict] = []
    degraded_reasons: list[str] = []

    for source in sources:
        adapter = ADAPTERS.get(source.provider_type)
        if not adapter or source.verification_status != "verified" or source.access_mode not in ALLOWED_ACCESS_MODES:
            continue
        config = _config_from_model(source)
        try:
            postings = await adapter.fetch_jobs(config, SearchQuery(query=query, location=location))
        except Exception as exc:
            degraded_reasons.append(f"{source.provider_type} source failed: {type(exc).__name__}")
            continue
        for posting in postings:
            row = await upsert_job_posting(db, source=source, posting=posting)
            direct_results.append(posting)
        direct_source_payloads.append({
            "id": str(source.id),
            "provider_type": source.provider_type,
            "company_name": source.company_name,
            "access_mode": source.access_mode,
            "verification_status": source.verification_status,
        })

    ranked = rank_postings(direct_results, query, location=location)
    result_payloads = [_posting_to_result(match.posting, match.score, match.reasons) for match in ranked if match.score > 0 or not query]
    broad_used = False
    mode = "direct_source" if result_payloads else "provider_limited"
    if result_payloads:
        observe_job_search_broad_api_call_avoided(reason="direct_source")

    if not result_payloads:
        cap = await broad_provider_capacity(db, user_id=user_id, provider="serpapi", query=query, location=location, request_mode="fallback")
        if cap["allowed"] and os.getenv("JOB_SEARCH_BROAD_PROVIDER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
            broad_results = await broad_search(query, location)
            observe_job_search_broad_api_call(provider="serpapi")
            broad_used = bool(broad_results)
            if broad_results:
                await _upsert_broad_source_candidates(db, broad_results)
                await record_broad_provider_usage(
                    db,
                    user_id=user_id,
                    provider="serpapi",
                    query=query,
                    location=location,
                    request_mode="fallback",
                    result_count=len(broad_results),
                )
                result_payloads = broad_results
                mode = "broad_only"
        else:
            degraded_reasons.append(cap["reason"] or "Broad search is not configured.")

    summary = SourceSummary(
        direct_sources=direct_source_payloads,
        broad_provider_used=broad_used,
        verified_source_count=len([source for source in sources if source.verification_status == "verified"]),
        stale_source_count=len([source for source in sources if source.verification_status == "stale"]),
        blocked_source_count=len([source for source in sources if source.verification_status == "blocked"]),
    )
    provider_status = {
        "mode": mode,
        "direct_sources_checked": len(direct_source_payloads),
        "broad_search_used": broad_used,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
        "source_freshness": "verified_today" if direct_source_payloads else "unknown",
        "cost_saved_estimate": {"broad_api_calls_avoided": 1 if direct_source_payloads and not broad_used else 0},
    }
    observe_job_search_request(mode=mode)
    for result in result_payloads:
        observe_job_search_results(source_type=result.get("source"), count=1)
    return SearchResolution(results=result_payloads, provider_status=provider_status, source_summary=summary)


async def _upsert_broad_source_candidates(db: AsyncSession, broad_results: list[dict]) -> None:
    seen: set[str] = set()
    for result in broad_results:
        url = str(result.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        config = parse_source_config(url)
        if not config:
            continue
        await upsert_company_job_source(db, config, discovered_from="broad_search")


async def broad_provider_capacity(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    provider: str,
    query: str,
    location: str,
    request_mode: str,
) -> dict:
    month = date.today().replace(day=1)
    global_cap = int(os.getenv("JOB_SEARCH_SERPAPI_MONTHLY_CAP", "250"))
    user_cap = int(os.getenv("JOB_SEARCH_SERPAPI_USER_MONTHLY_CAP", "25"))
    global_count = await _usage_count(db, provider=provider, month_bucket=month, user_id=None)
    if global_count >= global_cap:
        return {"allowed": False, "reason": "Broad provider monthly cap reached."}
    user_count = await _usage_count(db, provider=provider, month_bucket=month, user_id=user_id)
    if user_count >= user_cap:
        return {"allowed": False, "reason": "Broad provider user monthly cap reached."}
    return {"allowed": True, "reason": None}


async def record_broad_provider_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    provider: str,
    query: str,
    location: str,
    request_mode: str,
    result_count: int,
) -> None:
    month = date.today().replace(day=1)
    query_hash, _ = source_link_hash(f"{query.strip().lower()}|{location.strip().lower()}")
    for key, row_user_id in [(str(user_id), user_id), ("global", None)]:
        existing = (
            await db.execute(
                select(JobSearchProviderUsage).where(
                    JobSearchProviderUsage.user_key == key,
                    JobSearchProviderUsage.provider == provider,
                    JobSearchProviderUsage.request_mode == request_mode,
                    JobSearchProviderUsage.query_hash == query_hash,
                    JobSearchProviderUsage.month_bucket == month,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.request_count += 1
            existing.result_count += result_count
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(JobSearchProviderUsage(
                user_id=row_user_id,
                user_key=key,
                provider=provider,
                request_mode=request_mode,
                query_hash=query_hash,
                month_bucket=month,
                request_count=1,
                result_count=result_count,
            ))


async def _usage_count(db: AsyncSession, *, provider: str, month_bucket: date, user_id: uuid.UUID | None) -> int:
    stmt = select(func.coalesce(func.sum(JobSearchProviderUsage.request_count), 0)).where(
        JobSearchProviderUsage.provider == provider,
        JobSearchProviderUsage.month_bucket == month_bucket,
    )
    if user_id is None:
        stmt = stmt.where(JobSearchProviderUsage.user_key == "global")
    else:
        stmt = stmt.where(JobSearchProviderUsage.user_id == user_id)
    return int((await db.execute(stmt)).scalar_one())


async def _matching_sources(db: AsyncSession, query: str) -> list[CompanyJobSource]:
    result = await db.execute(
        select(CompanyJobSource).where(
            CompanyJobSource.active.is_(True),
        )
    )
    sources = result.scalars().all()
    query_norm = query.lower().strip()
    if not query_norm:
        return sources
    return [
        source for source in sources
        if query_norm in (source.company_name or "").lower()
        or query_norm in (source.company_domain or "").lower()
        or (source.company_name or "").lower() in query_norm
        or (source.provider_key or "").lower() in query_norm
    ]


def _config_from_model(source: CompanyJobSource) -> SourceConfig:
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


def _posting_to_result(posting: NormalizedJobPosting, score: int, reasons: list[str]) -> dict:
    freshness = "seen_today" if posting.date_posted else "known_source"
    return {
        "id": posting.external_job_id or posting.canonical_url,
        "title": posting.title,
        "company": posting.company_name,
        "location": posting.location_text,
        "source": posting.source_type,
        "source_label": "Company career site",
        "source_confidence": posting.source_confidence,
        "freshness": freshness,
        "url": posting.canonical_url,
        "posted_at": posting.date_posted.isoformat() if posting.date_posted else None,
        "description": posting.description_text,
        "match_score": score,
        "match_reasons": reasons,
    }
