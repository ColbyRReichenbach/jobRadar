from __future__ import annotations

import logging

from backend.services.research_radar.llm import ResearchModelUnavailableError, extract_evidence_with_metrics


logger = logging.getLogger(__name__)


async def extract_evidence_node(state):
    normalized_brief = state["normalized_brief"]
    evidence_items: list[dict] = []
    llm_calls: list[dict] = []
    extraction_errors: list[dict] = []
    source_items = state.get("source_items", [])
    for source_item in source_items:
        try:
            extracted, llm_call = await extract_evidence_with_metrics(
                normalized_brief,
                source_item,
                db_session=state.get("db"),
                user_id=state.get("user_id"),
            )
        except ResearchModelUnavailableError as exc:
            source_ref = source_item.get("source_item_id") or source_item.get("source_url")
            extraction_errors.append(
                {
                    "source_item_id": source_item.get("source_item_id"),
                    "source_url": source_item.get("source_url"),
                    "error_type": exc.__class__.__name__,
                    "message": str(exc),
                }
            )
            logger.warning("research_evidence_source_failed source_ref=%s error=%s", source_ref, exc)
            continue
        for item in extracted:
            evidence_items.append(item.model_dump())
        if llm_call:
            llm_calls.append(llm_call)
    if source_items and extraction_errors and len(extraction_errors) == len(source_items):
        raise ResearchModelUnavailableError("Radar evidence extraction failed for all sources")
    result = {"evidence_items": evidence_items}
    if llm_calls:
        result["_llm_calls"] = llm_calls
    if extraction_errors:
        result["evidence_extraction_errors"] = extraction_errors
    return result
