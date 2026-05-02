from __future__ import annotations

import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Application, Company


def aggregate_min_users() -> int:
    raw = os.getenv("APPTRAIL_AGGREGATE_MIN_USERS", "3")
    try:
        return max(2, int(raw))
    except ValueError:
        return 3


def has_enough_contributors(count: int | None) -> bool:
    return (count or 0) >= aggregate_min_users()


def bucket_count(count: int | None) -> str | None:
    if count is None or not has_enough_contributors(count):
        return None
    if count < 5:
        return f"{aggregate_min_users()}-4"
    if count < 10:
        return "5-9"
    if count < 25:
        return "10-24"
    if count < 50:
        return "25-49"
    if count < 100:
        return "50-99"
    return "100+"


async def distinct_company_user_count(db: AsyncSession, company_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(func.distinct(Application.user_id))).where(
            Application.company_id == company_id,
            Application.user_id.isnot(None),
        )
    )
    return int(result.scalar() or 0)


async def distinct_ats_user_count(db: AsyncSession, platform: str) -> int:
    result = await db.execute(
        select(func.count(func.distinct(Application.user_id)))
        .join(Company, Company.id == Application.company_id)
        .where(
            Company.ats_platform == platform,
            Application.user_id.isnot(None),
        )
    )
    return int(result.scalar() or 0)
