from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from backend.celery_app import celery_app
from backend.services.source_intelligence.url_classifier import extract_urls_from_text


PARSER_VERSION = "source-url-v1"


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def reprocess_source_intelligence_for_user(user_id: uuid.UUID, *, limit: int = 500) -> dict:
    from backend.database import async_session_factory

    async with async_session_factory() as db:
        result = await reprocess_source_intelligence_in_session(db, user_id, limit=limit)
        await db.commit()
        return result


async def reprocess_source_intelligence_in_session(db, user_id: uuid.UUID, *, limit: int = 500) -> dict:
    from backend.models import Application, EmailEvent
    from backend.services.source_intelligence.discovery import process_stored_links_for_source_discovery
    from backend.services.source_intelligence.link_store import store_many_user_application_links, store_user_application_link
    from backend.services.source_intelligence.locks import source_intelligence_lock

    application_count = 0
    email_count = 0
    stored_link_count = 0
    discovery_count = 0

    async with source_intelligence_lock(db, f"source-reprocess:{user_id}:{PARSER_VERSION}") as locked:
        if not locked:
            return {
                "user_id": str(user_id),
                "status": "skipped_locked",
                "applications_processed": 0,
                "emails_processed": 0,
                "links_stored": 0,
                "discovery_events": 0,
            }

        applications = (
            await db.execute(
                select(Application)
                .where(Application.user_id == user_id, Application.job_url.isnot(None))
                .limit(limit)
            )
        ).scalars().all()
        for application in applications:
            if not application.job_url:
                continue
            stored = await store_user_application_link(
                db,
                user_id=user_id,
                raw_url=application.job_url,
                application_id=application.id,
                created_from="historical_application_reprocess",
                parser_version=PARSER_VERSION,
            )
            stored_link_count += 1
            discovery = await process_stored_links_for_source_discovery(
                db,
                user_id=user_id,
                stored_links=[stored],
                discovered_from="historical_application_reprocess",
            )
            discovery_count += len(discovery)
            application_count += 1

        remaining = max(limit - application_count, 0)
        if remaining:
            email_events = (
                await db.execute(
                    select(EmailEvent)
                    .where(EmailEvent.user_id == user_id)
                    .limit(remaining)
                )
            ).scalars().all()
            for event in email_events:
                candidate_urls = _historical_email_urls(event)
                if not candidate_urls:
                    continue
                stored_links = await store_many_user_application_links(
                    db,
                    user_id=user_id,
                    raw_urls=candidate_urls,
                    application_id=event.application_id,
                    email_event_id=event.id,
                    created_from="historical_email_reprocess",
                )
                stored_link_count += len(stored_links)
                discovery = await process_stored_links_for_source_discovery(
                    db,
                    user_id=user_id,
                    stored_links=stored_links,
                    discovered_from="historical_email_reprocess",
                )
                discovery_count += len(discovery)
                email_count += 1

    return {
        "user_id": str(user_id),
        "applications_processed": application_count,
        "emails_processed": email_count,
        "links_stored": stored_link_count,
        "discovery_events": discovery_count,
    }


def _historical_email_urls(event) -> list[str]:
    urls: list[str] = []
    for value in (event.action_url, event.body, event.snippet, event.summary, event.key_sentence):
        urls.extend(extract_urls_from_text(value))
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


@celery_app.task(name="backend.tasks.reprocess_source_intelligence.reprocess_user", bind=True, max_retries=3)
def reprocess_user(self, user_id: str, limit: int = 500) -> dict:
    try:
        return _run_async(reprocess_source_intelligence_for_user(uuid.UUID(user_id), limit=limit))
    except Exception as exc:
        raise self.retry(exc=exc)
