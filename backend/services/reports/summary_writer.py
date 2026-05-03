"""Optional summary helpers for generated reports.

This module does not call a model. It prepares a constrained payload that a
future AI summary step may consume and renders only caller-provided summaries.
"""

from __future__ import annotations

from typing import Any

from backend.services.reports.report_templates import ReportInput


SUMMARY_INSTRUCTION = "Do not add claims not present in the provided metrics."


def build_summary_payload(report: ReportInput) -> dict[str, Any]:
    return {
        "instruction": SUMMARY_INSTRUCTION,
        "metadata": report.metadata.__dict__,
        "metrics": report.metrics,
        "token_breakdown": report.token_breakdown,
        "cost_breakdown": report.cost_breakdown,
        "latency_metrics": report.latency_metrics,
        "notes": report.notes,
    }


def render_summary_section(report: ReportInput) -> str:
    if report.ai_summary:
        return "\n".join(
            [
                "## AI Summary",
                "",
                "> Optional summary generated from computed report inputs only.",
                "",
                report.ai_summary,
            ]
        )

    return "\n".join(
        [
            "## Summary",
            "",
            "No AI summary was generated. Deterministic metric tables below are the source of truth.",
        ]
    )
