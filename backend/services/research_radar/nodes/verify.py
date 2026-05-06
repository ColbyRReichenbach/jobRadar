from __future__ import annotations

from backend.services.research_radar.llm import verify_report_with_metrics


async def verify_report_node(state):
    evidence_items = state.get("evidence_items", [])
    verification_result, llm_call = await verify_report_with_metrics(
        state["normalized_brief"],
        state.get("report_sections", []),
        evidence_items,
        db_session=state.get("db"),
        user_id=state.get("user_id"),
    )
    final_report = dict(state.get("final_report", {}))
    final_report["status"] = "needs_review" if verification_result.status == "needs_review" else "published"
    if not evidence_items:
        final_report["status"] = "needs_review"
        current_confidence = final_report.get("overall_confidence")
        if current_confidence is None:
            final_report["overall_confidence"] = 0.45
        else:
            final_report["overall_confidence"] = min(float(current_confidence), 0.45)
        structured_json = dict(final_report.get("structured_json") or {})
        structured_json["no_evidence_captured"] = True
        structured_json["review_reason"] = "no_research_evidence"
        final_report["structured_json"] = structured_json
    result = {
        "verification_result": verification_result.model_dump(),
        "final_report": final_report,
    }
    if llm_call:
        result["_llm_calls"] = [llm_call]
    return result
