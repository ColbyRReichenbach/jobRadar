from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from backend.celery_app import celery_app
from backend.models import Application, Contact, EmailEvent, ResearchReport
from backend.services.search.documents import SOURCE_APPLICATION, SOURCE_CONTACT, SOURCE_EMAIL, SOURCE_RADAR_REPORT


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def index_search_document_async(source_type: str, source_id: str, user_id: str | None = None) -> bool:
    from backend.database import async_session_factory
    from backend.services.search.indexer import index_record

    source_uuid = uuid.UUID(source_id)
    user_uuid = uuid.UUID(user_id) if user_id else None
    model_map = {
        SOURCE_APPLICATION: Application,
        SOURCE_CONTACT: Contact,
        SOURCE_EMAIL: EmailEvent,
        SOURCE_RADAR_REPORT: ResearchReport,
    }
    model = model_map.get(source_type)
    if model is None:
        raise ValueError(f"Unsupported source type: {source_type}")

    async with async_session_factory() as db:
        stmt = select(model).where(model.id == source_uuid)
        if user_uuid is not None:
            stmt = stmt.where(model.user_id == user_uuid)
        record = (await db.execute(stmt)).scalars().first()
        if record is None:
            return False
        await index_record(db, record)
        await db.commit()
        return True


async def reindex_search_documents_async(user_id: str) -> dict[str, int]:
    from backend.database import async_session_factory
    from backend.services.search.indexer import reindex_user_documents

    async with async_session_factory() as db:
        counts = await reindex_user_documents(db, user_id=uuid.UUID(user_id))
        await db.commit()
        return counts


@celery_app.task(name="backend.tasks.index_search_documents.index_search_document")
def index_search_document(source_type: str, source_id: str, user_id: str | None = None) -> bool:
    return _run_async(index_search_document_async(source_type, source_id, user_id))


@celery_app.task(name="backend.tasks.index_search_documents.reindex_search_documents")
def reindex_search_documents(user_id: str) -> dict[str, int]:
    return _run_async(reindex_search_documents_async(user_id))
