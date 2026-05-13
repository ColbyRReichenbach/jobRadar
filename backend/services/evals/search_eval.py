"""Deterministic search quality evaluation.

This module intentionally avoids live OpenSearch, embeddings, or model calls so
CI can reproduce the same retrieval metrics from sanitized fixtures.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "job",
    "jobs",
    "of",
    "role",
    "roles",
    "the",
    "to",
    "with",
}

DEFAULT_DOCUMENTS_PATH = Path("evals/search/search_documents_v1.json")
DEFAULT_QUERIES_PATH = Path("evals/search/search_queries_v1.jsonl")
DEFAULT_BASELINES_PATH = Path("evals/search/search_baselines_v1.json")


@dataclass(frozen=True)
class SearchEvalDocument:
    key: str
    user_key: str
    source_type: str
    title: str
    subtitle: str | None = None
    body: str | None = None
    keywords: list[str] = field(default_factory=list)
    source_updated_at: datetime | None = None
    indexed_at: datetime | None = None

    @property
    def search_text(self) -> str:
        return " ".join(
            part
            for part in [
                self.title,
                self.subtitle or "",
                self.body or "",
                " ".join(self.keywords),
            ]
            if part
        )


@dataclass(frozen=True)
class SearchEvalQuery:
    id: str
    query: str
    expected_document_keys: list[str]
    notes: str | None = None


@dataclass(frozen=True)
class RankedDocument:
    key: str
    source_type: str
    title: str
    score: float


@dataclass(frozen=True)
class SearchEvalCaseResult:
    query_id: str
    query: str
    expected_document_keys: list[str]
    returned_document_keys: list[str]
    top_score: float | None
    latency_ms: float


@dataclass(frozen=True)
class SearchEvalStrategyResult:
    name: str
    strategy_type: str
    status: str
    description: str | None
    skip_reason: str | None
    metrics: dict[str, float | int | None]
    cases: list[SearchEvalCaseResult]


@dataclass(frozen=True)
class SearchEvalResult:
    dataset_version: str
    generated_at: str
    primary_user_key: str
    document_count: int
    query_count: int
    expected_query_count: int
    stale_document_count: int
    indexing_failure_count: int
    user_isolation: dict[str, Any]
    strategies: list[SearchEvalStrategyResult]
    recommended_strategy: str | None
    decision_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(text.lower()) if len(token) >= 2 and token not in STOPWORDS]


def _unique_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        unique.append(term)
    return unique


def _expanded_terms(terms: list[str], aliases: dict[str, list[str]]) -> list[str]:
    expanded = list(terms)
    for term in terms:
        expanded.extend(_tokenize(" ".join(aliases.get(term, []))))
    return _unique_terms(expanded)


def _field_score(text: str | None, terms: list[str], weight: float) -> float:
    if not text:
        return 0.0
    tokens = set(_tokenize(text))
    return sum(weight for term in terms if term in tokens)


def _score_document(
    doc: SearchEvalDocument,
    *,
    terms: list[str],
    expanded: list[str],
    strategy_type: str,
    source_boosts: dict[str, float],
) -> float:
    if strategy_type == "keyword_title":
        score = _field_score(doc.title, terms, 6.0) + _field_score(doc.subtitle, terms, 3.0)
        return score

    use_expansion = strategy_type in {"semantic_expansion", "hybrid_plus_boost"}
    scoring_terms = expanded if use_expansion else terms
    exact_score = (
        _field_score(doc.title, terms, 6.0)
        + _field_score(doc.subtitle, terms, 3.0)
        + _field_score(doc.body, terms, 1.5)
        + _field_score(" ".join(doc.keywords), terms, 2.5)
    )
    expansion_score = 0.0
    if use_expansion:
        expansion_only = [term for term in scoring_terms if term not in terms]
        expansion_score = (
            _field_score(doc.title, expansion_only, 2.0)
            + _field_score(doc.subtitle, expansion_only, 1.2)
            + _field_score(doc.body, expansion_only, 0.8)
            + _field_score(" ".join(doc.keywords), expansion_only, 1.0)
        )
    coverage_bonus = 3.0 if terms and all(term in _tokenize(doc.search_text) for term in terms) else 0.0
    score = exact_score + expansion_score + coverage_bonus
    if strategy_type == "hybrid_plus_boost" and score > 0:
        score *= float(source_boosts.get(doc.source_type, 1.0))
    return score


def rank_documents(
    query: str,
    documents: list[SearchEvalDocument],
    *,
    strategy_type: str,
    aliases: dict[str, list[str]] | None = None,
    source_boosts: dict[str, float] | None = None,
    limit: int = 10,
) -> list[RankedDocument]:
    terms = _unique_terms(_tokenize(query))
    if not terms:
        return []
    expanded = _expanded_terms(terms, aliases or {})
    ranked: list[RankedDocument] = []
    for doc in documents:
        score = _score_document(
            doc,
            terms=terms,
            expanded=expanded,
            strategy_type=strategy_type,
            source_boosts=source_boosts or {},
        )
        if score <= 0:
            continue
        ranked.append(RankedDocument(key=doc.key, source_type=doc.source_type, title=doc.title, score=round(score, 4)))
    ranked.sort(key=lambda item: (item.score, item.key), reverse=True)
    return ranked[:limit]


def _recall_at(expected: set[str], returned: list[str], k: int) -> float:
    if not expected:
        return 0.0
    return len(expected.intersection(returned[:k])) / len(expected)


def _mrr(expected: set[str], returned: list[str]) -> float:
    for index, key in enumerate(returned, start=1):
        if key in expected:
            return 1.0 / index
    return 0.0


def _ndcg(expected: set[str], returned: list[str], k: int = 10) -> float:
    if not expected:
        return 0.0
    dcg = 0.0
    for index, key in enumerate(returned[:k], start=1):
        if key in expected:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(expected), k)
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil((percentile / 100.0) * len(ordered)) - 1)
    return ordered[index]


def _strategy_metrics(cases: list[SearchEvalCaseResult], expected_query_count: int) -> dict[str, float | int | None]:
    expected_cases = [case for case in cases if case.expected_document_keys]
    latencies = [case.latency_ms for case in cases]
    if expected_query_count == 0:
        return {
            "recall_at_3": None,
            "recall_at_5": None,
            "mrr": None,
            "ndcg_at_10": None,
            "zero_result_rate": round(sum(1 for case in cases if not case.returned_document_keys) / len(cases), 4) if cases else 0.0,
            "p50_latency_ms": round(_percentile(latencies, 50), 4),
            "p95_latency_ms": round(_percentile(latencies, 95), 4),
            "avg_latency_ms": round(statistics.fmean(latencies), 4) if latencies else 0.0,
        }
    return {
        "recall_at_3": round(statistics.fmean(_recall_at(set(case.expected_document_keys), case.returned_document_keys, 3) for case in expected_cases), 4),
        "recall_at_5": round(statistics.fmean(_recall_at(set(case.expected_document_keys), case.returned_document_keys, 5) for case in expected_cases), 4),
        "mrr": round(statistics.fmean(_mrr(set(case.expected_document_keys), case.returned_document_keys) for case in expected_cases), 4),
        "ndcg_at_10": round(statistics.fmean(_ndcg(set(case.expected_document_keys), case.returned_document_keys, 10) for case in expected_cases), 4),
        "zero_result_rate": round(sum(1 for case in cases if not case.returned_document_keys) / len(cases), 4) if cases else 0.0,
        "p50_latency_ms": round(_percentile(latencies, 50), 4),
        "p95_latency_ms": round(_percentile(latencies, 95), 4),
        "avg_latency_ms": round(statistics.fmean(latencies), 4) if latencies else 0.0,
    }


def load_search_documents(path: Path | str = DEFAULT_DOCUMENTS_PATH) -> tuple[str, str, list[SearchEvalDocument], int]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    documents: list[SearchEvalDocument] = []
    failures = 0
    for item in payload.get("documents", []):
        if not item.get("key") or not item.get("user_key") or not item.get("source_type") or not item.get("title"):
            failures += 1
            continue
        documents.append(
            SearchEvalDocument(
                key=item["key"],
                user_key=item["user_key"],
                source_type=item["source_type"],
                title=item["title"],
                subtitle=item.get("subtitle"),
                body=item.get("body"),
                keywords=list(item.get("keywords") or []),
                source_updated_at=_parse_datetime(item.get("source_updated_at")),
                indexed_at=_parse_datetime(item.get("indexed_at")),
            )
        )
    return payload["dataset_version"], payload["primary_user_key"], documents, failures


def load_search_queries(path: Path | str = DEFAULT_QUERIES_PATH) -> list[SearchEvalQuery]:
    queries: list[SearchEvalQuery] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        try:
            queries.append(
                SearchEvalQuery(
                    id=str(payload["id"]),
                    query=str(payload["query"]),
                    expected_document_keys=list(payload.get("expected_document_keys") or []),
                    notes=payload.get("notes"),
                )
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Invalid search eval query on line {line_number}") from exc
    return queries


def load_baselines(path: Path | str = DEFAULT_BASELINES_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _recommended_strategy(strategies: list[SearchEvalStrategyResult]) -> str | None:
    completed = [strategy for strategy in strategies if strategy.status == "completed"]
    if not completed:
        return None
    strategy_priority = {
        "semantic_expansion": 3,
        "hybrid_plus_boost": 2,
        "keyword_full_text": 1,
        "keyword_title": 0,
    }
    completed.sort(
        key=lambda strategy: (
            float(strategy.metrics.get("recall_at_5") or 0.0),
            float(strategy.metrics.get("mrr") or 0.0),
            float(strategy.metrics.get("ndcg_at_10") or 0.0),
            -float(strategy.metrics.get("zero_result_rate") or 0.0),
            strategy_priority.get(strategy.strategy_type, 0),
        ),
        reverse=True,
    )
    return completed[0].name


def run_search_eval(
    *,
    documents_path: Path | str = DEFAULT_DOCUMENTS_PATH,
    queries_path: Path | str = DEFAULT_QUERIES_PATH,
    baselines_path: Path | str = DEFAULT_BASELINES_PATH,
) -> SearchEvalResult:
    dataset_version, primary_user_key, all_documents, indexing_failures = load_search_documents(documents_path)
    queries = load_search_queries(queries_path)
    baseline_config = load_baselines(baselines_path)
    aliases = baseline_config.get("semantic_aliases") or {}
    source_boosts = baseline_config.get("source_boosts") or {}

    user_documents = [doc for doc in all_documents if doc.user_key == primary_user_key]
    expected_query_count = sum(1 for query in queries if query.expected_document_keys)
    stale_count = sum(
        1
        for doc in user_documents
        if doc.source_updated_at and doc.indexed_at and doc.source_updated_at > doc.indexed_at
    )

    strategy_results: list[SearchEvalStrategyResult] = []
    for strategy in baseline_config.get("strategies", []):
        if strategy.get("enabled") is False:
            strategy_results.append(
                SearchEvalStrategyResult(
                    name=strategy["name"],
                    strategy_type=strategy["type"],
                    status="skipped",
                    description=strategy.get("description"),
                    skip_reason=strategy.get("skip_reason", "strategy disabled"),
                    metrics={},
                    cases=[],
                )
            )
            continue

        cases: list[SearchEvalCaseResult] = []
        for query in queries:
            started = time.perf_counter()
            ranked = rank_documents(
                query.query,
                user_documents,
                strategy_type=strategy["type"],
                aliases=aliases,
                source_boosts=source_boosts,
                limit=10,
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            cases.append(
                SearchEvalCaseResult(
                    query_id=query.id,
                    query=query.query,
                    expected_document_keys=query.expected_document_keys,
                    returned_document_keys=[item.key for item in ranked],
                    top_score=ranked[0].score if ranked else None,
                    latency_ms=round(latency_ms, 4),
                )
            )
        strategy_results.append(
            SearchEvalStrategyResult(
                name=strategy["name"],
                strategy_type=strategy["type"],
                status="completed",
                description=strategy.get("description"),
                skip_reason=None,
                metrics=_strategy_metrics(cases, expected_query_count),
                cases=cases,
            )
        )

    foreign_keys = {doc.key for doc in all_documents if doc.user_key != primary_user_key}
    leaked_keys = sorted(
        {
            key
            for strategy in strategy_results
            for case in strategy.cases
            for key in case.returned_document_keys
            if key in foreign_keys
        }
    )
    recommended = _recommended_strategy(strategy_results)
    return SearchEvalResult(
        dataset_version=dataset_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        primary_user_key=primary_user_key,
        document_count=len(user_documents),
        query_count=len(queries),
        expected_query_count=expected_query_count,
        stale_document_count=stale_count,
        indexing_failure_count=indexing_failures,
        user_isolation={
            "passed": not leaked_keys,
            "foreign_document_count": len(foreign_keys),
            "leaked_document_keys": leaked_keys,
        },
        strategies=strategy_results,
        recommended_strategy=recommended,
        decision_note=(
            f"Use {recommended} for the next retrieval iteration because it has the strongest recall/MRR blend "
            "with the least additional ranking complexity among tied strategies."
            if recommended
            else "No completed strategy was available."
        ),
    )


def render_search_eval_report(result: SearchEvalResult) -> str:
    lines = [
        "# Search Eval Report",
        "",
        f"- Generated at: `{result.generated_at}`",
        f"- Dataset version: `{result.dataset_version}`",
        f"- Recommended strategy: `{result.recommended_strategy or 'n/a'}`",
        f"- Decision note: {result.decision_note}",
        "",
        "## Dataset",
        "",
        f"- User-scoped documents: {result.document_count}",
        f"- Queries: {result.query_count}",
        f"- Queries with expected relevant documents: {result.expected_query_count}",
        f"- Stale indexed documents: {result.stale_document_count}",
        f"- Indexing fixture failures: {result.indexing_failure_count}",
        "",
        "## Strategy Results",
        "",
        "| Strategy | Status | Recall@3 | Recall@5 | MRR | nDCG@10 | Zero-result rate | p95 latency ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for strategy in result.strategies:
        metrics = strategy.metrics
        if strategy.status != "completed":
            lines.append(
                f"| `{strategy.name}` | skipped: {strategy.skip_reason} | - | - | - | - | - | - |"
            )
            continue
        lines.append(
            "| `{name}` | {status} | {r3} | {r5} | {mrr} | {ndcg} | {zero} | {p95} |".format(
                name=strategy.name,
                status=strategy.status,
                r3=metrics.get("recall_at_3"),
                r5=metrics.get("recall_at_5"),
                mrr=metrics.get("mrr"),
                ndcg=metrics.get("ndcg_at_10"),
                zero=metrics.get("zero_result_rate"),
                p95=metrics.get("p95_latency_ms"),
            )
        )

    lines.extend(
        [
            "",
            "## Query-Level Evidence",
            "",
            "| Query | Expected | Top returned |",
            "| --- | --- | --- |",
        ]
    )
    winning = next((strategy for strategy in result.strategies if strategy.name == result.recommended_strategy), None)
    if winning:
        for case in winning.cases:
            expected = ", ".join(f"`{item}`" for item in case.expected_document_keys) or "none expected"
            returned = ", ".join(f"`{item}`" for item in case.returned_document_keys[:5]) or "none"
            lines.append(f"| `{case.query}` | {expected} | {returned} |")

    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            f"- User isolation passed: `{result.user_isolation['passed']}`",
            f"- Foreign documents held out: {result.user_isolation['foreign_document_count']}",
            f"- Leaked foreign document keys: {result.user_isolation['leaked_document_keys'] or 'none'}",
            "",
            "## Production Notes",
            "",
            "- `vector_embedding_v1` is explicitly skipped until embeddings are provisioned.",
            "- The semantic strategy is a deterministic expansion proxy, not a claim that vector search is live.",
            "- Hybrid-plus-boost is tracked as a candidate, but tied quality is not enough to justify extra ranking complexity.",
            "- The next production ranking change should require this eval plus live latency/cost telemetry from real traffic.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_search_eval_outputs(
    result: SearchEvalResult,
    *,
    report_path: Path | str = Path("docs/ai-artifacts/search-eval.md"),
    metrics_path: Path | str = Path("docs/ai-artifacts/generated/search-eval-v1-metrics.json"),
) -> tuple[Path, Path]:
    report_target = Path(report_path)
    metrics_target = Path(metrics_path)
    report_target.parent.mkdir(parents=True, exist_ok=True)
    metrics_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(render_search_eval_report(result), encoding="utf-8")
    metrics_target.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return report_target, metrics_target
