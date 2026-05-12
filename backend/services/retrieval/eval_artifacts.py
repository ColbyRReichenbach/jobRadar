"""Local retrieval eval artifact generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.retrieval.chunking import chunk_text
from backend.services.retrieval.lexical import RETRIEVER_VERSION, query_terms


@dataclass(frozen=True)
class LocalEvalDocument:
    key: str
    source_type: str
    title: str
    content: str


@dataclass(frozen=True)
class LocalEvalQuery:
    id: str
    query: str
    expected_document_keys: list[str]


LOCAL_DOCUMENTS = [
    LocalEvalDocument(
        key="application:tracebank-assistant-search",
        source_type="application",
        title="TraceBank Assistant Search Data Scientist",
        content="Build assistant search quality models, lexical retrieval, and NLP evaluation workflows.",
    ),
    LocalEvalDocument(
        key="email:interview-assistant-search",
        source_type="email",
        title="Assistant search interview",
        content="Interview invitation for the assistant search data science role with TraceBank.",
    ),
    LocalEvalDocument(
        key="radar_report:platform-radar",
        source_type="radar_report",
        title="Platform hiring radar",
        content="Radar found new platform engineering and NLP hiring signals in developer tools.",
    ),
]

LOCAL_QUERIES = [
    LocalEvalQuery(
        id="q_assistant_search",
        query="assistant search data scientist",
        expected_document_keys=["application:tracebank-assistant-search", "email:interview-assistant-search"],
    ),
    LocalEvalQuery(
        id="q_platform_radar",
        query="platform NLP radar",
        expected_document_keys=["radar_report:platform-radar"],
    ),
]


def _score(content: str, title: str, terms: list[str]) -> float:
    lowered_content = content.lower()
    lowered_title = title.lower()
    score = 0.0
    for term in terms:
        score += lowered_content.count(term)
        if term in lowered_title:
            score += 3
    if terms and all(term in lowered_content or term in lowered_title for term in terms):
        score += 5
    return score


def build_local_retrieval_eval_artifact() -> dict[str, Any]:
    chunks = []
    for document in LOCAL_DOCUMENTS:
        for chunk in chunk_text(document.content, max_tokens=28, overlap_tokens=6):
            chunks.append(
                {
                    "document_key": document.key,
                    "source_type": document.source_type,
                    "title": document.title,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                }
            )

    cases = []
    hits_at_3 = 0
    reciprocal_ranks = []
    for query in LOCAL_QUERIES:
        terms = query_terms(query.query)
        ranked = sorted(
            (
                {
                    "document_key": chunk["document_key"],
                    "source_type": chunk["source_type"],
                    "chunk_index": chunk["chunk_index"],
                    "score": _score(chunk["content"], chunk["title"], terms),
                }
                for chunk in chunks
                if any(term in f"{chunk['title']} {chunk['content']}".lower() for term in terms)
            ),
            key=lambda item: item["score"],
            reverse=True,
        )[:3]
        returned_keys = [item["document_key"] for item in ranked]
        first_rank = next(
            (
                index
                for index, key in enumerate(returned_keys, start=1)
                if key in query.expected_document_keys
            ),
            None,
        )
        if any(key in returned_keys for key in query.expected_document_keys):
            hits_at_3 += 1
        reciprocal_ranks.append(1 / first_rank if first_rank else 0)
        cases.append(
            {
                "id": query.id,
                "query": query.query,
                "expected_document_keys": query.expected_document_keys,
                "returned_document_keys": returned_keys,
                "top_chunks": ranked,
            }
        )

    query_count = len(LOCAL_QUERIES)
    return {
        "artifact": "local_retrieval_eval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "retriever_version": RETRIEVER_VERSION,
        "dataset": "local_retrieval_foundation_v1",
        "document_count": len(LOCAL_DOCUMENTS),
        "chunk_count": len(chunks),
        "query_count": query_count,
        "metrics": {
            "hit_rate_at_3": hits_at_3 / query_count if query_count else 0,
            "mean_reciprocal_rank": sum(reciprocal_ranks) / query_count if query_count else 0,
        },
        "cases": cases,
        "limitations": [
            "Uses tiny local deterministic fixtures, not production traffic.",
            "Exercises lexical chunk retrieval only; no embeddings, reranking, or OpenSearch.",
        ],
    }


def write_local_retrieval_eval_artifact(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = build_local_retrieval_eval_artifact()
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
