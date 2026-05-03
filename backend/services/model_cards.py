"""Model card persistence and audit helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiModelCard


@dataclass(frozen=True)
class ModelCardWarning:
    task_name: str
    model: str
    prompt_version: str
    message: str


async def get_model_card(
    db: AsyncSession,
    *,
    task_name: str,
    model: str,
    prompt_version: str,
) -> AiModelCard | None:
    result = await db.execute(
        select(AiModelCard).where(
            AiModelCard.task_name == task_name,
            AiModelCard.model == model,
            AiModelCard.prompt_version == prompt_version,
        )
    )
    return result.scalar_one_or_none()


async def create_model_card(
    db: AsyncSession,
    *,
    task_name: str,
    model: str,
    prompt_version: str,
    intended_use: str,
    prohibited_use: str | None = None,
    limitations: str | None = None,
    eval_dataset_version: str | None = None,
    primary_metrics: dict | None = None,
    guardrail_metrics: dict | None = None,
    approval_status: str = "draft",
    approved_by_user_id: uuid.UUID | None = None,
    rollback_plan: str | None = None,
    review_cadence: str | None = None,
) -> AiModelCard:
    card = AiModelCard(
        task_name=task_name,
        model=model,
        prompt_version=prompt_version,
        intended_use=intended_use,
        prohibited_use=prohibited_use,
        limitations=limitations,
        eval_dataset_version=eval_dataset_version,
        primary_metrics=primary_metrics,
        guardrail_metrics=guardrail_metrics,
        approval_status=approval_status,
        approved_by_user_id=approved_by_user_id,
        rollback_plan=rollback_plan,
        review_cadence=review_cadence,
    )
    db.add(card)
    await db.flush()
    return card


async def missing_model_card_warning(
    db: AsyncSession,
    *,
    task_name: str,
    model: str,
    prompt_version: str,
) -> ModelCardWarning | None:
    card = await get_model_card(db, task_name=task_name, model=model, prompt_version=prompt_version)
    if card is not None:
        return None
    return ModelCardWarning(
        task_name=task_name,
        model=model,
        prompt_version=prompt_version,
        message=f"Missing model card for {task_name} using {model} / {prompt_version}",
    )
