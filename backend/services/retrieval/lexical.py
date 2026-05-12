"""Portable lexical retrieval over document chunks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
import time
import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import DocumentChunk, RetrievalTrace, UserKnowledgeDocument
from backend.services.search.documents import SUPPORTED_SOURCE_TYPES


RETRIEVER_VERSION = "lexical_chunks_v1"
TERM_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    chunk_index: int
    title: str
    snippet: str
    score: float
    content_hash: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["chunk_id"] = str(self.chunk_id)
        payload["document_id"] = str(self.document_id)
        payload["source_id"] = str(self.source_id)
        return payload


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_query(query: str | None) -> str:
    return " ".join((query or "").lower().split())


def query_terms(query: str | None) -> list[str]:
    return [match.group(0) for match in TERM_RE.finditer(normalize_query(query)) if len(match.group(0)) >= 2][:12]


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _score(content: str, title: str, terms: list[str]) -> float:
    lowered_content = content.lower()
    lowered_title = title.lower()
    score = 0.0
    for term in terms:
        content_hits = lowered_content.count(term)
        if content_hits:
            score += content_hits
        if term in lowered_title:
            score += 3
    if terms and all(term in lowered_content or term in lowered_title for term in terms):
        score += 5
    return score


def _snippet(content: str, terms: list[str], *, limit: int = 260) -> str:
    lowered = content.lower()
    match_index = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(match_index - 60, 0)
    snippet = " ".join(content[start : start + limit].split())
    if start > 0:
        snippet = f"...{snippet}"
    if start + limit < len(content):
        snippet = f"{snippet}..."
    return snippet


SUPPORTED_FILTER_KEYS = {
    "source_id",
    "source_ids",
    "document_id",
    "document_ids",
    "chunk_index",
    "chunk_indices",
}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _uuid_values(filters: dict[str, Any], single_key: str, list_key: str) -> tuple[list[uuid.UUID], str | None]:
    raw_values: list[Any] = []
    if single_key in filters:
        raw_values.extend(_as_list(filters.get(single_key)))
    if list_key in filters:
        raw_values.extend(_as_list(filters.get(list_key)))
    if not raw_values:
        return [], None
    values: list[uuid.UUID] = []
    for value in raw_values:
        try:
            values.append(uuid.UUID(str(value)))
        except (TypeError, ValueError):
            return [], "invalid_filters"
    return values, None


def _int_values(filters: dict[str, Any], single_key: str, list_key: str) -> tuple[list[int], str | None]:
    raw_values: list[Any] = []
    if single_key in filters:
        raw_values.extend(_as_list(filters.get(single_key)))
    if list_key in filters:
        raw_values.extend(_as_list(filters.get(list_key)))
    if not raw_values:
        return [], None
    values: list[int] = []
    for value in raw_values:
        try:
            values.append(int(value))
        except (TypeError, ValueError):
            return [], "invalid_filters"
    return values, None


def _filter_conditions(filters: dict[str, Any] | None) -> tuple[list[Any], str | None]:
    if not filters:
        return [], None
    unsupported = sorted(set(filters) - SUPPORTED_FILTER_KEYS)
    if unsupported:
        return [], "unsupported_filters"

    conditions = []
    source_ids, status = _uuid_values(filters, "source_id", "source_ids")
    if status:
        return [], status
    if "source_id" in filters or "source_ids" in filters:
        if not source_ids:
            return [], "empty_filters"
        conditions.append(DocumentChunk.source_id.in_(source_ids))

    document_ids, status = _uuid_values(filters, "document_id", "document_ids")
    if status:
        return [], status
    if "document_id" in filters or "document_ids" in filters:
        if not document_ids:
            return [], "empty_filters"
        conditions.append(DocumentChunk.document_id.in_(document_ids))

    chunk_indices, status = _int_values(filters, "chunk_index", "chunk_indices")
    if status:
        return [], status
    if "chunk_index" in filters or "chunk_indices" in filters:
        if not chunk_indices:
            return [], "empty_filters"
        conditions.append(DocumentChunk.chunk_index.in_(chunk_indices))

    return conditions, None


async def retrieve_document_chunks(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    source_types: list[str] | None = None,
    limit: int = 8,
    surface: str = "retrieval",
    filters: dict[str, Any] | None = None,
) -> list[RetrievedChunk]:
    started = time.perf_counter()
    normalized_query = normalize_query(query)
    terms = query_terms(query)
    allowed_source_types = None
    if source_types:
        allowed_source_types = [item for item in source_types if item in SUPPORTED_SOURCE_TYPES]
        if not allowed_source_types:
            await _record_trace(
                db,
                user_id=user_id,
                surface=surface,
                query=query,
                normalized_query=normalized_query,
                source_types=[],
                filters=filters,
                candidate_count=0,
                results=[],
                latency_ms=(time.perf_counter() - started) * 1000,
                status="no_allowed_source_types",
            )
            return []
    if not terms:
        await _record_trace(
            db,
            user_id=user_id,
            surface=surface,
            query=query,
            normalized_query=normalized_query,
            source_types=allowed_source_types,
            filters=filters,
            candidate_count=0,
            results=[],
            latency_ms=(time.perf_counter() - started) * 1000,
            status="empty_query",
        )
        return []

    filter_conditions, filter_status = _filter_conditions(filters)
    if filter_status:
        await _record_trace(
            db,
            user_id=user_id,
            surface=surface,
            query=query,
            normalized_query=normalized_query,
            source_types=allowed_source_types,
            filters=filters,
            candidate_count=0,
            results=[],
            latency_ms=(time.perf_counter() - started) * 1000,
            status=filter_status,
        )
        return []

    query_filters = [DocumentChunk.user_id == user_id]
    if allowed_source_types:
        query_filters.append(DocumentChunk.source_type.in_(allowed_source_types))
    query_filters.extend(filter_conditions)
    lower_content = func.lower(DocumentChunk.content)
    query_filters.append(or_(*(lower_content.like(_like(term), escape="\\") for term in terms)))

    stmt = (
        select(DocumentChunk, UserKnowledgeDocument)
        .join(UserKnowledgeDocument, DocumentChunk.document_id == UserKnowledgeDocument.id)
        .where(*query_filters)
        .order_by(DocumentChunk.created_at.desc())
        .limit(max(limit * 8, 50))
    )
    rows = list((await db.execute(stmt)).all())
    scored = sorted(
        ((chunk, document, _score(chunk.content, document.title, terms)) for chunk, document in rows),
        key=lambda item: (item[2], item[0].created_at),
        reverse=True,
    )
    results = [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=document.id,
            source_type=chunk.source_type,
            source_id=chunk.source_id,
            chunk_index=chunk.chunk_index,
            title=document.title,
            snippet=_snippet(chunk.content, terms),
            score=score,
            content_hash=chunk.content_hash,
            metadata={
                **(document.metadata_json or {}),
                "chunk_index": chunk.chunk_index,
                "token_count": chunk.token_count,
            },
        )
        for chunk, document, score in scored[:limit]
    ]
    await _record_trace(
        db,
        user_id=user_id,
        surface=surface,
        query=query,
        normalized_query=normalized_query,
        source_types=allowed_source_types,
        filters=filters,
        candidate_count=len(rows),
        results=results,
        latency_ms=(time.perf_counter() - started) * 1000,
        status="ok",
    )
    return results


async def _record_trace(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    surface: str,
    query: str,
    normalized_query: str,
    source_types: list[str] | None,
    filters: dict[str, Any] | None,
    candidate_count: int,
    results: list[RetrievedChunk],
    latency_ms: float,
    status: str,
) -> RetrievalTrace:
    trace = RetrievalTrace(
        user_id=user_id,
        surface=surface,
        query=query,
        normalized_query=normalized_query,
        retriever_version=RETRIEVER_VERSION,
        source_types=source_types,
        filters_json=filters,
        candidate_count=candidate_count,
        returned_count=len(results),
        selected_chunk_ids=[str(item.chunk_id) for item in results],
        scores_json=[
            {
                "chunk_id": str(item.chunk_id),
                "document_id": str(item.document_id),
                "source_type": item.source_type,
                "source_id": str(item.source_id),
                "chunk_index": item.chunk_index,
                "title": item.title,
                "snippet": item.snippet,
                "content_hash": item.content_hash,
                "score": item.score,
            }
            for item in results
        ],
        latency_ms=round(latency_ms, 3),
        status=status,
        created_at=_utcnow(),
    )
    db.add(trace)
    await db.flush()
    return trace
