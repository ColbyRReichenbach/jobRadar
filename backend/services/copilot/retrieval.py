"""Copilot retrieval over user-scoped search documents."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.copilot.config import max_context_docs, max_context_tokens
from backend.services.copilot.schemas import CopilotCitation
from backend.services.search.indexer import search_user_documents


def _rough_token_count(text: str) -> int:
    return max(1, len(text) // 4)


async def retrieve_copilot_context(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    source_types: list[str] | None = None,
) -> list[CopilotCitation]:
    results = await search_user_documents(
        db,
        user_id=user_id,
        query=query,
        source_types=source_types,
        limit=max_context_docs(),
    )
    citations: list[CopilotCitation] = []
    token_budget = max_context_tokens()
    used_tokens = 0
    for result in results:
        text = " ".join(part for part in [result.title, result.subtitle, result.snippet] if part)
        tokens = _rough_token_count(text)
        if used_tokens + tokens > token_budget:
            break
        used_tokens += tokens
        citations.append(
            CopilotCitation(
                document_id=result.document_id,
                source_type=result.source_type,
                source_id=result.source_id,
                title=result.title,
                snippet=result.snippet,
            )
        )
    return citations
