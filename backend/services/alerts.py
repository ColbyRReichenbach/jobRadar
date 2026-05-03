from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Alert, NotificationPreference, User
from backend.services.notification_preferences import is_alert_enabled


RADAR_ALERT_TYPES = {"opportunity_signal", "research_report_ready", "research_run_failed"}
ADMIN_AI_ALERT_TYPES = {"ai_safety_quarantine", "ai_safety_block", "ai_rate_limit", "ai_budget_block"}


def _env_int(name: str, *, default: int, minimum: int = 0) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except ValueError:
        return default


async def _radar_alert_volume_allows(db: AsyncSession, *, user_id, alert_type: str) -> bool:
    if alert_type not in RADAR_ALERT_TYPES:
        return True

    max_per_day = _env_int("RADAR_ALERT_MAX_PER_USER_PER_DAY", default=5)
    if max_per_day <= 0:
        return False

    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = (
        await db.execute(
            select(func.count(Alert.id)).where(
                Alert.user_id == user_id,
                Alert.alert_type.in_(RADAR_ALERT_TYPES),
                Alert.created_at >= since,
            )
        )
    ).scalar_one()
    return int(count or 0) < max_per_day


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

    if not await _radar_alert_volume_allows(db, user_id=user_id, alert_type=alert_type):
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


async def create_admin_operational_alert(
    db: AsyncSession,
    *,
    alert_type: str,
    title: str,
    body: str | None = None,
    action_url: str | None = None,
    dedupe_key: str | None = None,
) -> int:
    """Create a low-volume in-app alert for each admin user.

    The dedupe key prevents repeated safety events from flooding the admin
    notification center while still preserving the full event ledger in AI Ops.
    """
    if alert_type not in ADMIN_AI_ALERT_TYPES:
        return 0
    if os.getenv("AI_ADMIN_ALERTS_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return 0

    admins = list((await db.execute(select(User).where(User.is_admin.is_(True)))).scalars())
    if not admins:
        return 0

    created = 0
    since = datetime.now(timezone.utc) - timedelta(hours=6)
    for admin in admins:
        filters = [
            Alert.user_id == admin.id,
            Alert.alert_type == alert_type,
            Alert.created_at >= since,
        ]
        if dedupe_key:
            filters.append(Alert.action_url == dedupe_key)
        existing = (await db.execute(select(Alert.id).where(*filters).limit(1))).scalar_one_or_none()
        if existing:
            continue
        db.add(
            Alert(
                user_id=admin.id,
                alert_type=alert_type,
                title=title,
                body=body,
                action_url=dedupe_key or action_url,
            )
        )
        created += 1
    return created
