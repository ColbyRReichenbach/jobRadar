from __future__ import annotations

from backend.services.research_radar.llm import verify_report_with_metrics


async def verify_report_node(state):
    verification_result, llm_call = await verify_report_with_metrics(
        state["normalized_brief"],
        state.get("report_sections", []),
        state.get("evidence_items", []),
        db_session=state.get("db"),
        user_id=state.get("user_id"),
    )
    final_report = dict(state.get("final_report", {}))
    final_report["status"] = "needs_review" if verification_result.status == "needs_review" else "published"
    result = {
        "verification_result": verification_result.model_dump(),
        "final_report": final_report,
    }
    if llm_call:
        result["_llm_calls"] = [llm_call]
    return result
