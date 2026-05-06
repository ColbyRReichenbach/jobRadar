"""Deterministic Copilot route-intent eval."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ROUTER_DATASET = Path("evals/copilot/copilot_router_v1.jsonl")


@dataclass(frozen=True)
class RouterEvalCase:
    id: str
    message: str
    expected_route: str
    expected_entities: dict[str, str]
    should_clarify: bool


@dataclass(frozen=True)
class RouteDecision:
    route: str
    confidence: float
    entities: dict[str, str]
    needs_clarification: bool
    decision_path: str


@dataclass(frozen=True)
class RouterCaseResult:
    case_id: str
    message: str
    expected_route: str
    predicted_route: str
    route_correct: bool
    expected_clarification: bool
    needs_clarification: bool
    clarification_correct: bool
    confidence: float
    entities: dict[str, str]
    failure_types: list[str]


def _load_jsonl(path: Path | str) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL on line {line_number}: {path}") from exc
    return rows


def load_router_cases(path: Path | str = DEFAULT_ROUTER_DATASET) -> list[RouterEvalCase]:
    cases = []
    for payload in _load_jsonl(path):
        cases.append(
            RouterEvalCase(
                id=str(payload["id"]),
                message=str(payload["message"]),
                expected_route=str(payload["expected_route"]),
                expected_entities={str(k): str(v) for k, v in dict(payload.get("expected_entities") or {}).items()},
                should_clarify=bool(payload.get("should_clarify", False)),
            )
        )
    return cases


def _extract_entities(message: str) -> dict[str, str]:
    entities: dict[str, str] = {}
    lowered = message.lower()
    known_companies = {
        "bank of america": "Bank of America",
        "bofa": "Bank of America",
        "google": "Google",
        "stripe": "Stripe",
    }
    known_roles = {
        "data analyst": "data analyst",
        "data scientist": "data scientist",
        "software engineer": "software engineer",
    }
    known_locations = {
        "new york": "New York",
        "nyc": "New York",
        "remote": "Remote",
    }
    for token, value in known_companies.items():
        if token in lowered:
            entities["company"] = value
            break
    for token, value in known_roles.items():
        if token in lowered:
            entities["role"] = value
            break
    for token, value in known_locations.items():
        if token in lowered:
            entities["location"] = value
            break
    return entities


def deterministic_route(message: str) -> RouteDecision:
    lowered = message.lower()
    entities = _extract_entities(message)

    route = "unknown"
    confidence = 0.25
    clarify = False

    if "gmail" in lowered and re.search(r"\b(sync|connect|connection|import)\b", lowered):
        route, confidence = "gmail_sync_diagnostics", 0.92
    elif "private" in lowered and ("link" in lowered or "shared" in lowered or "source" in lowered):
        route, confidence = "source_privacy_settings", 0.91
    elif "why" in lowered and "radar" in lowered and re.search(r"\b(fail|failed|error|stuck)\b", lowered):
        route, confidence = "radar_run_diagnostics", 0.9
    elif "radar" in lowered and re.search(r"\b(create|make|set up|track|tracker)\b", lowered):
        route, confidence = "radar_tracker_create_or_update", 0.88
        clarify = not all(key in entities for key in {"company", "role", "location"})
    elif re.search(r"\b(find|search|show)\b", lowered) and re.search(r"\b(job|jobs|role|roles)\b", lowered):
        route, confidence = "job_search", 0.88
        clarify = "role" not in entities
    elif "source" in lowered and ("job" in lowered or "company" in lowered or "have" in lowered):
        route, confidence = "job_source_question", 0.84
    elif "application" in lowered and re.search(r"\b(follow|follow-up|follow up|pipeline|need)\b", lowered):
        route, confidence = "application_pipeline_question", 0.87
    elif entities.get("company") and re.search(r"\b(what|what's|status|going on)\b", lowered):
        route, confidence, clarify = "unknown", 0.45, True

    return RouteDecision(
        route=route,
        confidence=round(confidence, 4),
        entities=entities,
        needs_clarification=clarify,
        decision_path="deterministic_rules_v1",
    )


def _baseline_decision(_: str) -> RouteDecision:
    return RouteDecision(
        route="generic_search_fallback",
        confidence=0.0,
        entities={},
        needs_clarification=False,
        decision_path="current_generic_copilot_baseline",
    )


def score_router_case(case: RouterEvalCase, decision: RouteDecision) -> RouterCaseResult:
    route_correct = decision.route == case.expected_route
    if case.expected_route == "unknown" and decision.needs_clarification and case.should_clarify:
        route_correct = True
    clarification_correct = decision.needs_clarification == case.should_clarify
    failures = []
    if not route_correct:
        failures.append("wrong_route" if decision.route != "generic_search_fallback" else "missing_route")
    if not clarification_correct:
        failures.append("clarification_error")
    return RouterCaseResult(
        case_id=case.id,
        message=case.message,
        expected_route=case.expected_route,
        predicted_route=decision.route,
        route_correct=route_correct,
        expected_clarification=case.should_clarify,
        needs_clarification=decision.needs_clarification,
        clarification_correct=clarification_correct,
        confidence=decision.confidence,
        entities=decision.entities,
        failure_types=failures,
    )


def _metrics(results: list[RouterCaseResult]) -> dict[str, float | int]:
    if not results:
        return {
            "case_count": 0,
            "route_accuracy": 0.0,
            "missing_route_rate": 0.0,
            "wrong_route_rate": 0.0,
            "clarification_accuracy": 0.0,
        }
    return {
        "case_count": len(results),
        "route_accuracy": round(sum(1 for item in results if item.route_correct) / len(results), 4),
        "missing_route_rate": round(sum(1 for item in results if "missing_route" in item.failure_types) / len(results), 4),
        "wrong_route_rate": round(sum(1 for item in results if "wrong_route" in item.failure_types) / len(results), 4),
        "clarification_accuracy": round(sum(1 for item in results if item.clarification_correct) / len(results), 4),
    }


def run_copilot_router_eval(dataset_path: Path | str = DEFAULT_ROUTER_DATASET) -> dict[str, Any]:
    cases = load_router_cases(dataset_path)
    baseline_results = [score_router_case(case, _baseline_decision(case.message)) for case in cases]
    candidate_results = [score_router_case(case, deterministic_route(case.message)) for case in cases]
    failure_counts: dict[str, int] = {}
    for result in candidate_results:
        for failure in result.failure_types:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
    return {
        "dataset_path": str(dataset_path),
        "dataset_version": Path(dataset_path).stem,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "name": "generic_search_fallback",
            "metrics": _metrics(baseline_results),
            "case_results": [asdict(item) for item in baseline_results],
        },
        "candidate": {
            "name": "deterministic_router_v1",
            "metrics": _metrics(candidate_results),
            "case_results": [asdict(item) for item in candidate_results],
        },
        "failure_summary": {
            "failed_case_count": sum(1 for item in candidate_results if item.failure_types),
            "failure_type_counts": dict(sorted(failure_counts.items())),
        },
        "decision_note": "Router eval is fixture-based and intended to expose missing product routes before live routing is enabled.",
    }
