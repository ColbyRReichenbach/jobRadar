import pytest
import uuid
from sqlalchemy import select

from backend.models import Application, CopilotMessage
from backend.services.copilot.guardrails import reset_rate_limit_for_tests
from backend.services.search.indexer import index_record
from tests.conftest import AUTH_HEADER, TEST_USER_ID


@pytest.fixture(autouse=True)
def enable_copilot(monkeypatch):
    monkeypatch.setenv("COPILOT_ENABLED", "true")
    reset_rate_limit_for_tests()


async def _seed_search_doc(db_session):
    app = Application(
        user_id=TEST_USER_ID,
        company="TraceBank",
        role_title="Assistant Search Data Scientist",
        description_text="Build NLP search quality models for assistant conversations.",
    )
    db_session.add(app)
    await db_session.flush()
    await index_record(db_session, app)
    await db_session.commit()
    return app


@pytest.mark.asyncio
async def test_copilot_conversation_message_returns_search_fallback_with_citations(client, db_session):
    app = await _seed_search_doc(db_session)
    conversation_resp = await client.post("/api/copilot/conversations", json={"title": "Interview prep"}, headers=AUTH_HEADER)
    assert conversation_resp.status_code == 201
    conversation_id = conversation_resp.json()["conversation"]["id"]

    message_resp = await client.post(
        f"/api/copilot/conversations/{conversation_id}/messages",
        json={"content": "What assistant search roles am I tracking?"},
        headers=AUTH_HEADER,
    )

    assert message_resp.status_code == 201
    payload = message_resp.json()
    assert payload["assistant_message"]["metadata"]["mode"] == "search_fallback"
    assert payload["assistant_message"]["citations"][0]["source_id"] == str(app.id)
    assert "TraceBank" in payload["assistant_message"]["content"]

    saved_messages = (
        await db_session.execute(select(CopilotMessage).where(CopilotMessage.conversation_id == uuid.UUID(conversation_id)))
    ).scalars().all()
    assert [message.role for message in saved_messages] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_copilot_fails_closed_without_openai_when_fallback_disabled(client, db_session, monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("COPILOT_ALLOW_SEARCH_FALLBACK", "false")

    await _seed_search_doc(db_session)
    conversation_resp = await client.post("/api/copilot/conversations", json={"title": "Interview prep"}, headers=AUTH_HEADER)
    assert conversation_resp.status_code == 201
    conversation_id = conversation_resp.json()["conversation"]["id"]

    message_resp = await client.post(
        f"/api/copilot/conversations/{conversation_id}/messages",
        json={"content": "What assistant search roles am I tracking?"},
        headers=AUTH_HEADER,
    )

    assert message_resp.status_code == 503
    assert message_resp.json()["detail"] == "Copilot is temporarily unavailable. OpenAI-backed answers are required."


@pytest.mark.asyncio
async def test_copilot_lists_reads_searches_and_records_feedback(client, db_session):
    await _seed_search_doc(db_session)
    conversation_resp = await client.post("/api/copilot/conversations", json={}, headers=AUTH_HEADER)
    conversation_id = conversation_resp.json()["conversation"]["id"]
    message_resp = await client.post(
        f"/api/copilot/conversations/{conversation_id}/messages",
        json={"content": "assistant search"},
        headers=AUTH_HEADER,
    )
    assistant_id = message_resp.json()["assistant_message"]["id"]

    list_resp = await client.get("/api/copilot/conversations", headers=AUTH_HEADER)
    detail_resp = await client.get(f"/api/copilot/conversations/{conversation_id}", headers=AUTH_HEADER)
    search_resp = await client.post("/api/copilot/search", json={"query": "assistant search"}, headers=AUTH_HEADER)
    feedback_resp = await client.post(
        f"/api/copilot/messages/{assistant_id}/feedback",
        json={"rating": "thumbs_up", "notes": "Grounded answer"},
        headers=AUTH_HEADER,
    )

    assert list_resp.status_code == 200
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["messages"]) == 2
    assert search_resp.status_code == 200
    assert search_resp.json()["results"][0]["source_type"] == "application"
    assert feedback_resp.status_code == 201
    assert feedback_resp.json()["feedback"]["rating"] == "thumbs_up"


@pytest.mark.asyncio
async def test_copilot_disabled_flag_blocks_access(client, monkeypatch):
    monkeypatch.setenv("COPILOT_ENABLED", "false")

    response = await client.post("/api/copilot/conversations", json={}, headers=AUTH_HEADER)

    assert response.status_code == 403
    assert response.json()["detail"] == "Copilot is disabled"
