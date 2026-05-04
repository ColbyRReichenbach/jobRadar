from __future__ import annotations

import asyncio
import os
import uuid

from sqlalchemy import select

from backend.celery_app import celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def verify_source_by_id_async(source_id: uuid.UUID) -> dict:
    from backend.database import async_session_factory
    from backend.models import CompanyJobSource
    from backend.services.job_sources.verifier import verify_company_job_source
    from backend.services.source_intelligence.locks import source_intelligence_lock

    async with async_session_factory() as db:
        source = (await db.execute(select(CompanyJobSource).where(CompanyJobSource.id == source_id))).scalar_one_or_none()
        if not source:
            return {"source_id": str(source_id), "status": "missing"}
        async with source_intelligence_lock(db, f"job-source-verify:{source_id}") as locked:
            if not locked:
                return {"source_id": str(source_id), "status": "skipped_locked"}
            result = await verify_company_job_source(db, source)
            await db.commit()
            return {
                "source_id": str(source_id),
                "provider_type": source.provider_type,
                "status": result.status,
                "job_count": result.job_count,
                "error_type": result.error_type,
            }


async def verify_due_sources_async(limit: int | None = None) -> dict:
    from backend.database import async_session_factory
    from backend.models import CompanyJobSource
    from backend.services.job_sources.verifier import verify_company_job_source
    from backend.services.source_intelligence.locks import source_intelligence_lock

    max_sources = limit or int(os.getenv("SOURCE_VERIFICATION_MAX_SOURCES_PER_RUN", "100"))
    async with async_session_factory() as db:
        sources = (
            await db.execute(
                select(CompanyJobSource)
                .where(
                    CompanyJobSource.active.is_(True),
                    CompanyJobSource.verification_status.in_(("pending", "stale", "failed")),
                )
                .order_by(CompanyJobSource.last_verified_at.asc().nullsfirst(), CompanyJobSource.updated_at.asc())
                .limit(max_sources)
            )
        ).scalars().all()
        results = []
        for source in sources:
            async with source_intelligence_lock(db, f"job-source-verify:{source.id}") as locked:
                if not locked:
                    results.append({"source_id": str(source.id), "provider_type": source.provider_type, "status": "skipped_locked"})
                    continue
                result = await verify_company_job_source(db, source)
                results.append({"source_id": str(source.id), "provider_type": source.provider_type, "status": result.status})
        await db.commit()
        return {"checked": len(results), "results": results}


@celery_app.task(name="backend.tasks.verify_job_sources.verify_source_by_id", bind=True, max_retries=3)
def verify_source_by_id(self, source_id: str) -> dict:
    try:
        return _run_async(verify_source_by_id_async(uuid.UUID(source_id)))
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="backend.tasks.verify_job_sources.verify_due_sources", bind=True, max_retries=3)
def verify_due_sources(self, limit: int | None = None) -> dict:
    try:
        return _run_async(verify_due_sources_async(limit=limit))
    except Exception as exc:
        raise self.retry(exc=exc)
