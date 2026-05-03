"""Optional OpenSearch adapter placeholder.

The project can select this backend with `SEARCH_BACKEND=opensearch`, but CI
and local development fall back to Postgres unless an OpenSearch URL is
configured and a concrete client is added.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import SearchDocument
from backend.services.search.backends.base import SearchResult
from backend.services.search.documents import SearchDocumentInput


class OpenSearchUnavailableError(RuntimeError):
    pass


class OpenSearchSearchBackend:
    name = "opensearch"

    def __init__(self, *, url: str | None = None) -> None:
        self.url = url or os.getenv("SEARCH_OPENSEARCH_URL") or os.getenv("OPENSEARCH_URL")

    def _ensure_available(self) -> None:
        if not self.url:
            raise OpenSearchUnavailableError("SEARCH_OPENSEARCH_URL is not configured")

    async def index_document(self, db: AsyncSession, document: SearchDocumentInput) -> SearchDocument:
        self._ensure_available()
        raise OpenSearchUnavailableError("OpenSearch indexing client is not configured")

    async def delete_document(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
    ) -> bool:
        self._ensure_available()
        raise OpenSearchUnavailableError("OpenSearch delete client is not configured")

    async def search(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        query: str,
        source_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        self._ensure_available()
        raise OpenSearchUnavailableError("OpenSearch query client is not configured")

    async def healthcheck(self, db: AsyncSession, *, user_id: uuid.UUID | None = None) -> dict[str, Any]:
        if not self.url:
            return {
                "backend": self.name,
                "status": "unavailable",
                "fallback_available": True,
                "reason": "SEARCH_OPENSEARCH_URL is not configured",
            }
        return {
            "backend": self.name,
            "status": "unavailable",
            "fallback_available": True,
            "reason": "OpenSearch client is not configured",
        }
