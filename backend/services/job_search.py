import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
SERPAPI_URL = "https://serpapi.com/search"

GREENHOUSE_TARGETS = {
    "twitch": "twitch",
    "draftkings": "draftkings",
    "captech": "captech",
}
GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"


def job_search_provider_status(query: str) -> dict:
    """Return user-facing search provider availability and scope."""
    query_lower = query.lower().strip()
    greenhouse_targets = [
        company_name
        for company_name in GREENHOUSE_TARGETS
        if company_name in query_lower or not query_lower
    ]
    degraded_reasons: list[str] = []
    if not SERPAPI_KEY:
        degraded_reasons.append("Broad job search is not configured, so external job board results are unavailable.")
    if query_lower and not greenhouse_targets:
        degraded_reasons.append(
            "No configured Greenhouse board matched this company or keyword. Try a broader role search or configure a search provider."
        )

    return {
        "serpapi_configured": bool(SERPAPI_KEY),
        "greenhouse_targets": sorted(GREENHOUSE_TARGETS.keys()),
        "greenhouse_targets_searched": greenhouse_targets,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }


async def search_serpapi(query: str, location: str) -> list[dict]:
    """Search jobs via SerpAPI Google Jobs engine."""
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY not set, skipping SerpAPI search")
        return []

    async def _search():
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                SERPAPI_URL,
                params={
                    "engine": "google_jobs",
                    "q": query,
                    "location": location,
                    "api_key": SERPAPI_KEY,
                },
            )
            resp.raise_for_status()
            return resp.json()

    try:
        data = await with_retry(_search)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (429, 402):
            logger.warning(f"SerpAPI limit hit: {e.response.status_code}")
            return []
        logger.error(f"SerpAPI error: {e}")
        return []
    except Exception as e:
        logger.error(f"SerpAPI request failed: {e}")
        return []

    results = []
    for job in data.get("jobs_results", []):
        results.append({
            "title": job.get("title"),
            "company": job.get("company_name"),
            "location": job.get("location"),
            "source": "serpapi",
            "url": job.get("related_links", [{}])[0].get("link") if job.get("related_links") else None,
            "posted_at": job.get("detected_extensions", {}).get("posted_at"),
            "description": (job.get("description") or "")[:500],
        })
    return results


async def search_greenhouse(company_token: str) -> list[dict]:
    """Search Greenhouse boards API for a target company."""

    async def _search():
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(f"{GREENHOUSE_API}/{company_token}/jobs")
            resp.raise_for_status()
            return resp.json()

    try:
        data = await with_retry(_search)
    except Exception as e:
        logger.error(f"Greenhouse search failed for {company_token}: {e}")
        return []

    results = []
    for job in data.get("jobs", []):
        loc = job.get("location", {}).get("name", "")
        results.append({
            "title": job.get("title"),
            "company": company_token.capitalize(),
            "location": loc,
            "source": "greenhouse",
            "url": job.get("absolute_url"),
            "posted_at": job.get("updated_at"),
            "description": None,
        })
    return results


async def search_jobs(query: str, location: str) -> list[dict]:
    """Combined search: SerpAPI + Greenhouse target companies."""
    all_results = []

    # SerpAPI search
    serpapi_results = await search_serpapi(query, location)
    all_results.extend(serpapi_results)

    # Greenhouse proactive search for target companies
    query_lower = query.lower()
    for company_name, token in GREENHOUSE_TARGETS.items():
        if company_name in query_lower or not query_lower:
            gh_results = await search_greenhouse(token)
            all_results.extend(gh_results)

    return all_results
