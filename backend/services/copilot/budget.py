"""Copilot budget controls."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiModelCall
from backend.services.copilot.config import global_daily_cost_cap_cents, per_user_daily_cost_cap_cents


def _day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def _sum_copilot_cost(db: AsyncSession, *, user_id: uuid.UUID | None = None) -> int:
    filters = [
        AiModelCall.surface == "copilot",
        AiModelCall.created_at >= _day_start(),
    ]
    if user_id is not None:
        filters.append(AiModelCall.user_id == user_id)
    value = (await db.execute(select(func.coalesce(func.sum(AiModelCall.cost_estimate_cents), 0)).where(*filters))).scalar_one()
    return int(value or 0)


async def enforce_copilot_budget(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    user_cap = per_user_daily_cost_cap_cents()
    global_cap = global_daily_cost_cap_cents()
    if user_cap and await _sum_copilot_cost(db, user_id=user_id) >= user_cap:
        raise HTTPException(status_code=429, detail="Copilot daily budget reached")
    if global_cap and await _sum_copilot_cost(db) >= global_cap:
        raise HTTPException(status_code=429, detail="Copilot global daily budget reached")
