from __future__ import annotations

from urllib.parse import urlparse

from backend.services.research_radar.config import TRUSTED_DOMAIN_BONUS


def _domain_bonus(domain: str | None) -> float:
    if not domain:
        return 0.0
    lowered = domain.lower()
    for token, bonus in TRUSTED_DOMAIN_BONUS.items():
        if token in lowered:
            return bonus
    return 0.25


def _evidence_key(item: dict) -> str:
    url = item.get("url") or ""
    parsed = urlparse(url)
    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return "|".join(
        [
            (item.get("company_name") or "").strip().lower(),
            (item.get("role_title") or "").strip().lower(),
            (item.get("evidence_type") or "").strip().lower(),
            canonical_url.lower(),
        ]
    )


async def dedupe_and_rank_evidence(state):
    deduped: dict[str, dict] = {}
    for item in state.get("evidence_items", []):
        key = _evidence_key(item)
        candidate = dict(item)
        candidate["relevance_score"] = round(min(1.0, item.get("relevance_score", 0.5) + _domain_bonus(item.get("domain")) / 2), 2)
        candidate["novelty_score"] = round(item.get("novelty_score", 0.5), 2)
        candidate["_key"] = key
        existing = deduped.get(key)
        if not existing or candidate["relevance_score"] > existing["relevance_score"]:
            deduped[key] = candidate

    ranked = sorted(
        deduped.values(),
        key=lambda item: (item.get("relevance_score", 0.0), item.get("confidence", 0.0), item.get("novelty_score", 0.0)),
        reverse=True,
    )
    return {"evidence_items": ranked}
