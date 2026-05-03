"""Copilot answer orchestration."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import CopilotConversation
from backend.services import ai_orchestrator, ai_safety
from backend.services.copilot.citations import InvalidCitationError, validate_model_citations
from backend.services.copilot.guardrails import sanitize_context_snippet, sanitize_suggested_actions
from backend.services.copilot.retrieval import retrieve_copilot_context
from backend.services.copilot.schemas import CopilotCitation

COPILOT_TASK = "copilot_answer"


class CopilotModelUnavailableError(RuntimeError):
    """Raised when Copilot cannot produce a governed OpenAI-backed answer."""


def search_fallback_allowed() -> bool:
    if os.getenv("TESTING") == "1":
        return True
    return os.getenv("COPILOT_ALLOW_SEARCH_FALLBACK", "false").lower() == "true"


def build_copilot_prompt(*, question: str, citations: list[CopilotCitation]) -> str:
    context = [
        {
            "document_id": str(item.document_id),
            "source_type": item.source_type,
            "source_id": str(item.source_id),
            "title": item.title,
            "snippet": item.snippet,
        }
        for item in citations
    ]
    return json.dumps(
        {
            "question": question,
            "retrieved_context": context,
            "response_contract": {
                "answer": "string",
                "citations": [{"document_id": "uuid", "quote": "optional short quote"}],
                "suggested_actions": [
                    {
                        "title": "string",
                        "description": "string",
                        "action_type": "read_only_suggestion",
                        "requires_confirmation": True,
                    }
                ],
            },
            "rules": [
                "Use only retrieved_context.",
                "Cite document_id values from retrieved_context only.",
                "Do not mutate data or claim an action was performed.",
            ],
        },
        sort_keys=True,
    )


def build_search_fallback_answer(question: str, citations: list[CopilotCitation]) -> dict[str, Any]:
    if not citations:
        return {
            "answer": "I could not find matching AppTrail records for that question yet.",
            "citations": [],
            "suggested_actions": [],
            "mode": "search_fallback",
        }

    lines = ["I found these relevant AppTrail records:"]
    for index, citation in enumerate(citations[:5], start=1):
        detail = f"{index}. {citation.title} ({citation.source_type})"
        safe_snippet = sanitize_context_snippet(citation.snippet)
        if safe_snippet:
            detail += f": {safe_snippet}"
        lines.append(detail)
    return {
        "answer": "\n".join(lines),
        "citations": [item.to_dict() for item in citations],
        "suggested_actions": [],
        "mode": "search_fallback",
    }


async def answer_copilot_question(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation: CopilotConversation,
    question: str,
    source_types: list[str] | None = None,
) -> dict[str, Any]:
    citations = await retrieve_copilot_context(db, user_id=user_id, query=question, source_types=source_types)
    if not ai_orchestrator.has_configured_api_key():
        if search_fallback_allowed():
            ai_orchestrator.record_fallback(COPILOT_TASK, "api_key_not_configured", {"surface": "copilot"})
            return build_search_fallback_answer(question, citations)
        raise CopilotModelUnavailableError("OPENAI_API_KEY is not configured for Copilot")

    try:
        result = await ai_safety.run_json_task_with_safety(
            COPILOT_TASK,
            build_copilot_prompt(question=question, citations=citations),
            metadata={
                "surface": "copilot",
                "user_id": str(user_id),
                "conversation_id": str(conversation.id),
                "retrieved_document_ids": [str(item.document_id) for item in citations],
            },
            db_session=db,
            user_id=str(user_id),
            data_classes=[
                ai_safety.DATA_CLASS_CAREER_PRIVATE,
                ai_safety.DATA_CLASS_UNTRUSTED_INBOUND,
                ai_safety.DATA_CLASS_USER_IDENTITY,
            ],
            allow_identity=False,
            untrusted_input=True,
            block_on_high_risk=True,
        )
        payload = result.payload
        answer = str(payload.get("answer") or "").strip()
        if not answer:
            raise ValueError("Copilot model returned an empty answer")
        validated_citations = validate_model_citations(payload.get("citations"), citations)
        if citations and not validated_citations:
            raise InvalidCitationError("model omitted citations for retrieved context")
        return {
            "answer": answer,
            "citations": validated_citations,
            "suggested_actions": sanitize_suggested_actions(payload.get("suggested_actions")),
            "mode": "model",
            "model": result.model,
            "prompt_version": result.prompt_version,
            "model_call_id": str(result.model_call_id) if result.model_call_id else None,
        }
    except Exception as exc:  # noqa: BLE001
        if search_fallback_allowed():
            ai_orchestrator.record_fallback(COPILOT_TASK, "model_failure_or_invalid_citation", {"surface": "copilot", "error": str(exc)[:300]})
            return build_search_fallback_answer(question, citations)
        raise CopilotModelUnavailableError("Copilot OpenAI answer failed validation or generation") from exc
