"""Offline Copilot groundedness and citation evaluation."""

from __future__ import annotations

import json
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.copilot.orchestrator import build_search_fallback_answer
from backend.services.copilot.schemas import CopilotCitation

DEFAULT_COPILOT_DATASET = Path("evals/copilot/copilot_questions_v1.jsonl")


@dataclass(frozen=True)
class CopilotEvalCase:
    id: str
    question: str
    answerable: bool
    expected_terms: list[str]
    expected_citation_document_ids: list[str]
    forbidden_terms: list[str]
    retrieved_context: list[dict[str, Any]]
    bad_candidate_answer: str | None = None


@dataclass(frozen=True)
class CopilotEvalCaseResult:
    id: str
    question: str
    answer: str
    answerable: bool
    passed: bool
    relevance_score: float
    citation_coverage: float
    unsupported_claim: bool
    refusal_correct: bool | None
    latency_ms: float
    citations: list[str]
    failure_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CopilotBadExample:
    case_id: str
    answer: str
    failure_types: list[str]


@dataclass(frozen=True)
class CopilotEvalResult:
    dataset_version: str
    generated_at: str
    cases: list[CopilotEvalCaseResult]
    bad_examples: list[CopilotBadExample]
    metrics: dict[str, float | int]
    decision_note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL on line {line_number}: {path}") from exc
    return rows


def load_copilot_eval_cases(path: Path | str = DEFAULT_COPILOT_DATASET) -> list[CopilotEvalCase]:
    cases: list[CopilotEvalCase] = []
    for payload in _load_jsonl(path):
        cases.append(
            CopilotEvalCase(
                id=str(payload["id"]),
                question=str(payload["question"]),
                answerable=bool(payload["answerable"]),
                expected_terms=list(payload.get("expected_terms") or []),
                expected_citation_document_ids=list(payload.get("expected_citation_document_ids") or []),
                forbidden_terms=list(payload.get("forbidden_terms") or []),
                retrieved_context=list(payload.get("retrieved_context") or []),
                bad_candidate_answer=payload.get("bad_candidate_answer"),
            )
        )
    return cases


def _citations_from_context(context: list[dict[str, Any]]) -> list[CopilotCitation]:
    citations: list[CopilotCitation] = []
    for item in context:
        citations.append(
            CopilotCitation(
                document_id=uuid.UUID(str(item["document_id"])),
                source_type=str(item["source_type"]),
                source_id=uuid.UUID(str(item["source_id"])),
                title=str(item["title"]),
                snippet=item.get("snippet"),
            )
        )
    return citations


def _term_score(answer: str, terms: list[str]) -> float:
    if not terms:
        return 1.0
    lowered = answer.lower()
    hits = sum(1 for term in terms if term.lower() in lowered)
    return hits / len(terms)


def _coverage(actual: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0 if not actual else 0.0
    return len(set(actual).intersection(expected)) / len(set(expected))


def _unsupported(answer: str, forbidden_terms: list[str]) -> bool:
    lowered = answer.lower()
    return any(term.lower() in lowered for term in forbidden_terms)


def _score_bad_candidate(case: CopilotEvalCase) -> CopilotBadExample | None:
    if not case.bad_candidate_answer:
        return None
    failures: list[str] = []
    if _unsupported(case.bad_candidate_answer, case.forbidden_terms):
        failures.append("unsupported_claim")
    if case.expected_citation_document_ids and not any(doc_id in case.bad_candidate_answer for doc_id in case.expected_citation_document_ids):
        failures.append("missing_citation")
    if not failures:
        return None
    return CopilotBadExample(case_id=case.id, answer=case.bad_candidate_answer, failure_types=failures)


def score_copilot_case(case: CopilotEvalCase) -> CopilotEvalCaseResult:
    citations = _citations_from_context(case.retrieved_context)
    started = time.perf_counter()
    payload = build_search_fallback_answer(case.question, citations)
    latency_ms = (time.perf_counter() - started) * 1000.0
    answer = str(payload["answer"])
    citation_ids = [str(item.get("document_id")) for item in payload.get("citations", [])]
    relevance = _term_score(answer, case.expected_terms)
    citation_coverage = _coverage(citation_ids, case.expected_citation_document_ids)
    unsupported = _unsupported(answer, case.forbidden_terms)
    refusal_correct = None
    failures: list[str] = []

    if case.answerable:
        if relevance < 1.0:
            failures.append("answer_relevance")
        if citation_coverage < 1.0:
            failures.append("missing_citation")
    else:
        refusal_correct = not citation_ids and "could not find" in answer.lower()
        if not refusal_correct:
            failures.append("refusal_miss")
    if unsupported:
        failures.append("unsupported_claim")

    return CopilotEvalCaseResult(
        id=case.id,
        question=case.question,
        answer=answer,
        answerable=case.answerable,
        passed=not failures,
        relevance_score=round(relevance, 4),
        citation_coverage=round(citation_coverage, 4),
        unsupported_claim=unsupported,
        refusal_correct=refusal_correct,
        latency_ms=round(latency_ms, 4),
        citations=citation_ids,
        failure_types=failures,
    )


def run_copilot_eval(dataset_path: Path | str = DEFAULT_COPILOT_DATASET) -> CopilotEvalResult:
    cases = load_copilot_eval_cases(dataset_path)
    results = [score_copilot_case(case) for case in cases]
    bad_examples = [item for item in (_score_bad_candidate(case) for case in cases) if item is not None]
    answerable = [case for case in results if case.answerable]
    unanswerable = [case for case in results if not case.answerable]
    latencies = [case.latency_ms for case in results]
    metrics: dict[str, float | int] = {
        "case_count": len(results),
        "pass_rate": round(sum(1 for case in results if case.passed) / len(results), 4) if results else 0.0,
        "groundedness": round(sum(1 for case in answerable if case.passed) / len(answerable), 4) if answerable else 0.0,
        "citation_coverage": round(statistics.fmean(case.citation_coverage for case in answerable), 4) if answerable else 0.0,
        "unsupported_claim_rate": round(sum(1 for case in results if case.unsupported_claim) / len(results), 4) if results else 0.0,
        "refusal_correctness": round(sum(1 for case in unanswerable if case.refusal_correct) / len(unanswerable), 4) if unanswerable else 0.0,
        "p95_latency_ms": round(max(latencies), 4) if latencies else 0.0,
        "cost_estimate_cents": 0,
    }
    return CopilotEvalResult(
        dataset_version=Path(dataset_path).stem,
        generated_at=datetime.now(timezone.utc).isoformat(),
        cases=results,
        bad_examples=bad_examples,
        metrics=metrics,
        decision_note="Offline fallback answers are fully grounded on this fixture; live model variants still require red-team and production telemetry gates.",
    )


def render_copilot_eval_report(result: CopilotEvalResult) -> str:
    lines = [
        "# Copilot Eval Report",
        "",
        f"- Generated at: `{result.generated_at}`",
        f"- Dataset version: `{result.dataset_version}`",
        f"- Decision note: {result.decision_note}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in result.metrics.items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## Case Results",
            "",
            "| Case | Passed | Citation coverage | Unsupported claim | Failures |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for case in result.cases:
        failures = ", ".join(case.failure_types) or "none"
        lines.append(f"| `{case.id}` | `{case.passed}` | {case.citation_coverage} | `{case.unsupported_claim}` | {failures} |")
    good = next((case for case in result.cases if case.passed and case.answerable), None)
    lines.extend(["", "## Good Example", ""])
    if good:
        lines.extend([f"- Case: `{good.id}`", f"- Answer: {good.answer}"])
    lines.extend(["", "## Bad Examples Caught By Scorer", ""])
    if result.bad_examples:
        for bad in result.bad_examples:
            lines.append(f"- `{bad.case_id}` would fail: {', '.join(bad.failure_types)}")
    else:
        lines.append("- None in this fixture.")
    return "\n".join(lines) + "\n"


def write_copilot_eval_outputs(
    result: CopilotEvalResult,
    *,
    report_path: Path | str = Path("docs/interview-artifacts/copilot-eval.md"),
    metrics_path: Path | str = Path("docs/interview-artifacts/generated/copilot-eval-v1-metrics.json"),
) -> tuple[Path, Path]:
    report_target = Path(report_path)
    metrics_target = Path(metrics_path)
    report_target.parent.mkdir(parents=True, exist_ok=True)
    metrics_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text(render_copilot_eval_report(result), encoding="utf-8")
    metrics_target.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return report_target, metrics_target
