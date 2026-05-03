import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
HUNTER_BASE_URL = "https://api.hunter.io/v2"

TARGET_DEPARTMENTS = {"engineering", "data", "analytics"}
TARGET_SENIORITIES = {"senior", "manager", "director"}


async def find_contacts(domain: str, company: str) -> list[dict]:
    """Search Hunter.io for contacts at the given domain.

    Filters by department (engineering/data/analytics) and seniority
    (senior/manager/director). Returns [] on rate limit or monthly limit.
    """
    if not HUNTER_API_KEY:
        logger.warning("HUNTER_API_KEY not set, returning empty contacts")
        return []

    async def _search():
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                f"{HUNTER_BASE_URL}/domain-search",
                params={
                    "domain": domain,
                    "api_key": HUNTER_API_KEY,
                    "limit": 20,
                },
            )
            resp.raise_for_status()
            return resp.json()

    try:
        data = await with_retry(_search)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("Hunter.io rate limited, returning empty")
            return []
        if e.response.status_code == 402:
            logger.warning("Hunter.io monthly limit reached, returning empty")
            return []
        logger.error(f"Hunter.io error: {e}")
        return []
    except Exception as e:
        logger.error(f"Hunter.io request failed: {e}")
        return []

    emails = data.get("data", {}).get("emails", [])
    filtered = []
    for email_entry in emails:
        dept = (email_entry.get("department") or "").lower()
        seniority = (email_entry.get("seniority") or "").lower()

        dept_match = any(d in dept for d in TARGET_DEPARTMENTS)
        seniority_match = any(s in seniority for s in TARGET_SENIORITIES)

        if dept_match or seniority_match:
            filtered.append({
                "name": f"{email_entry.get('first_name', '')} {email_entry.get('last_name', '')}".strip(),
                "title": email_entry.get("position", ""),
                "email": email_entry.get("value", ""),
                "confidence_score": (email_entry.get("confidence", 0)) / 100.0,
                "source": "hunter",
                "department": email_entry.get("department"),
                "seniority": email_entry.get("seniority"),
            })

    return filtered


def generate_linkedin_search_url(company: str, school: str | None = None) -> str:
    """Generate alumni LinkedIn search URL for the given company.

    Uses the user's school from their profile if available,
    otherwise falls back to a generic company search.
    """
    if school:
        keywords = f"{school} {company}"
    else:
        keywords = company
    encoded = keywords.replace(" ", "+")
    return f"https://www.linkedin.com/search/results/people/?keywords={encoded}"
