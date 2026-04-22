from __future__ import annotations

from backend.services.research_radar.llm import extract_evidence


async def extract_evidence_node(state):
    normalized_brief = state["normalized_brief"]
    evidence_items: list[dict] = []
    for source_item in state.get("source_items", []):
        extracted = await extract_evidence(normalized_brief, source_item)
        for item in extracted:
            evidence_items.append(item.model_dump())
    return {"evidence_items": evidence_items}
