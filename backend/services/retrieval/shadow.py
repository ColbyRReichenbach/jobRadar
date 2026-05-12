"""Opt-in retrieval shadow tracing for non-promoted retrievers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import RetrievalTrace
from backend.services.retrieval.lexical import RETRIEVER_VERSION as CHUNK_RETRIEVER_VERSION
from backend.services.retrieval.lexical import normalize_query, query_terms, retrieve_document_chunks
from backend.services.search.backends.base import SearchResult
from backend.services.search.documents import SUPPORTED_SOURCE_TYPES
from backend.services.search.indexer import search_user_documents


SOURCE_RETRIEVER_VERSION = "source_search_documents_v1"
DEFAULT_SHADOW_LIMIT = 8


@dataclass(frozen=True)
class RetrievalShadowComparison:
    surface: str
    query: str
    source_trace_id: uuid.UUID
    chunk_trace_id: uuid.UUID | None
    source_retriever_version: str
    chunk_retriever_version: str
    source_returned_count: int
    chunk_returned_count: int

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_trace_id"] = str(self.source_trace_id)
        payload["chunk_trace_id"] = str(self.chunk_trace_id) if self.chunk_trace_id else None
        return payload


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _surface_env_name(surface: str) -> str:
    safe_surface = "".join(char if char.isalnum() else "_" for char in surface).upper()
    return f"{safe_surface}_RETRIEVAL_SHADOW_ENABLED"


def retrieval_shadow_enabled(surface: str) -> bool:
    """Return whether shadow tracing is explicitly enabled for a surface."""
    return _env_enabled("RETRIEVAL_SHADOW_ENABLED") or _env_enabled(_surface_env_name(surface))


def _shadow_surface(surface: str) -> str:
    return surface if surface.endswith("_shadow") else f"{surface}_shadow"


def _allowed_source_types(source_types: list[str] | None) -> list[str] | None:
    if not source_types:
        return None
    return [item for item in source_types if item in SUPPORTED_SOURCE_TYPES]


def _source_trace_status(query: str, source_types: list[str] | None) -> str:
    if not query_terms(query):
        return "empty_query"
    if source_types and not _allowed_source_types(source_types):
        return "no_allowed_source_types"
    return "ok"


def _source_scores(results: list[SearchResult]) -> list[dict[str, Any]]:
    return [
        {
            "rank": index,
            "document_id": str(result.document_id),
            "source_type": result.source_type,
            "source_id": str(result.source_id),
            "title": result.title,
            "snippet": result.snippet,
            "score": result.score,
        }
        for index, result in enumerate(results, start=1)
    ]


async def _record_source_trace(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    surface: str,
    query: str,
    source_types: list[str] | None,
    results: list[SearchResult],
    latency_ms: float,
    status: str,
) -> RetrievalTrace:
    trace = RetrievalTrace(
        user_id=user_id,
        surface=surface,
        query=query,
        normalized_query=normalize_query(query),
        retriever_version=SOURCE_RETRIEVER_VERSION,
        source_types=_allowed_source_types(source_types),
        filters_json=None,
        candidate_count=len(results),
        returned_count=len(results),
        selected_chunk_ids=[],
        scores_json=_source_scores(results),
        latency_ms=round(latency_ms, 3),
        status=status,
        created_at=_utcnow(),
    )
    db.add(trace)
    await db.flush()
    return trace


async def _latest_chunk_trace(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    surface: str,
    query: str,
) -> RetrievalTrace | None:
    return (
        await db.execute(
            select(RetrievalTrace)
            .where(
                RetrievalTrace.user_id == user_id,
                RetrievalTrace.surface == surface,
                RetrievalTrace.normalized_query == normalize_query(query),
                RetrievalTrace.retriever_version == CHUNK_RETRIEVER_VERSION,
            )
            .order_by(RetrievalTrace.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def run_retrieval_shadow_comparison(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    surface: str,
    source_types: list[str] | None = None,
    limit: int = DEFAULT_SHADOW_LIMIT,
    source_results: list[SearchResult] | None = None,
) -> RetrievalShadowComparison:
    """Run source and chunk retrieval side by side and persist comparable traces.

    This function is intentionally observational: callers keep using their
    existing source-level retrieval results for product behavior.
    """
    trace_surface = _shadow_surface(surface)
    status = _source_trace_status(query, source_types)
    started = time.perf_counter()
    if source_results is None:
        source_results = await search_user_documents(
            db,
            user_id=user_id,
            query=query,
            source_types=source_types,
            limit=limit,
        )
    source_latency_ms = (time.perf_counter() - started) * 1000
    source_trace = await _record_source_trace(
        db,
        user_id=user_id,
        surface=trace_surface,
        query=query,
        source_types=source_types,
        results=source_results,
        latency_ms=source_latency_ms,
        status=status,
    )

    chunks = await retrieve_document_chunks(
        db,
        user_id=user_id,
        query=query,
        source_types=source_types,
        limit=limit,
        surface=trace_surface,
    )
    chunk_trace = await _latest_chunk_trace(
        db,
        user_id=user_id,
        surface=trace_surface,
        query=query,
    )
    return RetrievalShadowComparison(
        surface=trace_surface,
        query=query,
        source_trace_id=source_trace.id,
        chunk_trace_id=chunk_trace.id if chunk_trace else None,
        source_retriever_version=SOURCE_RETRIEVER_VERSION,
        chunk_retriever_version=CHUNK_RETRIEVER_VERSION,
        source_returned_count=len(source_results),
        chunk_returned_count=len(chunks),
    )
