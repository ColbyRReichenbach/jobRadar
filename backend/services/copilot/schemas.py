"""Copilot response schemas and serializers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, asdict
from typing import Any

from backend.models import CopilotConversation, CopilotFeedback, CopilotMessage


@dataclass(frozen=True)
class CopilotCitation:
    document_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    title: str
    snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["document_id"] = str(self.document_id)
        payload["source_id"] = str(self.source_id)
        return payload


def serialize_conversation(conversation: CopilotConversation) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "status": conversation.status,
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
        "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
    }


def serialize_message(message: CopilotMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "role": message.role,
        "content": message.content,
        "citations": message.citations or [],
        "suggested_actions": message.suggested_actions or [],
        "metadata": message.metadata_json or {},
        "model_call_id": str(message.model_call_id) if message.model_call_id else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def serialize_feedback(feedback: CopilotFeedback) -> dict[str, Any]:
    return {
        "id": str(feedback.id),
        "message_id": str(feedback.message_id),
        "rating": feedback.rating,
        "notes": feedback.notes,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }
