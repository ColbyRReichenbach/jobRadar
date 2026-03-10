"""Sprint 19: Weekly digest email task."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_, or_

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def build_digest(db, user_id=None) -> dict:
    """Build weekly digest stats from the last 7 days."""
    from backend.models import Application, Interview, EmailEvent, Alert

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Applications submitted this week
    apps_stmt = select(func.count()).select_from(Application).where(
        and_(
            Application.applied_at.isnot(None),
            Application.applied_at >= week_ago,
        )
    )
    if user_id:
        apps_stmt = apps_stmt.where(Application.user_id == user_id)
    apps_count = (await db.execute(apps_stmt)).scalar() or 0

    # Interviews scheduled this week
    interviews_stmt = select(func.count()).select_from(Interview).where(
        and_(
            Interview.scheduled_at.isnot(None),
            Interview.scheduled_at >= week_ago,
        )
    )
    if user_id:
        interviews_stmt = interviews_stmt.where(Interview.user_id == user_id)
    interviews_count = (await db.execute(interviews_stmt)).scalar() or 0

    # Responses received (emails from companies)
    responses_stmt = select(func.count()).select_from(EmailEvent).where(
        and_(
            EmailEvent.received_at >= week_ago,
            EmailEvent.is_from_user.is_(False),
        )
    )
    if user_id:
        responses_stmt = responses_stmt.where(EmailEvent.user_id == user_id)
    responses_count = (await db.execute(responses_stmt)).scalar() or 0

    # Follow-ups due
    followups_stmt = select(func.count()).select_from(Application).where(
        and_(
            Application.follow_up_due.is_(True),
            Application.archived_at.is_(None),
        )
    )
    if user_id:
        followups_stmt = followups_stmt.where(Application.user_id == user_id)
    followups_count = (await db.execute(followups_stmt)).scalar() or 0

    # Active applications (not archived, not rejected)
    active_stmt = select(func.count()).select_from(Application).where(
        and_(
            Application.archived_at.is_(None),
            Application.status.notin_(["rejected", "denied"]),
        )
    )
    if user_id:
        active_stmt = active_stmt.where(Application.user_id == user_id)
    active_count = (await db.execute(active_stmt)).scalar() or 0

    # Upcoming interviews
    upcoming_stmt = select(func.count()).select_from(Interview).where(
        and_(
            Interview.scheduled_at > datetime.now(timezone.utc),
            or_(Interview.outcome == "pending", Interview.outcome.is_(None)),
        )
    )
    if user_id:
        upcoming_stmt = upcoming_stmt.where(Interview.user_id == user_id)
    upcoming_count = (await db.execute(upcoming_stmt)).scalar() or 0

    return {
        "period_start": week_ago.isoformat(),
        "period_end": datetime.now(timezone.utc).isoformat(),
        "applications_submitted": apps_count,
        "interviews_scheduled": interviews_count,
        "responses_received": responses_count,
        "followups_due": followups_count,
        "active_applications": active_count,
        "upcoming_interviews": upcoming_count,
    }


def render_digest_text(stats: dict) -> str:
    """Render digest stats as plain text email body."""
    lines = [
        "Your AppTrail Weekly Digest",
        "=" * 30,
        "",
        f"This Week ({stats['period_start'][:10]} to {stats['period_end'][:10]})",
        "",
        f"  Applications submitted: {stats['applications_submitted']}",
        f"  Interviews scheduled:   {stats['interviews_scheduled']}",
        f"  Responses received:     {stats['responses_received']}",
        "",
        "Current Status",
        "",
        f"  Active applications:    {stats['active_applications']}",
        f"  Upcoming interviews:    {stats['upcoming_interviews']}",
        f"  Follow-ups due:         {stats['followups_due']}",
        "",
        "Keep up the momentum!",
        "",
        "-- AppTrail",
    ]
    return "\n".join(lines)


async def _send_weekly_digest_async():
    from backend.database import async_session_factory
    from backend.models import NotificationPreference, User

    async with async_session_factory() as db:
        # Find users with digest enabled
        stmt = (
            select(NotificationPreference, User)
            .join(User, NotificationPreference.user_id == User.id)
            .where(NotificationPreference.weekly_digest_enabled == True)
        )
        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            logger.info("No users opted in for weekly digest")
            return 0

        sent = 0

        for pref, user in rows:
            if not user.email:
                continue
            try:
                stats = await build_digest(db, user_id=user.id)
                body = render_digest_text(stats)
                # Use Gmail API if available, otherwise log
                logger.info(f"Weekly digest for {user.email}: {stats}")
                # In production this would send via Gmail API or SendGrid
                # For now we create an alert so users see it in-app
                from backend.models import Alert
                alert = Alert(
                    user_id=user.id,
                    alert_type="weekly_digest",
                    title="Your Weekly Digest",
                    body=body,
                )
                db.add(alert)
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send digest to {user.email}: {e}")

        if sent > 0:
            await db.commit()

        logger.info(f"Sent weekly digest to {sent} users")
        return sent


@celery_app.task(bind=True, max_retries=3)
def send_weekly_digest(self):
    """Celery task: send weekly digest to opted-in users."""
    try:
        return _run_async(_send_weekly_digest_async())
    except Exception as exc:
        logger.error(f"Weekly digest task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
