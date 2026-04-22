from __future__ import annotations

from backend.services.research_radar.llm import verify_report


async def verify_report_node(state):
    result = await verify_report(
        state["normalized_brief"],
        state.get("report_sections", []),
        state.get("evidence_items", []),
    )
    final_report = dict(state.get("final_report", {}))
    final_report["status"] = "needs_review" if result.status == "needs_review" else "published"
    return {
        "verification_result": result.model_dump(),
        "final_report": final_report,
    }
