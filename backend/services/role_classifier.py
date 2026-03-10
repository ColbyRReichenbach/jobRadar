"""Role classifier — maps job titles to umbrella categories via keyword matching."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import RoleUmbrella

_umbrella_cache: list | None = None


async def _load_umbrellas(db: AsyncSession) -> list[dict]:
    global _umbrella_cache
    if _umbrella_cache is not None:
        return _umbrella_cache
    result = await db.execute(select(RoleUmbrella))
    umbrellas = result.scalars().all()
    _umbrella_cache = [
        {"id": u.id, "name": u.name, "aliases": u.aliases or []}
        for u in umbrellas
    ]
    return _umbrella_cache


async def classify_role(db: AsyncSession, title: str, description: str = "") -> dict:
    """Classify a role title into an umbrella category.

    Returns {"umbrella_id": uuid|None, "umbrella_name": str|None, "confidence": float}
    """
    umbrellas = await _load_umbrellas(db)
    if not umbrellas:
        return {"umbrella_id": None, "umbrella_name": None, "confidence": 0.0}

    title_lower = title.lower().strip()

    # Exact name match
    for u in umbrellas:
        if u["name"].lower() == title_lower:
            return {"umbrella_id": u["id"], "umbrella_name": u["name"], "confidence": 1.0}

    # Alias exact match
    for u in umbrellas:
        for alias in u["aliases"]:
            if alias.lower() == title_lower:
                return {"umbrella_id": u["id"], "umbrella_name": u["name"], "confidence": 0.95}

    # Substring match (umbrella name or alias contained in title, or vice versa)
    best = None
    best_score = 0
    for u in umbrellas:
        all_names = [u["name"].lower()] + [a.lower() for a in u["aliases"]]
        for name in all_names:
            if name in title_lower or title_lower in name:
                score = len(name) / max(len(title_lower), 1)
                if score > best_score:
                    best = u
                    best_score = score

    if best and best_score > 0.3:
        return {"umbrella_id": best["id"], "umbrella_name": best["name"], "confidence": min(best_score, 0.85)}

    return {"umbrella_id": None, "umbrella_name": None, "confidence": 0.0}


def clear_cache():
    """Clear the umbrella cache (useful for tests)."""
    global _umbrella_cache
    _umbrella_cache = None
