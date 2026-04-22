from __future__ import annotations

import json


def build_brief_normalization_prompt(*, tracker: dict, user_context: dict) -> str:
    return "\n".join(
        [
            "Normalize this Radar research tracker into a structured research brief.",
            "Prefer explicit tracker inputs first, then fill gaps from the user context.",
            "Return JSON only.",
            "",
            "Tracker:",
            json.dumps(tracker, indent=2, sort_keys=True),
            "",
            "User context:",
            json.dumps(user_context, indent=2, sort_keys=True),
        ]
    )


def build_research_plan_prompt(*, normalized_brief: dict, depth: str, max_tasks: int) -> str:
    return "\n".join(
        [
            "Plan bounded public-web research tasks for this job-search tracker.",
            f"Depth: {depth}",
            f"Maximum tasks: {max_tasks}",
            "Return JSON with a `tasks` array only.",
            "",
            json.dumps(normalized_brief, indent=2, sort_keys=True),
        ]
    )


def build_evidence_extraction_prompt(*, normalized_brief: dict, source_document: dict) -> str:
    return "\n".join(
        [
            "Extract evidence items from this public source document for the tracker objective.",
            "Return JSON with an `evidence_items` array only.",
            "",
            "Normalized brief:",
            json.dumps(normalized_brief, indent=2, sort_keys=True),
            "",
            "Source document:",
            json.dumps(source_document, indent=2, sort_keys=True),
        ]
    )


def build_report_prompt(*, normalized_brief: dict, diff_summary: dict, evidence_items: list[dict]) -> str:
    compact_evidence = evidence_items[:12]
    return "\n".join(
        [
            "Write a grounded research report for this Radar tracker.",
            "Return JSON with keys `title`, `summary_markdown`, and `sections`.",
            "Each section must cite evidence ids in structured_json.citation_ids.",
            "",
            "Normalized brief:",
            json.dumps(normalized_brief, indent=2, sort_keys=True),
            "",
            "Diff summary:",
            json.dumps(diff_summary, indent=2, sort_keys=True),
            "",
            "Evidence items:",
            json.dumps(compact_evidence, indent=2, sort_keys=True),
        ]
    )


def build_verification_prompt(*, normalized_brief: dict, report_sections: list[dict], evidence_items: list[dict]) -> str:
    return "\n".join(
        [
            "Verify whether this report is grounded in the evidence and useful for the tracker objective.",
            "Return JSON only.",
            "",
            "Normalized brief:",
            json.dumps(normalized_brief, indent=2, sort_keys=True),
            "",
            "Report sections:",
            json.dumps(report_sections, indent=2, sort_keys=True),
            "",
            "Evidence items:",
            json.dumps(evidence_items[:12], indent=2, sort_keys=True),
        ]
    )
