"""Search backend contracts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import SearchDocument
from backend.services.search.documents import SearchDocumentInput


@dataclass(frozen=True)
class SearchResult:
    document_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    title: str
    subtitle: str | None
    snippet: str | None
    score: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["document_id"] = str(self.document_id)
        payload["source_id"] = str(self.source_id)
        return payload


class SearchBackend(Protocol):
    name: str

    async def index_document(self, db: AsyncSession, document: SearchDocumentInput) -> SearchDocument:
        ...

    async def delete_document(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        source_type: str,
        source_id: uuid.UUID,
    ) -> bool:
        ...

    async def search(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        query: str,
        source_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        ...

    async def healthcheck(self, db: AsyncSession, *, user_id: uuid.UUID | None = None) -> dict[str, Any]:
        ...
