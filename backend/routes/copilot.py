from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies import verify_api_key
from backend.models import CopilotConversation, CopilotFeedback, CopilotMessage
from backend.services.copilot.budget import enforce_copilot_budget
from backend.services.copilot.config import copilot_enabled, max_conversation_messages
from backend.services.copilot.guardrails import enforce_copilot_rate_limit, validate_user_message
from backend.services.copilot.orchestrator import CopilotModelUnavailableError, answer_copilot_question
from backend.services.copilot.schemas import serialize_conversation, serialize_feedback, serialize_message
from backend.services.experiments import record_feedback_reward_event
from backend.services.search.indexer import search_user_documents

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1)
    source_types: list[str] | None = None


class CopilotSearchPayload(BaseModel):
    query: str = Field(min_length=2)
    source_types: list[str] | None = None
    limit: int = Field(default=8, ge=1, le=25)


class FeedbackCreate(BaseModel):
    rating: str = Field(pattern="^(thumbs_up|thumbs_down)$")
    notes: str | None = Field(default=None, max_length=1000)


def _require_enabled() -> None:
    if not copilot_enabled():
        raise HTTPException(status_code=403, detail="Copilot is disabled")


def _require_dashboard_user(auth: dict) -> uuid.UUID:
    if auth.get("auth_type") != "jwt":
        raise HTTPException(status_code=403, detail="Dashboard session required")
    try:
        return uuid.UUID(str(auth["user_id"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Authentication required") from exc


async def _get_conversation(db: AsyncSession, *, user_id: uuid.UUID, conversation_id: str) -> CopilotConversation:
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    conversation = (
        await db.execute(
            select(CopilotConversation).where(
                CopilotConversation.id == cid,
                CopilotConversation.user_id == user_id,
            )
        )
    ).scalars().first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/conversations", status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    _require_enabled()
    user_id = _require_dashboard_user(auth)
    now = datetime.now(timezone.utc)
    conversation = CopilotConversation(
        user_id=user_id,
        title=(payload.title or "New conversation").strip() or "New conversation",
        updated_at=now,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return {"conversation": serialize_conversation(conversation)}


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    _require_enabled()
    user_id = _require_dashboard_user(auth)
    rows = (
        await db.execute(
            select(CopilotConversation)
            .where(CopilotConversation.user_id == user_id)
            .order_by(CopilotConversation.updated_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {"conversations": [serialize_conversation(row) for row in rows]}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    _require_enabled()
    user_id = _require_dashboard_user(auth)
    conversation = await _get_conversation(db, user_id=user_id, conversation_id=conversation_id)
    messages = (
        await db.execute(
            select(CopilotMessage)
            .where(CopilotMessage.user_id == user_id, CopilotMessage.conversation_id == conversation.id)
            .order_by(CopilotMessage.created_at.asc())
        )
    ).scalars().all()
    return {
        "conversation": serialize_conversation(conversation),
        "messages": [serialize_message(message) for message in messages],
    }


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def create_message(
    conversation_id: str,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    _require_enabled()
    user_id = _require_dashboard_user(auth)
    enforce_copilot_rate_limit(user_id)
    await enforce_copilot_budget(db, user_id=user_id)
    content = validate_user_message(payload.content)
    conversation = await _get_conversation(db, user_id=user_id, conversation_id=conversation_id)

    existing_count = (
        await db.execute(
            select(CopilotMessage.id).where(
                CopilotMessage.user_id == user_id,
                CopilotMessage.conversation_id == conversation.id,
            )
        )
    ).scalars().all()
    if len(existing_count) >= max_conversation_messages():
        raise HTTPException(status_code=413, detail="Copilot conversation is too long")

    now = datetime.now(timezone.utc)
    user_message = CopilotMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        content=content,
    )
    db.add(user_message)
    await db.flush()

    try:
        answer = await answer_copilot_question(
            db,
            user_id=user_id,
            conversation=conversation,
            question=content,
            source_types=payload.source_types,
        )
    except CopilotModelUnavailableError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail="Copilot is temporarily unavailable. OpenAI-backed answers are required.") from exc
    assistant_message = CopilotMessage(
        conversation_id=conversation.id,
        user_id=user_id,
        role="assistant",
        content=answer["answer"],
        citations=answer.get("citations", []),
        suggested_actions=answer.get("suggested_actions", []),
        metadata_json={
            "mode": answer.get("mode"),
            "model": answer.get("model"),
            "prompt_version": answer.get("prompt_version"),
        },
        model_call_id=uuid.UUID(answer["model_call_id"]) if answer.get("model_call_id") else None,
    )
    db.add(assistant_message)
    conversation.updated_at = now
    conversation.last_message_at = now
    if conversation.title == "New conversation":
        conversation.title = content[:80]
    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    await db.refresh(conversation)
    return {
        "conversation": serialize_conversation(conversation),
        "user_message": serialize_message(user_message),
        "assistant_message": serialize_message(assistant_message),
    }


@router.post("/search")
async def copilot_search(
    payload: CopilotSearchPayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    _require_enabled()
    user_id = _require_dashboard_user(auth)
    enforce_copilot_rate_limit(user_id)
    query = validate_user_message(payload.query)
    results = await search_user_documents(
        db,
        user_id=user_id,
        query=query,
        source_types=payload.source_types,
        limit=payload.limit,
    )
    return {"results": [result.to_dict() for result in results]}


@router.post("/messages/{message_id}/feedback", status_code=201)
async def create_feedback(
    message_id: str,
    payload: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    _require_enabled()
    user_id = _require_dashboard_user(auth)
    try:
        mid = uuid.UUID(message_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Message not found") from exc
    message = (
        await db.execute(
            select(CopilotMessage).where(
                CopilotMessage.id == mid,
                CopilotMessage.user_id == user_id,
                CopilotMessage.role == "assistant",
            )
        )
    ).scalars().first()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    feedback = (
        await db.execute(
            select(CopilotFeedback).where(
                CopilotFeedback.user_id == user_id,
                CopilotFeedback.message_id == message.id,
            )
        )
    ).scalars().first()
    if feedback is None:
        feedback = CopilotFeedback(user_id=user_id, message_id=message.id, rating=payload.rating, notes=payload.notes)
        db.add(feedback)
    else:
        feedback.rating = payload.rating
        feedback.notes = payload.notes
    await db.flush()
    await record_feedback_reward_event(db, feedback=feedback)
    await db.commit()
    await db.refresh(feedback)
    return {"feedback": serialize_feedback(feedback)}
