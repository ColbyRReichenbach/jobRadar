#!/usr/bin/env python3
"""Evaluate classifier-first Gmail routing with LLM adjudication as a layer.

This script reads a completed targeted label CSV. Rows that the classifier
already marked as not requiring LLM adjudication keep their deterministic
prediction. Rows with ``would_call_llm=true`` are sent through the live
redacted route/subtype LLM judge from ``run_gmail_llm_label_eval.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import statistics
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_gmail_label_eval import _clean, _pct, normalize_predicted_route, normalize_predicted_subtype
from scripts.run_gmail_llm_label_eval import (
    DEFAULT_LABEL_PATH,
    build_task,
    predict_row,
)


@dataclass(frozen=True)
class HybridLayerResult:
    case_id: str
    sender_domain: str
    expected_route: str
    expected_subtype: str
    hybrid_route: str
    hybrid_subtype: str
    hybrid_confidence: float
    route_match: bool
    subtype_match: bool
    full_match: bool
    decision_source: str
    model_used: bool
    model: str
    latency_ms: float
    prompt_tokens: int
    output_tokens: int
    cost_estimate_cents: float
    fallback_reason: str
    original_route: str
    original_subtype: str
    original_would_call_llm: str
    rationale: str
    redacted_subject: str
    redacted_body_preview: str


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _float(value: object) -> float:
    try:
        return float(str(value or "0"))
    except ValueError:
        return 0.0


def _labeled_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if _clean(row.get("expected_route")) and _clean(row.get("expected_subtype"))
    ]


async def evaluate_row(row: dict[str, str], *, task) -> HybridLayerResult:
    expected_route = _clean(row.get("expected_route"))
    expected_subtype = _clean(row.get("expected_subtype"))
    original_route = normalize_predicted_route(row)
    original_subtype = normalize_predicted_subtype(row)
    should_call = _truthy(row.get("would_call_llm"))

    if should_call:
        llm = await predict_row(row, task=task)
        route = llm.llm_route
        subtype = llm.llm_subtype
        confidence = llm.llm_confidence
        decision_source = "llm_adjudicated"
        model_used = True
        model = llm.model
        latency_ms = llm.latency_ms
        prompt_tokens = llm.prompt_tokens
        output_tokens = llm.output_tokens
        cost_estimate_cents = llm.cost_estimate_cents
        fallback_reason = llm.fallback_reason
        rationale = llm.rationale
    else:
        route = original_route
        subtype = original_subtype
        confidence = _float(row.get("predicted_confidence"))
        decision_source = "deterministic_classifier"
        model_used = False
        model = ""
        latency_ms = 0.0
        prompt_tokens = 0
        output_tokens = 0
        cost_estimate_cents = 0.0
        fallback_reason = ""
        rationale = "Accepted deterministic classifier result; row did not request LLM adjudication."

    return HybridLayerResult(
        case_id=_clean(row.get("case_id")),
        sender_domain=_clean(row.get("sender_domain")),
        expected_route=expected_route,
        expected_subtype=expected_subtype,
        hybrid_route=route,
        hybrid_subtype=subtype,
        hybrid_confidence=confidence,
        route_match=route == expected_route,
        subtype_match=subtype == expected_subtype,
        full_match=route == expected_route and subtype == expected_subtype,
        decision_source=decision_source,
        model_used=model_used,
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        cost_estimate_cents=cost_estimate_cents,
        fallback_reason=fallback_reason,
        original_route=original_route,
        original_subtype=original_subtype,
        original_would_call_llm=str(row.get("would_call_llm") or "").lower(),
        rationale=rationale,
        redacted_subject=_clean(row.get("redacted_subject")),
        redacted_body_preview=_clean(row.get("redacted_body_preview")),
    )


async def evaluate_rows(rows: list[dict[str, str]], *, task, concurrency: int) -> list[HybridLayerResult]:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _guarded(row: dict[str, str]) -> HybridLayerResult:
        async with semaphore:
            return await evaluate_row(row, task=task)

    return await asyncio.gather(*[_guarded(row) for row in rows])


def compute_metrics(
    results: list[HybridLayerResult],
    *,
    label_path: Path,
    llm_first_metrics_path: Path | None = None,
) -> dict[str, Any]:
    total = len(results)
    model_results = [result for result in results if result.model_used]
    latencies = sorted(result.latency_ms for result in model_results if result.latency_ms)
    prompt_tokens = sum(result.prompt_tokens for result in results)
    output_tokens = sum(result.output_tokens for result in results)
    total_cost = sum(result.cost_estimate_cents for result in results)
    source_counts = Counter(result.decision_source for result in results)
    route_pairs = Counter((result.hybrid_route, result.expected_route) for result in results)
    subtype_pairs = Counter((result.hybrid_subtype, result.expected_subtype) for result in results)
    high_conf_wrong = [
        result
        for result in results
        if result.hybrid_confidence >= 0.8 and not result.full_match
    ]
    metrics: dict[str, Any] = {
        "label_path": str(label_path),
        "sample_note": (
            "This is a simulated classifier-first hybrid eval over a targeted labeled sample. "
            "Only rows marked would_call_llm=true use the live LLM route/subtype judge."
        ),
        "totals": {
            "labeled_rows": total,
            "route_accuracy_pct": _pct(sum(result.route_match for result in results), total),
            "subtype_exact_match_pct": _pct(sum(result.subtype_match for result in results), total),
            "full_exact_match_pct": _pct(sum(result.full_match for result in results), total),
            "high_confidence_wrong_count": len(high_conf_wrong),
            "high_confidence_wrong_rate_pct": _pct(len(high_conf_wrong), total),
            "model_call_count": len(model_results),
            "model_call_rate_pct": _pct(len(model_results), total),
        },
        "decision_source_counts": {key: value for key, value in source_counts.most_common()},
        "latency": {
            "avg_model_call_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0,
            "p50_model_call_ms": round(statistics.median(latencies), 3) if latencies else 0,
            "p95_model_call_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 3) if latencies else 0,
        },
        "tokens": {
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "total_tokens": prompt_tokens + output_tokens,
            "avg_tokens_per_email": round((prompt_tokens + output_tokens) / total, 2) if total else 0,
        },
        "cost": {
            "total_cost_cents": round(total_cost, 6),
            "cost_per_1000_emails_cents": round(total_cost * 1000 / total, 6) if total else 0,
        },
        "top_route_pairs": [
            {"hybrid_route": predicted, "expected_route": expected, "count": count}
            for (predicted, expected), count in route_pairs.most_common(20)
        ],
        "top_subtype_pairs": [
            {"hybrid_subtype": predicted, "expected_subtype": expected, "count": count}
            for (predicted, expected), count in subtype_pairs.most_common(30)
        ],
        "high_confidence_wrong_case_ids": [result.case_id for result in high_conf_wrong[:50]],
    }
    if llm_first_metrics_path and llm_first_metrics_path.exists():
        llm_first = json.loads(llm_first_metrics_path.read_text(encoding="utf-8"))
        first_tokens = int(llm_first.get("tokens", {}).get("total_tokens") or 0)
        first_cost = float(llm_first.get("cost", {}).get("total_cost_cents") or 0)
        first_avg_latency = float(llm_first.get("latency", {}).get("avg_ms") or 0)
        metrics["llm_first_comparison"] = {
            "llm_first_total_tokens": first_tokens,
            "hybrid_total_tokens": prompt_tokens + output_tokens,
            "tokens_saved": first_tokens - (prompt_tokens + output_tokens),
            "tokens_saved_pct": round(((first_tokens - (prompt_tokens + output_tokens)) / first_tokens) * 100, 2) if first_tokens else 0,
            "llm_first_total_cost_cents": first_cost,
            "hybrid_total_cost_cents": round(total_cost, 6),
            "cost_saved_cents": round(first_cost - total_cost, 6),
            "cost_saved_pct": round(((first_cost - total_cost) / first_cost) * 100, 2) if first_cost else 0,
            "llm_first_avg_latency_ms": first_avg_latency,
            "hybrid_avg_model_call_latency_ms": metrics["latency"]["avg_model_call_ms"],
            "llm_first_model_call_count": int(llm_first.get("totals", {}).get("labeled_rows") or 0),
            "hybrid_model_call_count": len(model_results),
        }
    return metrics


def render_report(metrics: dict[str, Any]) -> str:
    totals = metrics["totals"]
    cost = metrics["cost"]
    tokens = metrics["tokens"]
    latency = metrics["latency"]
    comparison = metrics.get("llm_first_comparison") or {}
    route_rows = "\n".join(
        f"| `{row['hybrid_route']}` | `{row['expected_route']}` | {row['count']} |"
        for row in metrics["top_route_pairs"][:12]
    )
    subtype_rows = "\n".join(
        f"| `{row['hybrid_subtype']}` | `{row['expected_subtype']}` | {row['count']} |"
        for row in metrics["top_subtype_pairs"][:12]
    )
    comparison_section = ""
    if comparison:
        comparison_section = f"""
## LLM-First Comparison

| Metric | LLM-first | Hybrid layer | Saved |
| --- | ---: | ---: | ---: |
| Model calls | {comparison['llm_first_model_call_count']} | {comparison['hybrid_model_call_count']} | {comparison['llm_first_model_call_count'] - comparison['hybrid_model_call_count']} |
| Tokens | {comparison['llm_first_total_tokens']} | {comparison['hybrid_total_tokens']} | {comparison['tokens_saved']} ({comparison['tokens_saved_pct']}%) |
| Cost | {comparison['llm_first_total_cost_cents']} cents | {comparison['hybrid_total_cost_cents']} cents | {comparison['cost_saved_cents']} cents ({comparison['cost_saved_pct']}%) |
"""

    return f"""# Gmail Hybrid LLM Layer Eval

Generated at: {datetime.now(timezone.utc).isoformat()}

{metrics['sample_note']}

## Summary

| Metric | Value |
| --- | ---: |
| Labeled rows | {totals['labeled_rows']} |
| Route accuracy | {totals['route_accuracy_pct']}% |
| Subtype exact match | {totals['subtype_exact_match_pct']}% |
| Full route + subtype match | {totals['full_exact_match_pct']}% |
| High-confidence wrong | {totals['high_confidence_wrong_count']} ({totals['high_confidence_wrong_rate_pct']}%) |
| Model calls | {totals['model_call_count']} ({totals['model_call_rate_pct']}%) |

## Cost And Latency

| Metric | Value |
| --- | ---: |
| Prompt tokens | {tokens['prompt_tokens']} |
| Output tokens | {tokens['output_tokens']} |
| Total tokens | {tokens['total_tokens']} |
| Average tokens / email | {tokens['avg_tokens_per_email']} |
| Total cost estimate | {cost['total_cost_cents']} cents |
| Cost / 1,000 emails | {cost['cost_per_1000_emails_cents']} cents |
| Avg model-call latency | {latency['avg_model_call_ms']} ms |
| P50 model-call latency | {latency['p50_model_call_ms']} ms |
| P95 model-call latency | {latency['p95_model_call_ms']} ms |
{comparison_section}
## Top Route Pairs

| Hybrid Route | Expected Route | Count |
| --- | --- | ---: |
{route_rows or '| _None_ | _None_ | 0 |'}

## Top Subtype Pairs

| Hybrid Subtype | Expected Subtype | Count |
| --- | --- | ---: |
{subtype_rows or '| _None_ | _None_ | 0 |'}
"""


def write_artifacts(results: list[HybridLayerResult], metrics: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result_rows = [asdict(result) for result in results]
    if result_rows:
        _write_csv(output_dir / "case_results.csv", result_rows, list(result_rows[0].keys()))
    with (output_dir / "case_results.jsonl").open("w", encoding="utf-8") as handle:
        for row in result_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(metrics), encoding="utf-8")


async def async_main(args: argparse.Namespace) -> Path:
    label_path = Path(args.label_path)
    rows = _labeled_rows(_read_csv(label_path))
    if args.limit:
        rows = rows[: args.limit]
    task = build_task(args.model)
    results = await evaluate_rows(rows, task=task, concurrency=args.concurrency)
    llm_first_metrics_path = Path(args.llm_first_metrics_path) if args.llm_first_metrics_path else None
    metrics = compute_metrics(results, label_path=label_path, llm_first_metrics_path=llm_first_metrics_path)
    output_dir = Path(args.output_dir) if args.output_dir else label_path.parent / "hybrid_llm_layer_eval"
    if args.limit:
        output_dir = output_dir / f"limit_{args.limit}"
    write_artifacts(results, metrics, output_dir)
    return output_dir


def main() -> None:
    default_llm_metrics = (
        Path(DEFAULT_LABEL_PATH).parent
        / "llm_route_subtype_eval"
        / "metrics.json"
    )
    parser = argparse.ArgumentParser(description="Run classifier-first Gmail hybrid eval with LLM adjudication layer.")
    parser.add_argument("--label-path", default=DEFAULT_LABEL_PATH)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--llm-first-metrics-path", default=str(default_llm_metrics))
    args = parser.parse_args()
    output_dir = asyncio.run(async_main(args))
    print(output_dir)


if __name__ == "__main__":
    main()
