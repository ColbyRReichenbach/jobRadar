"""Search indexing orchestration."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Application, Contact, EmailEvent, ResearchReport, SearchDocument
from backend.services.search.backends.base import SearchResult
from backend.services.search.backends.opensearch import OpenSearchSearchBackend, OpenSearchUnavailableError
from backend.services.search.backends.postgres import PostgresSearchBackend
from backend.services.search.documents import (
    SOURCE_APPLICATION,
    SOURCE_CONTACT,
    SOURCE_EMAIL,
    SOURCE_RADAR_REPORT,
    SUPPORTED_SOURCE_TYPES,
    build_search_document,
)

logger = logging.getLogger(__name__)


def configured_search_backend() -> str:
    return os.getenv("SEARCH_BACKEND", "postgres").strip().lower() or "postgres"


def opensearch_fallback_enabled() -> bool:
    return os.getenv("SEARCH_OPENSEARCH_FALLBACK_TO_POSTGRES", "true").lower() != "false"


def _postgres_backend() -> PostgresSearchBackend:
    return PostgresSearchBackend()


def _opensearch_backend() -> OpenSearchSearchBackend:
    return OpenSearchSearchBackend()


async def index_record(db: AsyncSession, record: Any) -> SearchDocument:
    document = build_search_document(record)
    return await _postgres_backend().index_document(db, document)


async def index_records(db: AsyncSession, records: list[Any]) -> list[SearchDocument]:
    rows = []
    for record in records:
        rows.append(await index_record(db, record))
    return rows


async def delete_indexed_record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
) -> bool:
    return await _postgres_backend().delete_document(
        db,
        user_id=user_id,
        source_type=source_type,
        source_id=source_id,
    )


async def search_user_documents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    source_types: list[str] | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    backend_name = configured_search_backend()
    if backend_name == "opensearch":
        try:
            return await _opensearch_backend().search(
                db,
                user_id=user_id,
                query=query,
                source_types=source_types,
                limit=limit,
            )
        except OpenSearchUnavailableError as exc:
            if not opensearch_fallback_enabled():
                raise
            logger.warning("OpenSearch unavailable; falling back to Postgres search", extra={"reason": str(exc)})

    return await _postgres_backend().search(
        db,
        user_id=user_id,
        query=query,
        source_types=source_types,
        limit=limit,
    )


async def search_backend_health(db: AsyncSession, *, user_id: uuid.UUID | None = None) -> dict[str, Any]:
    backend_name = configured_search_backend()
    postgres_health = await _postgres_backend().healthcheck(db, user_id=user_id)
    if backend_name != "opensearch":
        return postgres_health

    opensearch_health = await _opensearch_backend().healthcheck(db, user_id=user_id)
    return {
        **opensearch_health,
        "fallback_backend": postgres_health,
    }


async def _records_for_source_type(db: AsyncSession, *, user_id: uuid.UUID, source_type: str) -> list[Any]:
    if source_type == SOURCE_APPLICATION:
        return list((await db.execute(select(Application).where(Application.user_id == user_id))).scalars())
    if source_type == SOURCE_CONTACT:
        return list((await db.execute(select(Contact).where(Contact.user_id == user_id))).scalars())
    if source_type == SOURCE_EMAIL:
        return list((await db.execute(select(EmailEvent).where(EmailEvent.user_id == user_id))).scalars())
    if source_type == SOURCE_RADAR_REPORT:
        return list((await db.execute(select(ResearchReport).where(ResearchReport.user_id == user_id))).scalars())
    raise ValueError(f"Unsupported source type: {source_type}")


async def reindex_user_documents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source_types: list[str] | None = None,
) -> dict[str, int]:
    requested = source_types or sorted(SUPPORTED_SOURCE_TYPES)
    counts: dict[str, int] = {}
    for source_type in requested:
        if source_type not in SUPPORTED_SOURCE_TYPES:
            continue
        records = await _records_for_source_type(db, user_id=user_id, source_type=source_type)
        await index_records(db, records)
        counts[source_type] = len(records)
    return counts


async def search_index_metrics(db: AsyncSession, *, user_id: uuid.UUID | None = None) -> dict[str, Any]:
    return await search_backend_health(db, user_id=user_id)
