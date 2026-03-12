"""Sprint 7: Check if job postings are still alive."""

import asyncio
import random
from datetime import datetime, timezone
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.celery_app import celery_app


DEAD_SIGNALS = [
    "position has been filled",
    "no longer accepting applications",
    "this job is no longer available",
    "job has been closed",
    "this position has been closed",
    "this role has been filled",
    "posting has expired",
]

PLATFORM_DEAD_SIGNALS = {
    "greenhouse.io": ["Page not found", "404"],
    "lever.co": ["This position is no longer available"],
    "myworkday.com": ["The page you are looking for cannot be found"],
}


def _alert_action_url(path: str, **params: str | None) -> str:
    clean_params = {key: value for key, value in params.items() if value}
    query = urlencode(clean_params)
    return f"{path}?{query}" if query else path


async def _check_url(url: str) -> dict:
    """Check if a job URL is still alive. Returns {alive: bool, reason: str}."""
    import httpx

    try:
        await asyncio.sleep(random.uniform(2, 4))  # polite delay
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        ) as client:
            resp = await client.get(url)

            if resp.status_code == 404:
                return {"alive": False, "reason": "404 Not Found"}

            if resp.status_code >= 400:
                return {"alive": False, "reason": f"HTTP {resp.status_code}"}

            body = resp.text.lower()[:5000]

            # Check generic dead signals
            for signal in DEAD_SIGNALS:
                if signal in body:
                    return {"alive": False, "reason": signal}

            # Check platform-specific signals
            for platform, signals in PLATFORM_DEAD_SIGNALS.items():
                if platform in url.lower():
                    for sig in signals:
                        if sig.lower() in body:
                            return {"alive": False, "reason": sig}

            # Check for redirect to generic careers page
            final_url = str(resp.url).lower()
            if url.lower() != final_url:
                # Redirected somewhere — check if it's a generic careers page
                if "/careers" in final_url and "/jobs/" not in final_url:
                    return {"alive": False, "reason": "Redirected to generic careers page"}

            return {"alive": True, "reason": ""}

    except Exception as e:
        # Network errors — don't mark as dead, just skip
        return {"alive": True, "reason": f"check_error: {str(e)}"}


async def _run_check():
    """Check up to 50 active applications for dead listings."""
    from backend.database import async_session_factory
    from backend.models import Alert, Application, NotificationPreference, User
    from backend.services.notification_preferences import is_alert_enabled

    async with async_session_factory() as db:
        enabled_users_result = await db.execute(
            select(User.id).where(User.notifications_started_at.isnot(None))
        )
        enabled_user_ids = {row[0] for row in enabled_users_result.all()}
        pref_result = await db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id.in_(enabled_user_ids))
        )
        prefs_by_user = {pref.user_id: pref for pref in pref_result.scalars().all()}

        stmt = (
            select(Application)
            .where(
                Application.archived_at.is_(None),
                Application.listing_alive.is_(True),
                Application.job_url.isnot(None),
                Application.status.in_(["saved", "applied", "interviewing"]),
            )
            .limit(50)
        )
        result = await db.execute(stmt)
        apps = result.scalars().all()

        checked = 0
        dead = 0
        for app in apps:
            result = await _check_url(app.job_url)
            app.listing_last_checked = datetime.now(timezone.utc)
            if not result["alive"]:
                app.listing_alive = False
                app.listing_died_at = datetime.now(timezone.utc)
                if app.user_id and app.user_id in enabled_user_ids and is_alert_enabled(prefs_by_user.get(app.user_id), "dead_listing"):
                    db.add(
                        Alert(
                            user_id=app.user_id,
                            alert_type="dead_listing",
                            title=f"Posting may be closed at {app.company}",
                            body=f"{app.role_title} looks inactive. Open Pipeline to review this application.",
                            action_url=_alert_action_url("/dashboard", job_id=str(app.id)),
                        )
                    )
                dead += 1
            checked += 1

        await db.commit()
        return {"checked": checked, "dead": dead}


@celery_app.task(bind=True, max_retries=3)
def check_dead_apps(self):
    """Celery task: check if job postings are still alive."""
    try:
        result = asyncio.run(_run_check())
        return result
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
