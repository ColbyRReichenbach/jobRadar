from __future__ import annotations

from backend.services.research_radar.llm import write_report_with_metrics


async def write_report_node(state):
    final_report, sections, llm_call = await write_report_with_metrics(
        state["normalized_brief"],
        state["diff_summary"],
        state.get("evidence_items", []),
        db_session=state.get("db"),
        user_id=state.get("user_id"),
    )
    result = {
        "final_report": final_report.model_dump(),
        "report_sections": [section.model_dump() for section in sections],
    }
    if llm_call:
        result["_llm_calls"] = [llm_call]
    return result
