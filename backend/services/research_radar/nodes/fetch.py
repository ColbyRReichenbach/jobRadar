from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from backend.models import ResearchSourceItem
from backend.services.research_radar.config import DEFAULT_FETCH_USER_AGENT, FETCH_TIMEOUT_SECONDS


async def fetch_document(url: str) -> tuple[str, str]:
    headers = {"User-Agent": DEFAULT_FETCH_USER_AGENT}
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    return html[:20000], text[:12000]


async def fetch_documents(state):
    db = state["db"]
    tracker = state["tracker"]
    max_sources = tracker.get("max_sources_per_run", 20)
    source_payloads: list[dict] = []

    for task in state.get("search_tasks", []):
        for candidate in task.get("candidates", []):
            if len(source_payloads) >= max_sources:
                break
            raw_html, raw_text = await fetch_document(candidate["url"])
            content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            existing = (
                await db.execute(
                    select(ResearchSourceItem).where(
                        ResearchSourceItem.user_id == state["user_id"],
                        ResearchSourceItem.source_url == candidate["url"],
                        ResearchSourceItem.content_hash == content_hash,
                    )
                )
            ).scalars().first()
            if existing:
                source_payloads.append(
                    {
                        "source_item_id": existing.id,
                        "source_url": existing.source_url,
                        "title": existing.title,
                        "source_type": existing.source_type,
                        "domain": urlparse(existing.source_url).netloc.lower() if existing.source_url else None,
                        "published_at": existing.published_at.isoformat() if existing.published_at else None,
                        "raw_text": existing.raw_text,
                        "company_name": task.get("company_hint"),
                        "role_title": task.get("role_hint"),
                    }
                )
                continue

            item = ResearchSourceItem(
                run_id=state["run_id"],
                user_id=state["user_id"],
                profile_id=state["profile_id"],
                source_type=candidate["source_type"],
                source_name="public_web_search",
                source_url=candidate["url"],
                title=candidate["title"],
                raw_text=raw_text,
                raw_json={"html_excerpt": raw_html[:5000], "search_candidate": candidate},
                published_at=datetime.now(timezone.utc),
                content_hash=content_hash,
            )
            db.add(item)
            await db.flush()
            source_payloads.append(
                {
                    "source_item_id": item.id,
                    "source_url": item.source_url,
                    "title": item.title,
                    "source_type": item.source_type,
                    "domain": urlparse(item.source_url).netloc.lower() if item.source_url else None,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "raw_text": item.raw_text,
                    "company_name": task.get("company_hint"),
                    "role_title": task.get("role_hint"),
                }
            )
        if len(source_payloads) >= max_sources:
            break

    await db.flush()
    return {"source_items": source_payloads}
