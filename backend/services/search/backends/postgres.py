"""Postgres-compatible search backend.

The implementation intentionally uses portable SQL LIKE matching so local
SQLite tests and CI do not require Postgres extensions or OpenSearch.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import SearchDocument
from backend.services.search.backends.base import SearchResult
from backend.services.search.documents import SearchDocumentInput, SUPPORTED_SOURCE_TYPES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _terms(query: str) -> list[str]:
    return [part.lower() for part in query.split() if len(part.strip()) >= 2][:8]


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _snippet(text: str | None, terms: list[str], limit: int = 180) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    match_index = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(match_index - 50, 0)
    snippet = " ".join(text[start : start + limit].split())
    if start > 0:
        snippet = f"...{snippet}"
    if start + limit < len(text):
        snippet = f"{snippet}..."
    return snippet


def _score(document: SearchDocument, terms: list[str]) -> float:
    title = (document.title or "").lower()
    subtitle = (document.subtitle or "").lower()
    body = (document.body or "").lower()
    search_text = (document.search_text or "").lower()

    score = 0.0
    for term in terms:
        if term in title:
            score += 5
        if term in subtitle:
            score += 2
        if term in body:
            score += 1
    if terms and all(term in search_text for term in terms):
        score += 4
    return score


class PostgresSearchBackend:
    name = "postgres"

    async def index_document(self, db: AsyncSession, document: SearchDocumentInput) -> SearchDocument:
        existing = (
            await db.execute(
                select(SearchDocument).where(
                    SearchDocument.user_id == document.user_id,
                    SearchDocument.source_type == document.source_type,
                    SearchDocument.source_id == document.source_id,
                )
            )
        ).scalars().first()
        row = existing or SearchDocument(
            user_id=document.user_id,
            source_type=document.source_type,
            source_id=document.source_id,
            title=document.title,
            search_text=document.search_text,
            content_hash=document.content_hash,
        )
        row.title = document.title
        row.subtitle = document.subtitle
        row.body = document.body
        row.keywords = document.keywords
        row.metadata_json = document.metadata
        row.search_text = document.search_text
        row.content_hash = document.content_hash
        row.source_updated_at = document.source_updated_at
        row.indexed_at = _utcnow()
        if existing is None:
            db.add(row)
        await db.flush()
        return row

    async def delete_document(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
    ) -> bool:
        result = await db.execute(
            delete(SearchDocument).where(
                SearchDocument.user_id == user_id,
                SearchDocument.source_type == source_type,
                SearchDocument.source_id == source_id,
            )
        )
        await db.flush()
        return bool(result.rowcount)

    async def search(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        query: str,
        source_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        terms = _terms(query)
        if not terms:
            return []

        filters = [SearchDocument.user_id == user_id]
        if source_types:
            allowed = [item for item in source_types if item in SUPPORTED_SOURCE_TYPES]
            if not allowed:
                return []
            filters.append(SearchDocument.source_type.in_(allowed))

        lower_text = func.lower(SearchDocument.search_text)
        filters.append(or_(*(lower_text.like(_like(term), escape="\\") for term in terms)))
        stmt = select(SearchDocument).where(*filters).order_by(SearchDocument.indexed_at.desc()).limit(max(limit * 5, 50))
        rows = list((await db.execute(stmt)).scalars())

        scored = sorted(
            ((row, _score(row, terms)) for row in rows),
            key=lambda item: (item[1], item[0].indexed_at),
            reverse=True,
        )
        results: list[SearchResult] = []
        for row, score in scored[:limit]:
            results.append(
                SearchResult(
                    document_id=row.id,
                    source_type=row.source_type,
                    source_id=row.source_id,
                    title=row.title,
                    subtitle=row.subtitle,
                    snippet=_snippet(row.body or row.search_text, terms),
                    score=score,
                    metadata=row.metadata_json or {},
                )
            )
        return results

    async def healthcheck(self, db: AsyncSession, *, user_id: uuid.UUID | None = None) -> dict[str, Any]:
        filters = []
        if user_id is not None:
            filters.append(SearchDocument.user_id == user_id)
        total = (await db.execute(select(func.count(SearchDocument.id)).where(*filters))).scalar_one()
        stale_cutoff = _utcnow() - timedelta(days=7)
        stale_filters = [
            *filters,
            SearchDocument.source_updated_at.isnot(None),
            SearchDocument.indexed_at < SearchDocument.source_updated_at,
            SearchDocument.indexed_at < stale_cutoff,
        ]
        stale = (await db.execute(select(func.count(SearchDocument.id)).where(*stale_filters))).scalar_one()
        return {
            "backend": self.name,
            "status": "ok",
            "document_count": int(total or 0),
            "stale_document_count": int(stale or 0),
        }
