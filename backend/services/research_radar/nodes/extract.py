from __future__ import annotations

from backend.services.research_radar.llm import extract_evidence_with_metrics


async def extract_evidence_node(state):
    normalized_brief = state["normalized_brief"]
    evidence_items: list[dict] = []
    llm_calls: list[dict] = []
    for source_item in state.get("source_items", []):
        extracted, llm_call = await extract_evidence_with_metrics(
            normalized_brief,
            source_item,
            db_session=state.get("db"),
            user_id=str(state.get("user_id")),
        )
        for item in extracted:
            evidence_items.append(item.model_dump())
        if llm_call:
            llm_calls.append(llm_call)
    result = {"evidence_items": evidence_items}
    if llm_calls:
        result["_llm_calls"] = llm_calls
    return result
