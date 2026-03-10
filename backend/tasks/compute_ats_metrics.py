"""Sprint 8: Celery task to recompute ATS behavioral metrics."""

import asyncio

from backend.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3)
def compute_ats_metrics_task(self):
    """Weekly task: recompute ATS platform behavioral metrics."""
    try:
        result = asyncio.run(_run())
        return result
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


async def _run():
    from backend.database import async_session_factory
    from backend.services.ats_intelligence import compute_ats_metrics

    async with async_session_factory() as db:
        metrics = await compute_ats_metrics(db)
        return {"metrics_computed": len(metrics)}
