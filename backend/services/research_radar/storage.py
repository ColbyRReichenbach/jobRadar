from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ResearchRun, ResearchRunStep


def _compact_json(value: Any) -> Any:
    if isinstance(value, list):
        return [_compact_json(item) for item in value[:10]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            if key in {"raw_text", "raw_html", "raw_json"}:
                continue
            compact[key] = _compact_json(item)
        return compact
    if isinstance(value, str) and len(value) > 500:
        return value[:500]
    return value


async def start_step(
    db: AsyncSession,
    *,
    run: ResearchRun,
    step_name: str,
    step_order: int,
    input_json: dict[str, Any] | None = None,
    model_name: str | None = None,
    prompt_version: str | None = None,
    tool_name: str | None = None,
) -> ResearchRunStep:
    run.current_step = step_name
    step = ResearchRunStep(
        run_id=run.id,
        user_id=run.user_id,
        profile_id=run.profile_id,
        step_name=step_name,
        step_order=step_order,
        status="running",
        model_name=model_name,
        prompt_version=prompt_version,
        tool_name=tool_name,
        input_json=_compact_json(input_json or {}),
        started_at=datetime.now(timezone.utc),
    )
    db.add(step)
    await db.flush()
    return step


async def finish_step(
    db: AsyncSession,
    step: ResearchRunStep,
    *,
    output_json: dict[str, Any] | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_estimate_cents: int | None = None,
) -> None:
    step.status = "succeeded"
    step.output_json = _compact_json(output_json or {})
    step.tokens_in = tokens_in
    step.tokens_out = tokens_out
    step.cost_estimate_cents = cost_estimate_cents
    step.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def fail_step(
    db: AsyncSession,
    step: ResearchRunStep | None,
    *,
    error_message: str,
    output_json: dict[str, Any] | None = None,
) -> None:
    if not step:
        return
    step.status = "failed"
    step.error_message = error_message[:2000]
    if output_json is not None:
        step.output_json = _compact_json(output_json)
    step.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def latest_running_step(db: AsyncSession, run_id) -> ResearchRunStep | None:
    return (
        await db.execute(
            select(ResearchRunStep)
            .where(ResearchRunStep.run_id == run_id, ResearchRunStep.status == "running")
            .order_by(ResearchRunStep.step_order.desc())
        )
    ).scalars().first()
