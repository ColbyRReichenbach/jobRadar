"""Versioned model pricing and token-cost helpers."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import AiModelPricing


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    input_token_cents_per_1m: float
    output_token_cents_per_1m: float
    cached_input_token_cents_per_1m: float | None = None
    reasoning_token_cents_per_1m: float | None = None


DEFAULT_MODEL_PRICING: dict[tuple[str, str], ModelPricing] = {
    ("openai", "gpt-4o-mini"): ModelPricing(
        provider="openai",
        model="gpt-4o-mini",
        input_token_cents_per_1m=15.0,
        output_token_cents_per_1m=60.0,
        cached_input_token_cents_per_1m=7.5,
    ),
    ("openai", "gpt-4o"): ModelPricing(
        provider="openai",
        model="gpt-4o",
        input_token_cents_per_1m=250.0,
        output_token_cents_per_1m=1000.0,
        cached_input_token_cents_per_1m=125.0,
    ),
    ("openai", "gpt-5.1"): ModelPricing(
        provider="openai",
        model="gpt-5.1",
        input_token_cents_per_1m=250.0,
        output_token_cents_per_1m=1000.0,
        cached_input_token_cents_per_1m=125.0,
        reasoning_token_cents_per_1m=1000.0,
    ),
    ("openai", "gpt-5.4"): ModelPricing(
        provider="openai",
        model="gpt-5.4",
        input_token_cents_per_1m=1000.0,
        output_token_cents_per_1m=3000.0,
        cached_input_token_cents_per_1m=500.0,
        reasoning_token_cents_per_1m=3000.0,
    ),
}


def _clean_model(model: str) -> str:
    return (model or "").strip()


def _pricing_from_payload(provider: str, model: str, payload: dict[str, Any]) -> ModelPricing:
    return ModelPricing(
        provider=provider,
        model=model,
        input_token_cents_per_1m=float(payload.get("input_token_cents_per_1m", 0.0)),
        output_token_cents_per_1m=float(payload.get("output_token_cents_per_1m", 0.0)),
        cached_input_token_cents_per_1m=(
            float(payload["cached_input_token_cents_per_1m"]) if payload.get("cached_input_token_cents_per_1m") is not None else None
        ),
        reasoning_token_cents_per_1m=(
            float(payload["reasoning_token_cents_per_1m"]) if payload.get("reasoning_token_cents_per_1m") is not None else None
        ),
    )


def load_pricing_config(raw_config: str | None = None) -> dict[tuple[str, str], ModelPricing]:
    """Load model pricing overrides from JSON while preserving conservative defaults.

    Expected shape:
    {
      "openai:gpt-4o-mini": {
        "input_token_cents_per_1m": 15,
        "output_token_cents_per_1m": 60
      }
    }
    """

    pricing = dict(DEFAULT_MODEL_PRICING)
    raw = raw_config if raw_config is not None else os.getenv("AI_MODEL_PRICING_CONFIG", "")
    if not raw.strip():
        return pricing

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("AI_MODEL_PRICING_CONFIG must be a JSON object")

    for key, payload in parsed.items():
        if not isinstance(key, str) or ":" not in key:
            raise ValueError("AI_MODEL_PRICING_CONFIG keys must use provider:model format")
        if not isinstance(payload, dict):
            raise ValueError("AI_MODEL_PRICING_CONFIG values must be objects")
        provider, model = key.split(":", 1)
        provider = provider.strip() or "openai"
        model = _clean_model(model)
        if not model:
            raise ValueError("AI_MODEL_PRICING_CONFIG model cannot be empty")
        pricing[(provider, model)] = _pricing_from_payload(provider, model, payload)
    return pricing


def get_model_pricing(provider: str, model: str, pricing_config: dict[tuple[str, str], ModelPricing] | None = None) -> ModelPricing:
    provider = (provider or "openai").strip()
    model = _clean_model(model)
    pricing = pricing_config or load_pricing_config()
    return pricing.get((provider, model)) or ModelPricing(
        provider=provider,
        model=model,
        input_token_cents_per_1m=0.0,
        output_token_cents_per_1m=0.0,
    )


async def record_model_pricing(
    db: AsyncSession,
    pricing: ModelPricing,
    *,
    effective_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> AiModelPricing:
    row = AiModelPricing(
        provider=pricing.provider,
        model=pricing.model,
        input_token_cents_per_1m=pricing.input_token_cents_per_1m,
        output_token_cents_per_1m=pricing.output_token_cents_per_1m,
        cached_input_token_cents_per_1m=pricing.cached_input_token_cents_per_1m,
        reasoning_token_cents_per_1m=pricing.reasoning_token_cents_per_1m,
        metadata_json=metadata,
        effective_at=effective_at or datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


async def get_effective_model_pricing(
    db: AsyncSession,
    *,
    provider: str,
    model: str,
    at: datetime | None = None,
) -> ModelPricing:
    effective_at = at or datetime.now(timezone.utc)
    result = await db.execute(
        select(AiModelPricing)
        .where(
            AiModelPricing.provider == provider,
            AiModelPricing.model == model,
            AiModelPricing.effective_at <= effective_at,
        )
        .order_by(desc(AiModelPricing.effective_at))
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return get_model_pricing(provider, model)
    return ModelPricing(
        provider=row.provider,
        model=row.model,
        input_token_cents_per_1m=row.input_token_cents_per_1m,
        output_token_cents_per_1m=row.output_token_cents_per_1m,
        cached_input_token_cents_per_1m=row.cached_input_token_cents_per_1m,
        reasoning_token_cents_per_1m=row.reasoning_token_cents_per_1m,
    )


def _cost_component(tokens: int | None, cents_per_1m: float | None) -> float:
    if not tokens or not cents_per_1m:
        return 0.0
    return max(tokens, 0) * cents_per_1m / 1_000_000


def estimate_cost_cents(
    *,
    model: str,
    provider: str = "openai",
    prompt_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    pricing_config: dict[tuple[str, str], ModelPricing] | None = None,
) -> tuple[int, dict[str, Any]]:
    pricing = get_model_pricing(provider, model, pricing_config)
    uncached_input_tokens = max((prompt_tokens or 0) - (cached_input_tokens or 0), 0)
    input_cost = _cost_component(uncached_input_tokens, pricing.input_token_cents_per_1m)
    cached_cost = _cost_component(cached_input_tokens, pricing.cached_input_token_cents_per_1m)
    output_cost = _cost_component(output_tokens, pricing.output_token_cents_per_1m)
    reasoning_cost = _cost_component(reasoning_tokens, pricing.reasoning_token_cents_per_1m)
    total = input_cost + cached_cost + output_cost + reasoning_cost
    rounded_total = int(math.ceil(total)) if total > 0 else 0
    return rounded_total, {
        "provider": pricing.provider,
        "model": pricing.model,
        "pricing_basis": "cents_per_1m_tokens",
        "input_cost_cents": round(input_cost, 6),
        "cached_input_cost_cents": round(cached_cost, 6),
        "output_cost_cents": round(output_cost, 6),
        "reasoning_cost_cents": round(reasoning_cost, 6),
        "total_cost_cents": rounded_total,
        "uncached_input_tokens": uncached_input_tokens,
    }
