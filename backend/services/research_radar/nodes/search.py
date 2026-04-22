from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from backend.services.research_radar.config import DEFAULT_FETCH_USER_AGENT, SEARCH_TIMEOUT_SECONDS
from backend.services.research_radar.schemas import SearchCandidate


def _clean_search_url(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return target[0]
    return url


def _infer_source_type(url: str) -> str:
    lowered = url.lower()
    if "/jobs/" in lowered or "careers" in lowered:
        return "company_careers"
    if "blog" in lowered or "engineering" in lowered:
        return "engineering_blog"
    if "press" in lowered or "news" in lowered:
        return "press"
    if "github.com" in lowered:
        return "github_org"
    return "public_web"


async def search_public_web(query: str, max_results: int) -> list[SearchCandidate]:
    params = {"q": query}
    headers = {"User-Agent": DEFAULT_FETCH_USER_AGENT}
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as client:
        response = await client.get("https://duckduckgo.com/html/", params=params)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[SearchCandidate] = []
    for anchor in soup.select("a.result__a, a[href]"):
        href = anchor.get("href")
        title = anchor.get_text(" ", strip=True)
        if not href or not title:
            continue
        clean_url = _clean_search_url(href)
        if not clean_url.startswith("http"):
            continue
        block = anchor.find_parent("div", class_="result")
        snippet_node = block.select_one(".result__snippet") if block else None
        snippet = snippet_node.get_text(" ", strip=True) if snippet_node else None
        domain = urlparse(clean_url).netloc.lower()
        candidates.append(
            SearchCandidate(
                url=clean_url,
                title=title,
                snippet=snippet,
                source_type=_infer_source_type(clean_url),
                domain=domain,
                published_at=datetime.now(timezone.utc).isoformat(),
                why_selected=f"Matched search query: {query}",
            )
        )
        if len(candidates) >= max_results:
            break
    return candidates


async def run_search_tasks(state):
    tasks = state.get("search_tasks", [])
    semaphore = asyncio.Semaphore(4)

    async def _run(task_payload: dict):
        async with semaphore:
            candidates = await search_public_web(task_payload["query"], task_payload.get("max_results", 5))
            updated = dict(task_payload)
            updated["candidates"] = [candidate.model_dump() for candidate in candidates]
            return updated

    updated_tasks = await asyncio.gather(*[_run(task_payload) for task_payload in tasks]) if tasks else []
    return {"search_tasks": updated_tasks}
