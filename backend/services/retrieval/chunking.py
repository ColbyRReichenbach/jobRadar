"""Deterministic document chunking for local lexical retrieval."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


TOKEN_RE = re.compile(r"\S+")


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    content: str
    token_count: int
    char_start: int
    char_end: int
    content_hash: str


def normalize_chunk_text(text: str | None) -> str:
    return " ".join((text or "").split())


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def chunk_text(
    text: str | None,
    *,
    max_tokens: int = 120,
    overlap_tokens: int = 24,
) -> list[TextChunk]:
    """Split text into deterministic overlapping chunks.

    The implementation is intentionally simple and dependency-free. It uses
    whitespace token positions in normalized text so local tests and production
    workers produce the same chunk boundaries.
    """
    normalized = normalize_chunk_text(text)
    if not normalized:
        return []
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    spans = [(match.start(), match.end()) for match in TOKEN_RE.finditer(normalized)]
    chunks: list[TextChunk] = []
    step = max_tokens - overlap_tokens
    start_token = 0
    while start_token < len(spans):
        end_token = min(start_token + max_tokens, len(spans))
        char_start = spans[start_token][0]
        char_end = spans[end_token - 1][1]
        content = normalized[char_start:char_end]
        chunks.append(
            TextChunk(
                chunk_index=len(chunks),
                content=content,
                token_count=end_token - start_token,
                char_start=char_start,
                char_end=char_end,
                content_hash=_hash_text(content),
            )
        )
        if end_token >= len(spans):
            break
        start_token += step
    return chunks
