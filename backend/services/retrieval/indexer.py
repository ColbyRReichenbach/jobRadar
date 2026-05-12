"""User knowledge document indexing built on existing SearchDocument inputs."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import DocumentChunk, SearchDocument, UserKnowledgeDocument
from backend.services.search.documents import SearchDocumentInput, build_search_document
from backend.services.retrieval.chunking import chunk_text, normalize_chunk_text


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _knowledge_content(document: SearchDocumentInput) -> str:
    keyword_text = " ".join(document.keywords or [])
    return normalize_chunk_text(
        " ".join(
            part
            for part in [
                document.title,
                document.subtitle or "",
                document.body or "",
                keyword_text,
            ]
            if part
        )
    )


async def index_knowledge_document(
    db: AsyncSession,
    document: SearchDocumentInput,
    *,
    search_document: SearchDocument | None = None,
    max_chunk_tokens: int = 120,
    chunk_overlap_tokens: int = 24,
) -> UserKnowledgeDocument:
    """Upsert a user knowledge document and replace its deterministic chunks."""
    content = _knowledge_content(document)
    chunks = chunk_text(content, max_tokens=max_chunk_tokens, overlap_tokens=chunk_overlap_tokens)
    existing = (
        await db.execute(
            select(UserKnowledgeDocument).where(
                UserKnowledgeDocument.user_id == document.user_id,
                UserKnowledgeDocument.source_type == document.source_type,
                UserKnowledgeDocument.source_id == document.source_id,
            )
        )
    ).scalar_one_or_none()

    row = existing or UserKnowledgeDocument(
        user_id=document.user_id,
        source_type=document.source_type,
        source_id=document.source_id,
        title=document.title,
        content=content,
        content_hash=document.content_hash,
    )
    row.search_document_id = search_document.id if search_document else None
    row.title = document.title
    row.subtitle = document.subtitle
    row.content = content
    row.content_hash = document.content_hash
    row.metadata_json = document.metadata
    row.source_updated_at = document.source_updated_at
    row.indexed_at = _utcnow()
    if existing is None:
        db.add(row)
        await db.flush()

    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == row.id))
    for item in chunks:
        db.add(
            DocumentChunk(
                user_id=document.user_id,
                document_id=row.id,
                source_type=document.source_type,
                source_id=document.source_id,
                chunk_index=item.chunk_index,
                content=item.content,
                token_count=item.token_count,
                char_start=item.char_start,
                char_end=item.char_end,
                content_hash=item.content_hash,
                metadata_json={
                    "title": document.title,
                    "subtitle": document.subtitle,
                    "search_document_id": str(search_document.id) if search_document else None,
                },
            )
        )
    await db.flush()
    return row


async def index_knowledge_record(
    db: AsyncSession,
    record,
    *,
    search_document: SearchDocument | None = None,
) -> UserKnowledgeDocument:
    return await index_knowledge_document(
        db,
        build_search_document(record),
        search_document=search_document,
    )


async def delete_knowledge_document(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        delete(UserKnowledgeDocument).where(
            UserKnowledgeDocument.user_id == user_id,
            UserKnowledgeDocument.source_type == source_type,
            UserKnowledgeDocument.source_id == source_id,
        )
    )
    await db.flush()
    return bool(result.rowcount)
