from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.services.research_radar.llm import (
    deterministic_extract_evidence,
    deterministic_normalized_brief,
    deterministic_research_plan,
    deterministic_report,
    deterministic_verification,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> list[dict[str, Any]]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _suite_result(name: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    passed = all(case["passed"] for case in cases)
    return {"suite": name, "passed": passed, "case_count": len(cases), "cases": cases}


def run_brief_normalization_eval() -> dict[str, Any]:
    cases = []
    for fixture in _load_fixture("brief_normalization.json"):
        brief = deterministic_normalized_brief(fixture["tracker"], fixture["user_context"]).model_dump()
        cases.append(
            {
                "name": fixture["name"],
                "passed": (
                    brief["ideal_role_titles"] == fixture["expect"]["ideal_role_titles"]
                    and brief["target_locations"] == fixture["expect"]["target_locations"]
                    and brief["remote_preferences"] == fixture["expect"]["remote_preferences"]
                ),
                "actual": {
                    "ideal_role_titles": brief["ideal_role_titles"],
                    "target_locations": brief["target_locations"],
                    "remote_preferences": brief["remote_preferences"],
                },
            }
        )
    return _suite_result("brief_normalization", cases)


def run_plan_quality_eval() -> dict[str, Any]:
    cases = []
    for fixture in _load_fixture("plan_quality.json"):
        tasks = deterministic_research_plan(
            fixture["normalized_brief"],
            fixture["depth"],
            fixture["max_queries"],
        )
        queries = [task.query for task in tasks]
        task_types = [task.task_type for task in tasks]
        cases.append(
            {
                "name": fixture["name"],
                "passed": (
                    len(tasks) <= fixture["expect"]["max_tasks"]
                    and all(required in task_types for required in fixture["expect"]["required_task_types"])
                    and all(token.lower() in " ".join(queries).lower() for token in fixture["expect"]["queries_contain"])
                ),
                "actual": {
                    "task_count": len(tasks),
                    "task_types": task_types,
                    "queries": queries,
                },
            }
        )
    return _suite_result("plan_quality", cases)


def run_evidence_extraction_eval() -> dict[str, Any]:
    cases = []
    for fixture in _load_fixture("evidence_extraction.json"):
        evidence_items = [item.model_dump() for item in deterministic_extract_evidence(fixture["normalized_brief"], fixture["source_document"])]
        first = evidence_items[0]
        cases.append(
            {
                "name": fixture["name"],
                "passed": (
                    first["evidence_type"] == fixture["expect"]["evidence_type"]
                    and first["company_name"] == fixture["expect"]["company_name"]
                    and first["role_title"] == fixture["expect"]["role_title"]
                    and fixture["expect"]["claim_contains"].lower() in first["claim"].lower()
                ),
                "actual": first,
            }
        )
    return _suite_result("evidence_extraction", cases)


def run_grounding_eval() -> dict[str, Any]:
    cases = []
    for fixture in _load_fixture("grounding.json"):
        result = deterministic_verification(fixture["report_sections"], fixture["evidence_items"]).model_dump()
        cases.append(
            {
                "name": fixture["name"],
                "passed": (
                    result["status"] == fixture["expect"]["status"]
                    and result["unsupported_claim_count"] == fixture["expect"]["unsupported_claim_count"]
                ),
                "actual": result,
            }
        )
    return _suite_result("grounding", cases)


def run_report_usefulness_eval() -> dict[str, Any]:
    cases = []
    for fixture in _load_fixture("report_usefulness.json"):
        report, sections = deterministic_report(
            fixture["normalized_brief"],
            fixture["diff_summary"],
            fixture["evidence_items"],
        )
        section_keys = [section.section_key for section in sections]
        cases.append(
            {
                "name": fixture["name"],
                "passed": (
                    report.finding_count == fixture["expect"]["finding_count"]
                    and report.new_findings_count == fixture["expect"]["new_findings_count"]
                    and all(key in section_keys for key in fixture["expect"]["required_sections"])
                    and fixture["expect"]["summary_contains"].lower() in report.summary_markdown.lower()
                ),
                "actual": {
                    "finding_count": report.finding_count,
                    "new_findings_count": report.new_findings_count,
                    "section_keys": section_keys,
                    "summary_markdown": report.summary_markdown,
                },
            }
        )
    return _suite_result("report_usefulness", cases)


def run_all_evals() -> dict[str, Any]:
    suites = [
        run_brief_normalization_eval(),
        run_plan_quality_eval(),
        run_evidence_extraction_eval(),
        run_grounding_eval(),
        run_report_usefulness_eval(),
    ]
    return {
        "passed": all(suite["passed"] for suite in suites),
        "suite_count": len(suites),
        "suites": suites,
    }


if __name__ == "__main__":
    summary = run_all_evals()
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["passed"] else 1)
