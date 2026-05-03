import asyncio
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import select, and_

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)


def _alert_action_url(path: str, **params: str | None) -> str:
    clean_params = {key: value for key, value in params.items() if value}
    query = urlencode(clean_params)
    return f"{path}?{query}" if query else path


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _check_followups_async():
    from backend.database import async_session_factory
    from backend.models import Application, NotificationPreference, User
    from backend.services.alerts import create_user_alert

    async with async_session_factory() as db:
        enabled_users_result = await db.execute(
            select(User.id).where(User.notifications_started_at.isnot(None))
        )
        enabled_user_ids = {row[0] for row in enabled_users_result.all()}
        pref_result = await db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id.in_(enabled_user_ids))
        )
        prefs_by_user = {pref.user_id: pref for pref in pref_result.scalars().all()}

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
                if app.user_id and app.user_id in enabled_user_ids:
                    await create_user_alert(
                        db,
                        user_id=app.user_id,
                        alert_type="follow_up",
                        title=f"Follow up with {app.company}",
                        body=f"{app.role_title} has been quiet for over a week. Open Pipeline to review your next step.",
                        action_url=_alert_action_url("/dashboard", job_id=str(app.id)),
                        notification_pref=prefs_by_user.get(app.user_id),
                    )
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
