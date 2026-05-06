#!/usr/bin/env python3
"""Run search/source retrieval artifact eval."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services.evals.artifact_packager import current_git_sha, utc_now_iso, write_feature_artifact_bundle
from backend.services.evals.search_eval import (
    DEFAULT_BASELINES_PATH,
    DEFAULT_DOCUMENTS_PATH,
    DEFAULT_QUERIES_PATH,
    run_search_eval,
)


def _winning_strategy(result: Any) -> Any | None:
    return next((strategy for strategy in result.strategies if strategy.name == result.recommended_strategy), None)


def build_artifact_payload(result: Any, *, documents_path: Path, queries_path: Path, baselines_path: Path) -> dict[str, Any]:
    winning = _winning_strategy(result)
    case_results = []
    failure_counts: Counter[str] = Counter()
    if winning:
        for case in winning.cases:
            failures = []
            if case.expected_document_keys and not set(case.expected_document_keys).intersection(case.returned_document_keys[:5]):
                failures.append("retrieval_miss")
            if not case.returned_document_keys:
                failures.append("zero_results")
            failure_counts.update(failures)
            case_results.append(
                {
                    "case_id": case.query_id,
                    "query": case.query,
                    "strategy": winning.name,
                    "expected_document_keys": case.expected_document_keys,
                    "returned_document_keys": case.returned_document_keys,
                    "top_score": case.top_score,
                    "passed": not failures,
                    "failure_types": failures,
                }
            )

    metrics = {
        "document_count": result.document_count,
        "query_count": result.query_count,
        "recommended_strategy": result.recommended_strategy,
        "stale_document_count": result.stale_document_count,
        "indexing_failure_count": result.indexing_failure_count,
        "user_isolation_passed": result.user_isolation["passed"],
    }
    if winning:
        metrics.update(winning.metrics)

    return {
        "metadata": {
            "report_type": "source-retrieval-eval",
            "title": "Search and Source Retrieval Artifact Eval",
            "generated_at": utc_now_iso(),
            "git_sha": current_git_sha(),
            "release_version": "feature-artifacts",
            "dataset_version": result.dataset_version,
            "model": "postgres-lexical",
            "prompt_version": str(result.recommended_strategy or "no-strategy"),
            "recommendation": "use_recommended_strategy_as_retrieval_baseline",
            "decision": "baseline_artifact_ready",
        },
        "metrics": metrics,
        "token_breakdown": {
            "model_calls": 0,
            "embedding_calls": 0,
            "evidence_status": "deterministic_search_fixture_eval",
        },
        "cost_breakdown": {
            "total_cost_cents": 0,
            "broad_provider_calls": 0,
        },
        "latency_metrics": winning.metrics if winning else {},
        "case_results": case_results,
        "failure_summary": {
            "failed_case_count": sum(1 for item in case_results if not item["passed"]),
            "failure_type_counts": dict(sorted(failure_counts.items())),
            "user_isolation": result.user_isolation,
        },
        "cost_projection": {
            "feature": "search_source_retrieval",
            "period": "per_dataset_scaled",
            "evidence_status": "fixture_projection",
            "baseline": {
                "queries": result.query_count,
                "broad_provider_fallback_rate": 1.0,
                "estimated_total_cost_cents": 0.0,
            },
            "candidate": {
                "queries": result.query_count,
                "broad_provider_fallback_rate": 0.0,
                "estimated_total_cost_cents": 0.0,
            },
            "delta": {
                "broad_calls_avoided": result.query_count,
                "cost_delta_cents": 0.0,
            },
        },
        "supporting_artifacts": [
            {"label": "Search documents fixture", "path": str(documents_path)},
            {"label": "Search queries fixture", "path": str(queries_path)},
            {"label": "Search baselines fixture", "path": str(baselines_path)},
            {"label": "Feature changelog", "path": "docs/interview-artifacts/feature-changelogs/search-source-intelligence-changelog.md"},
        ],
        "notes": [
            result.decision_note,
            "This artifact evaluates deterministic fixture retrieval. Direct source provider costs should be added from JobSearchProviderUsage in the DB-backed phase.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=DEFAULT_DOCUMENTS_PATH)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--baselines", type=Path, default=DEFAULT_BASELINES_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/interview-artifacts/generated"))
    parser.add_argument("--payload-output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    result = run_search_eval(documents_path=args.documents, queries_path=args.queries, baselines_path=args.baselines)
    payload = build_artifact_payload(
        result,
        documents_path=args.documents,
        queries_path=args.queries,
        baselines_path=args.baselines,
    )
    if args.payload_output:
        args.payload_output.parent.mkdir(parents=True, exist_ok=True)
        args.payload_output.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    output = write_feature_artifact_bundle(payload, args.output_dir, overwrite=args.overwrite)
    print(output)


if __name__ == "__main__":
    main()
