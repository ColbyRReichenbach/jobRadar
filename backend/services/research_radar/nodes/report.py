from __future__ import annotations

from backend.services.research_radar.llm import write_report


async def write_report_node(state):
    final_report, sections = await write_report(
        state["normalized_brief"],
        state["diff_summary"],
        state.get("evidence_items", []),
    )
    return {
        "final_report": final_report.model_dump(),
        "report_sections": [section.model_dump() for section in sections],
    }
