"""Deterministic Radar evidence quality eval."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RADAR_EVIDENCE_DATASET = Path("evals/radar/radar_evidence_quality_v1.jsonl")


GENERIC_PHRASES = {
    "always looking for talented people",
    "explore opportunities",
    "growing team",
    "join our team",
}


@dataclass(frozen=True)
class RadarEvidenceCase:
    id: str
    source_type: str
    source_tier: str
    title: str
    raw_text: str
    company_name: str
    role_title: str
    expected_publishable: bool
    expected_failure_type: str | None
    expected_missing_data: bool
    target_company: str | None = None
    days_old: int = 0


@dataclass(frozen=True)
class EvidenceQualityDecision:
    publishable: bool
    source_trust: float
    specificity_score: float
    company_match_score: float
    role_match_score: float
    recency_score: float
    missing_data: bool
    failure_types: list[str]


@dataclass(frozen=True)
class RadarEvidenceCaseResult:
    case_id: str
    expected_publishable: bool
    actual_publishable: bool
    expected_failure_type: str | None
    missing_data: bool
    passed: bool
    scores: dict[str, float]
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


def load_radar_evidence_cases(path: Path | str = DEFAULT_RADAR_EVIDENCE_DATASET) -> list[RadarEvidenceCase]:
    cases = []
    for payload in _load_jsonl(path):
        cases.append(
            RadarEvidenceCase(
                id=str(payload["id"]),
                source_type=str(payload["source_type"]),
                source_tier=str(payload["source_tier"]),
                title=str(payload["title"]),
                raw_text=str(payload.get("raw_text") or ""),
                company_name=str(payload["company_name"]),
                role_title=str(payload["role_title"]),
                expected_publishable=bool(payload["expected_publishable"]),
                expected_failure_type=payload.get("expected_failure_type"),
                expected_missing_data=bool(payload["expected_missing_data"]),
                target_company=payload.get("target_company"),
                days_old=int(payload.get("days_old") or 0),
            )
        )
    return cases


def _contains_role(case: RadarEvidenceCase) -> bool:
    text = f"{case.title} {case.raw_text}".lower()
    return case.role_title.lower() in text


def _is_generic(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in GENERIC_PHRASES)


def score_evidence_quality(case: RadarEvidenceCase) -> EvidenceQualityDecision:
    failures: list[str] = []
    text = case.raw_text.strip()
    target_company = case.target_company or case.company_name

    if not text:
        failures.append("empty_page")
    if text and _is_generic(text):
        failures.append("generic_evidence")
    if case.company_name.lower() != target_company.lower():
        failures.append("wrong_company")
    if text and not _is_generic(text) and not _contains_role(case):
        failures.append("wrong_role")
    if case.days_old > 90:
        failures.append("stale_evidence")

    source_trust = {
        "tier_1_verified_first_party": 1.0,
        "tier_1_official_public_database": 0.95,
        "tier_2_reputable_secondary": 0.75,
        "tier_3_discovery_candidate": 0.35,
        "tier_4_user_private_internal": 0.65,
    }.get(case.source_tier, 0.2)
    specificity = 0.9 if case.source_type == "job_posting" and _contains_role(case) else 0.25 if text else 0.0
    company_match = 1.0 if case.company_name.lower() == target_company.lower() else 0.0
    role_match = 1.0 if _contains_role(case) else 0.0
    recency = 1.0 if case.days_old <= 30 else 0.65 if case.days_old <= 90 else 0.2
    publishable = not failures and source_trust >= 0.75 and specificity >= 0.7 and company_match >= 1.0 and role_match >= 1.0
    return EvidenceQualityDecision(
        publishable=publishable,
        source_trust=round(source_trust, 4),
        specificity_score=round(specificity, 4),
        company_match_score=round(company_match, 4),
        role_match_score=round(role_match, 4),
        recency_score=round(recency, 4),
        missing_data=not publishable,
        failure_types=failures,
    )


def run_radar_evidence_eval(dataset_path: Path | str = DEFAULT_RADAR_EVIDENCE_DATASET) -> dict[str, Any]:
    cases = load_radar_evidence_cases(dataset_path)
    results = []
    failure_counts: dict[str, int] = {}
    for case in cases:
        decision = score_evidence_quality(case)
        expected_failure_present = (
            case.expected_failure_type is None
            or case.expected_failure_type in decision.failure_types
        )
        passed = (
            decision.publishable == case.expected_publishable
            and decision.missing_data == case.expected_missing_data
            and expected_failure_present
        )
        for failure in decision.failure_types:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
        results.append(
            RadarEvidenceCaseResult(
                case_id=case.id,
                expected_publishable=case.expected_publishable,
                actual_publishable=decision.publishable,
                expected_failure_type=case.expected_failure_type,
                missing_data=decision.missing_data,
                passed=passed,
                scores={
                    "source_trust": decision.source_trust,
                    "specificity_score": decision.specificity_score,
                    "company_match_score": decision.company_match_score,
                    "role_match_score": decision.role_match_score,
                    "recency_score": decision.recency_score,
                },
                failure_types=decision.failure_types,
            )
        )

    case_count = len(results)
    publishable = [item for item in results if item.actual_publishable]
    return {
        "dataset_path": str(dataset_path),
        "dataset_version": Path(dataset_path).stem,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case_results": [asdict(item) for item in results],
        "metrics": {
            "case_count": case_count,
            "pass_rate": round(sum(1 for item in results if item.passed) / case_count, 4) if case_count else 0.0,
            "publishable_rate": round(len(publishable) / case_count, 4) if case_count else 0.0,
            "generic_evidence_rate": round(failure_counts.get("generic_evidence", 0) / case_count, 4) if case_count else 0.0,
            "empty_page_evidence_rate": round(failure_counts.get("empty_page", 0) / case_count, 4) if case_count else 0.0,
            "wrong_company_rate": round(failure_counts.get("wrong_company", 0) / case_count, 4) if case_count else 0.0,
            "wrong_role_rate": round(failure_counts.get("wrong_role", 0) / case_count, 4) if case_count else 0.0,
            "missing_data_stated_rate": round(sum(1 for item in results if item.missing_data) / case_count, 4) if case_count else 0.0,
        },
        "failure_summary": {
            "failed_case_count": sum(1 for item in results if not item.passed),
            "failure_type_counts": dict(sorted(failure_counts.items())),
        },
        "decision_note": "Radar evidence eval is fixture-based and tests source-quality gates before report generation.",
    }
