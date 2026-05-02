"""Citation validation for Copilot answers."""

from __future__ import annotations

import uuid
from typing import Any

from backend.services.copilot.schemas import CopilotCitation


class InvalidCitationError(ValueError):
    pass


def validate_model_citations(payload: Any, retrieved: list[CopilotCitation]) -> list[dict[str, Any]]:
    allowed = {str(item.document_id): item for item in retrieved}
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise InvalidCitationError("citations must be a list")

    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise InvalidCitationError("citation entries must be objects")
        document_id = str(item.get("document_id") or item.get("id") or "").strip()
        try:
            document_id = str(uuid.UUID(document_id))
        except ValueError as exc:
            raise InvalidCitationError("citation document_id must be a UUID") from exc
        if document_id not in allowed:
            raise InvalidCitationError("citation document_id was not retrieved for this user")
        if document_id in seen:
            continue
        seen.add(document_id)
        citation = allowed[document_id].to_dict()
        if item.get("quote"):
            citation["quote"] = str(item["quote"])[:240]
        citations.append(citation)
    return citations
