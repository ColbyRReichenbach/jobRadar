"""Small statistics helpers for AI experiment reports."""

from __future__ import annotations

import math


def wilson_interval(successes: int, total: int, z: float = 1.96) -> dict[str, float]:
    if total <= 0:
        return {"low": 0.0, "high": 0.0}
    p_hat = successes / total
    denominator = 1 + z**2 / total
    centre = p_hat + z**2 / (2 * total)
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)
    return {
        "low": round(max(0.0, (centre - margin) / denominator), 4),
        "high": round(min(1.0, (centre + margin) / denominator), 4),
    }


def mean_delta(candidate: float, control: float) -> float:
    return round(candidate - control, 4)


def minimum_detectable_effect_warning(sample_size: int, minimum_sample_size: int) -> str | None:
    if sample_size >= minimum_sample_size:
        return None
    return f"Underpowered: {sample_size} samples is below configured minimum {minimum_sample_size}."
