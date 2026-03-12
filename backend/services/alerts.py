from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Alert, NotificationPreference
from backend.services.notification_preferences import is_alert_enabled


async def create_user_alert(
    db: AsyncSession,
    *,
    user_id,
    alert_type: str,
    title: str,
    body: str | None = None,
    action_url: str | None = None,
    notification_pref: NotificationPreference | None = None,
    respect_preferences: bool = True,
) -> Alert | None:
    pref = notification_pref
    if respect_preferences:
        if pref is None:
            result = await db.execute(
                select(NotificationPreference).where(NotificationPreference.user_id == user_id)
            )
            pref = result.scalar_one_or_none()
        if not is_alert_enabled(pref, alert_type):
            return None

    alert = Alert(
        user_id=user_id,
        alert_type=alert_type,
        title=title,
        body=body,
        action_url=action_url,
    )
    db.add(alert)
    return alert
