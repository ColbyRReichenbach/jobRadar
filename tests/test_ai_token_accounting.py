import json
from datetime import datetime, timezone

import pytest

from backend.services.ai_pricing import (
    ModelPricing,
    estimate_cost_cents,
    get_effective_model_pricing,
    load_pricing_config,
    record_model_pricing,
)


def test_estimate_cost_tracks_prompt_output_cached_and_reasoning_tokens():
    cost, breakdown = estimate_cost_cents(
        provider="openai",
        model="gpt-5.1",
        prompt_tokens=10_000,
        cached_input_tokens=4_000,
        reasoning_tokens=2_000,
        output_tokens=1_000,
    )

    assert cost > 0
    assert breakdown["uncached_input_tokens"] == 6_000
    assert breakdown["input_cost_cents"] > 0
    assert breakdown["cached_input_cost_cents"] > 0
    assert breakdown["output_cost_cents"] > 0
    assert breakdown["reasoning_cost_cents"] > 0
    assert breakdown["total_cost_cents"] == cost


def test_pricing_config_override_supports_model_tradeoff_analysis():
    config = load_pricing_config(
        json.dumps(
            {
                "openai:test-cheap": {
                    "input_token_cents_per_1m": 1,
                    "output_token_cents_per_1m": 2,
                },
                "openai:test-expensive": {
                    "input_token_cents_per_1m": 10,
                    "output_token_cents_per_1m": 20,
                },
            }
        )
    )

    cheap, _ = estimate_cost_cents(
        provider="openai",
        model="test-cheap",
        prompt_tokens=1_000_000,
        output_tokens=1_000_000,
        pricing_config=config,
    )
    expensive, _ = estimate_cost_cents(
        provider="openai",
        model="test-expensive",
        prompt_tokens=1_000_000,
        output_tokens=1_000_000,
        pricing_config=config,
    )

    assert cheap == 3
    assert expensive == 30


@pytest.mark.asyncio
async def test_effective_model_pricing_uses_latest_historical_record(db_session):
    older = datetime(2026, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2026, 5, 1, tzinfo=timezone.utc)
    await record_model_pricing(
        db_session,
        ModelPricing("openai", "test-model", input_token_cents_per_1m=10, output_token_cents_per_1m=20),
        effective_at=older,
    )
    await record_model_pricing(
        db_session,
        ModelPricing("openai", "test-model", input_token_cents_per_1m=30, output_token_cents_per_1m=40),
        effective_at=newer,
    )
    await db_session.commit()

    pricing = await get_effective_model_pricing(
        db_session,
        provider="openai",
        model="test-model",
        at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )

    assert pricing.input_token_cents_per_1m == 30
    assert pricing.output_token_cents_per_1m == 40
