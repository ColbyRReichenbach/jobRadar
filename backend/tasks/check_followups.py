import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _check_followups_async():
    from backend.database import async_session_factory
    from backend.models import Application

    async with async_session_factory() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = select(Application).where(
            and_(
                Application.status == "applied",
                Application.last_email_at.is_(None),
                Application.applied_at < cutoff,
                Application.archived_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        apps = result.scalars().all()

        count = 0
        for app in apps:
            if not app.follow_up_due:
                app.follow_up_due = True
                count += 1

        if count > 0:
            await db.commit()

        logger.info(f"Flagged {count} applications for follow-up")
        return count


@celery_app.task(bind=True, max_retries=3)
def check_followups(self):
    """Check for applications needing follow-up reminders."""
    try:
        return _run_async(_check_followups_async())
    except Exception as exc:
        logger.error(f"Follow-up check failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
