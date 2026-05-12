"""Retrieval eval gate comparing source-level and chunk-level retrieval."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.models import Base, RetrievalTrace, User
from backend.services.retrieval.indexer import index_knowledge_document
from backend.services.retrieval.lexical import RETRIEVER_VERSION as CHUNK_RETRIEVER_VERSION
from backend.services.retrieval.lexical import normalize_query, query_terms, retrieve_document_chunks
from backend.services.search.backends.base import SearchResult
from backend.services.search.backends.postgres import PostgresSearchBackend
from backend.services.search.documents import SUPPORTED_SOURCE_TYPES, SearchDocumentInput


SOURCE_RETRIEVER_VERSION = "source_search_documents_v1"
DATASET_VERSION = "retrieval_eval_gate_v2"
DEFAULT_K = 3
PRIMARY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
FOREIGN_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
EVAL_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000002b2b")


@dataclass(frozen=True)
class RetrievalEvalDocument:
    key: str
    user_key: str
    source_type: str
    title: str
    subtitle: str | None = None
    body: str | None = None
    keywords: list[str] = field(default_factory=list)

    @property
    def user_id(self) -> uuid.UUID:
        return PRIMARY_USER_ID if self.user_key == "primary" else FOREIGN_USER_ID

    @property
    def source_id(self) -> uuid.UUID:
        return uuid.uuid5(EVAL_NAMESPACE, self.key)

    def to_input(self) -> SearchDocumentInput:
        return SearchDocumentInput(
            user_id=self.user_id,
            source_type=self.source_type,
            source_id=self.source_id,
            title=self.title,
            subtitle=self.subtitle,
            body=self.body,
            keywords=self.keywords,
            metadata={
                "eval_document_key": self.key,
                "eval_user_key": self.user_key,
            },
            source_updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )


@dataclass(frozen=True)
class RetrievalEvalCase:
    id: str
    query: str
    expected_document_keys: list[str]
    source_types: list[str] | None = None
    expected_empty_reason: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class RetrievalEvalCaseResult:
    case_id: str
    query: str
    expected_document_keys: list[str]
    returned_document_keys: list[str]
    returned_source_types: list[str]
    expected_empty_reason: str | None
    leaked_document_keys: list[str]
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalEvalStrategyResult:
    name: str
    retriever_version: str
    k: int
    metrics: dict[str, Any]
    cases: list[RetrievalEvalCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "retriever_version": self.retriever_version,
            "k": self.k,
            "metrics": self.metrics,
            "cases": [case.to_dict() for case in self.cases],
        }


@dataclass(frozen=True)
class RetrievalEvalGateResult:
    dataset_version: str
    generated_at: str
    k: int
    document_count: int
    case_count: int
    strategies: list[RetrievalEvalStrategyResult]
    comparison: dict[str, Any]
    promotion_recommendation: str
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": "retrieval_eval_gate",
            "dataset_version": self.dataset_version,
            "generated_at": self.generated_at,
            "k": self.k,
            "document_count": self.document_count,
            "case_count": self.case_count,
            "strategies": [strategy.to_dict() for strategy in self.strategies],
            "comparison": self.comparison,
            "promotion_recommendation": self.promotion_recommendation,
            "limitations": self.limitations,
        }


EVAL_DOCUMENTS = [
    RetrievalEvalDocument(
        key="application:tracebank-assistant-search",
        user_key="primary",
        source_type="application",
        title="TraceBank Assistant Search Data Scientist",
        subtitle="Charlotte",
        body=(
            "Build assistant search quality models, lexical retrieval, chunk indexing, "
            "and NLP evaluation workflows."
        ),
        keywords=["assistant search", "retrieval", "NLP evals"],
    ),
    RetrievalEvalDocument(
        key="application:northstar-risk-ml-platform",
        user_key="primary",
        source_type="application",
        title="Northstar Risk ML Platform Engineer",
        subtitle="New York hybrid",
        body=(
            "Own fraud risk model monitoring, feature store reliability, and ML governance "
            "for regulated banking workflows."
        ),
        keywords=["risk ML", "feature store", "fraud monitoring"],
    ),
    RetrievalEvalDocument(
        key="email:interview-assistant-search",
        user_key="primary",
        source_type="email",
        title="Assistant search interview",
        subtitle="Jordan Recruiter",
        body="Interview invitation for the assistant search data science role with TraceBank.",
        keywords=["interview", "assistant search"],
    ),
    RetrievalEvalDocument(
        key="email:northstar-offer-risk-ml",
        user_key="primary",
        source_type="email",
        title="Northstar offer details",
        subtitle="Maya Recruiter",
        body=(
            "Offer follow-up mentions base salary, equity refresh, and response deadline "
            "for the risk ML platform role."
        ),
        keywords=["offer", "salary", "equity", "risk ML"],
    ),
    RetrievalEvalDocument(
        key="contact:jordan-ai-platform",
        user_key="primary",
        source_type="contact",
        title="Jordan Rivera",
        subtitle="AI Platform Lead at TraceBank",
        body="Jordan can discuss platform retrieval quality and evaluation workflows.",
        keywords=["AI Platform Lead", "TraceBank"],
    ),
    RetrievalEvalDocument(
        key="contact:maya-risk-recruiter",
        user_key="primary",
        source_type="contact",
        title="Maya Chen",
        subtitle="Risk ML recruiter at Northstar",
        body="Maya owns recruiter follow-up for fraud risk ML roles and offer process checkpoints.",
        keywords=["recruiter", "Northstar", "risk ML"],
    ),
    RetrievalEvalDocument(
        key="radar_report:platform-radar",
        user_key="primary",
        source_type="radar_report",
        title="Platform hiring radar",
        subtitle="published",
        body="Radar found new platform engineering and NLP hiring signals in developer tools.",
        keywords=["Radar", "platform", "NLP"],
    ),
    RetrievalEvalDocument(
        key="radar_report:fintech-risk-radar",
        user_key="primary",
        source_type="radar_report",
        title="Fintech risk hiring radar",
        subtitle="published",
        body=(
            "Radar summary notes regulated fintech teams hiring for fraud modeling, "
            "ML platform, and model governance."
        ),
        keywords=["Radar", "risk ML", "fraud governance"],
    ),
    RetrievalEvalDocument(
        key="application:foreign-assistant-search",
        user_key="foreign",
        source_type="application",
        title="OtherBank Assistant Search Data Scientist",
        body="This foreign user's assistant search document must not be retrieved for the primary user.",
        keywords=["assistant search", "foreign"],
    ),
    RetrievalEvalDocument(
        key="email:foreign-shadowleak-zebra",
        user_key="foreign",
        source_type="email",
        title="Shadowleak zebra coordinator",
        body="Foreign-only shibboleth zephyr marker for user isolation checks.",
        keywords=["shadowleak", "zebra", "shibboleth"],
    ),
]

EVAL_CASES = [
    RetrievalEvalCase(
        id="q_assistant_search_role",
        query="assistant search data scientist",
        expected_document_keys=[
            "application:tracebank-assistant-search",
            "email:interview-assistant-search",
        ],
    ),
    RetrievalEvalCase(
        id="q_risk_ml_application",
        query="fraud risk model monitoring feature store",
        expected_document_keys=["application:northstar-risk-ml-platform"],
        source_types=["application"],
    ),
    RetrievalEvalCase(
        id="q_offer_email",
        query="base salary equity response deadline",
        expected_document_keys=["email:northstar-offer-risk-ml"],
        source_types=["email"],
    ),
    RetrievalEvalCase(
        id="q_platform_contact",
        query="platform retrieval quality Jordan",
        expected_document_keys=["contact:jordan-ai-platform"],
        source_types=["contact"],
    ),
    RetrievalEvalCase(
        id="q_recruiter_contact",
        query="Maya recruiter fraud risk offer",
        expected_document_keys=["contact:maya-risk-recruiter"],
        source_types=["contact"],
    ),
    RetrievalEvalCase(
        id="q_radar_platform",
        query="platform NLP radar",
        expected_document_keys=["radar_report:platform-radar"],
        source_types=["radar_report"],
    ),
    RetrievalEvalCase(
        id="q_fintech_risk_radar",
        query="fraud model governance radar",
        expected_document_keys=["radar_report:fintech-risk-radar"],
        source_types=["radar_report"],
    ),
    RetrievalEvalCase(
        id="q_empty",
        query="",
        expected_document_keys=[],
        expected_empty_reason="empty_query",
    ),
    RetrievalEvalCase(
        id="q_unsupported_source",
        query="assistant search",
        expected_document_keys=[],
        source_types=["resume"],
        expected_empty_reason="no_allowed_source_types",
    ),
    RetrievalEvalCase(
        id="q_user_isolation_foreign_unique",
        query="shadowleak zebra shibboleth",
        expected_document_keys=[],
        notes="Foreign-only terms must not return another user's email document.",
    ),
]


def _source_id_key_map() -> dict[str, str]:
    return {str(document.source_id): document.key for document in EVAL_DOCUMENTS}


def _foreign_keys() -> set[str]:
    return {document.key for document in EVAL_DOCUMENTS if document.user_key != "primary"}


def _allowed_source_types(source_types: list[str] | None) -> list[str] | None:
    if not source_types:
        return None
    return [item for item in source_types if item in SUPPORTED_SOURCE_TYPES]


async def _ensure_eval_users(db: AsyncSession) -> None:
    for user_id, email, name in [
        (PRIMARY_USER_ID, "retrieval-primary@apptrail.test", "Retrieval Primary"),
        (FOREIGN_USER_ID, "retrieval-foreign@apptrail.test", "Retrieval Foreign"),
    ]:
        if await db.get(User, user_id):
            continue
        db.add(User(id=user_id, google_id=f"retrieval-{user_id}", email=email, name=name))
    await db.flush()


async def _seed_eval_documents(db: AsyncSession) -> None:
    await _ensure_eval_users(db)
    backend = PostgresSearchBackend()
    for document in EVAL_DOCUMENTS:
        document_input = document.to_input()
        search_document = await backend.index_document(db, document_input)
        await index_knowledge_document(db, document_input, search_document=search_document)
    await db.flush()


def _generated_source_trace(case: RetrievalEvalCase, results: list[SearchResult], *, status: str) -> dict[str, Any]:
    return {
        "retriever_version": SOURCE_RETRIEVER_VERSION,
        "query": case.query,
        "normalized_query": normalize_query(case.query),
        "source_types": _allowed_source_types(case.source_types),
        "candidate_count": len(results),
        "returned_count": len(results),
        "status": status,
        "scores": [
            {
                "document_id": str(result.document_id),
                "source_type": result.source_type,
                "source_id": str(result.source_id),
                "title": result.title,
                "snippet": result.snippet,
                "score": result.score,
            }
            for result in results
        ],
    }


def _trace_snapshot(trace: RetrievalTrace | None) -> dict[str, Any]:
    if trace is None:
        return {}
    return {
        "trace_id": str(trace.id),
        "retriever_version": trace.retriever_version,
        "query": trace.query,
        "normalized_query": trace.normalized_query,
        "source_types": trace.source_types,
        "filters": trace.filters_json,
        "candidate_count": trace.candidate_count,
        "returned_count": trace.returned_count,
        "selected_chunk_ids": trace.selected_chunk_ids,
        "status": trace.status,
        "scores": trace.scores_json or [],
        "latency_ms": trace.latency_ms,
    }


async def _latest_trace(
    db: AsyncSession,
    *,
    surface: str,
    query: str,
    retriever_version: str,
) -> RetrievalTrace | None:
    return (
        await db.execute(
            select(RetrievalTrace)
            .where(
                RetrievalTrace.user_id == PRIMARY_USER_ID,
                RetrievalTrace.surface == surface,
                RetrievalTrace.normalized_query == normalize_query(query),
                RetrievalTrace.retriever_version == retriever_version,
            )
            .order_by(RetrievalTrace.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _status_for_source_case(case: RetrievalEvalCase) -> str:
    if not query_terms(case.query):
        return "empty_query"
    if case.source_types and not _allowed_source_types(case.source_types):
        return "no_allowed_source_types"
    return "ok"


async def _run_source_strategy(db: AsyncSession, *, k: int) -> RetrievalEvalStrategyResult:
    source_id_to_key = _source_id_key_map()
    foreign_keys = _foreign_keys()
    case_results = []
    backend = PostgresSearchBackend()
    for case in EVAL_CASES:
        results = await backend.search(
            db,
            user_id=PRIMARY_USER_ID,
            query=case.query,
            source_types=case.source_types,
            limit=k,
        )
        returned = _dedupe_document_results(
            (source_id_to_key.get(str(result.source_id), f"unknown:{result.source_id}"), result.source_type)
            for result in results
        )
        case_results.append(
            RetrievalEvalCaseResult(
                case_id=case.id,
                query=case.query,
                expected_document_keys=case.expected_document_keys,
                returned_document_keys=[item[0] for item in returned],
                returned_source_types=[item[1] for item in returned],
                expected_empty_reason=case.expected_empty_reason,
                leaked_document_keys=[key for key, _source_type in returned if key in foreign_keys],
                trace=_generated_source_trace(case, results, status=_status_for_source_case(case)),
            )
        )
    return RetrievalEvalStrategyResult(
        name="source_search_documents",
        retriever_version=SOURCE_RETRIEVER_VERSION,
        k=k,
        metrics=_metrics(case_results, k=k),
        cases=case_results,
    )


async def _run_chunk_strategy(db: AsyncSession, *, k: int) -> RetrievalEvalStrategyResult:
    source_id_to_key = _source_id_key_map()
    foreign_keys = _foreign_keys()
    case_results = []
    for case in EVAL_CASES:
        chunks = await retrieve_document_chunks(
            db,
            user_id=PRIMARY_USER_ID,
            query=case.query,
            source_types=case.source_types,
            surface="retrieval_eval_gate",
            limit=k,
        )
        trace = await _latest_trace(
            db,
            surface="retrieval_eval_gate",
            query=case.query,
            retriever_version=CHUNK_RETRIEVER_VERSION,
        )
        returned = _dedupe_document_results(
            (source_id_to_key.get(str(chunk.source_id), f"unknown:{chunk.source_id}"), chunk.source_type)
            for chunk in chunks
        )
        case_results.append(
            RetrievalEvalCaseResult(
                case_id=case.id,
                query=case.query,
                expected_document_keys=case.expected_document_keys,
                returned_document_keys=[item[0] for item in returned],
                returned_source_types=[item[1] for item in returned],
                expected_empty_reason=case.expected_empty_reason,
                leaked_document_keys=[key for key, _source_type in returned if key in foreign_keys],
                trace=_trace_snapshot(trace),
            )
        )
    return RetrievalEvalStrategyResult(
        name="lexical_document_chunks",
        retriever_version=CHUNK_RETRIEVER_VERSION,
        k=k,
        metrics=_metrics(case_results, k=k),
        cases=case_results,
    )


def _dedupe_document_results(items) -> list[tuple[str, str]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for key, source_type in items:
        if key in seen:
            continue
        seen.add(key)
        deduped.append((key, source_type))
    return deduped


def _metrics(cases: list[RetrievalEvalCaseResult], *, k: int) -> dict[str, Any]:
    labeled_cases = [case for case in cases if case.expected_document_keys]
    empty_cases = [case for case in cases if case.expected_empty_reason]
    unlabeled_empty_cases = [case for case in cases if not case.expected_document_keys]
    recalls = []
    reciprocal_ranks = []
    precisions = []
    for case in labeled_cases:
        expected = set(case.expected_document_keys)
        returned = case.returned_document_keys[:k]
        relevant = [key for key in returned if key in expected]
        recalls.append(len(set(relevant)) / len(expected) if expected else 0)
        first_rank = next((index for index, key in enumerate(returned, start=1) if key in expected), None)
        reciprocal_ranks.append(1 / first_rank if first_rank else 0)
        precisions.append(len(relevant) / len(returned) if returned else 0)

    empty_correct = [len(case.returned_document_keys) == 0 for case in empty_cases]
    return {
        f"recall_at_{k}": sum(recalls) / len(recalls) if recalls else 0,
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0,
        f"source_precision_at_{k}": sum(precisions) / len(precisions) if precisions else 0,
        f"citation_precision_at_{k}": sum(precisions) / len(precisions) if precisions else 0,
        "empty_result_correctness": (
            sum(1 for item in empty_correct if item) / len(empty_correct) if empty_correct else None
        ),
        "empty_query_returned_empty": _case_returned_empty(cases, "q_empty"),
        "unsupported_source_returned_empty": _case_returned_empty(cases, "q_unsupported_source"),
        "user_isolation_query_returned_empty": _case_returned_empty(cases, "q_user_isolation_foreign_unique"),
        "user_isolation_failures": sum(len(case.leaked_document_keys) for case in cases),
        "case_count": len(cases),
        "labeled_case_count": len(labeled_cases),
        "expected_empty_case_count": len(empty_cases),
        "unlabeled_empty_case_count": len(unlabeled_empty_cases),
    }


def _case_returned_empty(cases: list[RetrievalEvalCaseResult], case_id: str) -> bool | None:
    case = next((item for item in cases if item.case_id == case_id), None)
    if case is None:
        return None
    return len(case.returned_document_keys) == 0


def _comparison(strategies: list[RetrievalEvalStrategyResult], *, k: int) -> dict[str, Any]:
    by_name = {strategy.name: strategy for strategy in strategies}
    source = by_name["source_search_documents"].metrics
    chunks = by_name["lexical_document_chunks"].metrics
    source_recall = source[f"recall_at_{k}"]
    chunk_recall = chunks[f"recall_at_{k}"]
    source_precision = source[f"citation_precision_at_{k}"]
    chunk_precision = chunks[f"citation_precision_at_{k}"]
    source_mrr = source["mrr"]
    chunk_mrr = chunks["mrr"]
    chunk_recall_delta = chunk_recall - source_recall
    chunk_precision_delta = chunk_precision - source_precision
    chunk_mrr_delta = chunk_mrr - source_mrr
    return {
        "primary_metric": f"recall_at_{k}",
        f"source_recall_at_{k}": source_recall,
        f"chunk_recall_at_{k}": chunk_recall,
        f"source_citation_precision_at_{k}": source_precision,
        f"chunk_citation_precision_at_{k}": chunk_precision,
        "source_mrr": source_mrr,
        "chunk_mrr": chunk_mrr,
        "chunk_minus_source_recall": chunk_recall_delta,
        "chunk_minus_source_mrr": chunk_mrr_delta,
        "chunk_minus_source_citation_precision": chunk_precision_delta,
        "chunk_recall_improved": chunk_recall_delta > 0,
        "chunk_mrr_improved": chunk_mrr_delta > 0,
        "chunk_citation_precision_improved": chunk_precision_delta > 0,
        "chunk_recall_tied": chunk_recall_delta == 0,
        "chunk_citation_precision_tied": chunk_precision_delta == 0,
        "both_user_isolated": (
            source["user_isolation_failures"] == 0
            and chunks["user_isolation_failures"] == 0
            and source["user_isolation_query_returned_empty"] is True
            and chunks["user_isolation_query_returned_empty"] is True
        ),
        "both_handle_empty_and_unsupported": all(
            strategy.metrics["empty_query_returned_empty"] is True
            and strategy.metrics["unsupported_source_returned_empty"] is True
            for strategy in strategies
        ),
        "chunk_retrieval_improves_eval_gate": chunk_recall_delta > 0 and chunk_precision_delta >= 0,
        "recommended_strategy_for_promotion": "none_hold_for_labeled_production_outcomes",
    }


async def run_retrieval_eval_gate(db: AsyncSession, *, k: int = DEFAULT_K) -> RetrievalEvalGateResult:
    await _seed_eval_documents(db)
    source = await _run_source_strategy(db, k=k)
    chunks = await _run_chunk_strategy(db, k=k)
    strategies = [source, chunks]
    return RetrievalEvalGateResult(
        dataset_version=DATASET_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        k=k,
        document_count=len(EVAL_DOCUMENTS),
        case_count=len(EVAL_CASES),
        strategies=strategies,
        comparison=_comparison(strategies, k=k),
        promotion_recommendation=(
            "do_not_promote_chunk_retrieval_yet: local eval gate is deterministic and useful for "
            "measurement, but it is too small to justify Copilot or Radar production routing changes."
        ),
        limitations=[
            "Uses manually labeled local fixtures, not production traffic or held-out user data.",
            "Compares source-level LIKE search with lexical chunks only; no embeddings, reranking, or OpenSearch.",
            "Citation precision is measured as returned-source relevance because no model answers are generated.",
            "Chunk retrieval is not promoted into Copilot or Radar runtime paths by this goal.",
        ],
    )


async def run_local_retrieval_eval_gate(*, k: int = DEFAULT_K) -> RetrievalEvalGateResult:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            result = await run_retrieval_eval_gate(session, k=k)
            await session.commit()
            return result
    finally:
        await engine.dispose()


async def write_retrieval_eval_gate_artifact(path: Path, *, k: int = DEFAULT_K) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = await run_local_retrieval_eval_gate(k=k)
    path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
