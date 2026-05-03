import uuid

import pytest

from backend.dependencies import hash_api_key
from backend.models import Application, CopilotConversation, CopilotMessage, User
from backend.services.copilot.guardrails import reset_rate_limit_for_tests
from backend.services.search.indexer import index_record
from tests.conftest import AUTH_HEADER, TEST_USER_ID, make_auth_header


@pytest.fixture(autouse=True)
def enable_copilot(monkeypatch):
    monkeypatch.setenv("COPILOT_ENABLED", "true")
    reset_rate_limit_for_tests()


@pytest.mark.asyncio
async def test_copilot_rejects_user_api_keys(client, db_session):
    user = await db_session.get(User, TEST_USER_ID)
    user.api_key_hash = hash_api_key("user-api-key")
    await db_session.commit()

    response = await client.post(
        "/api/copilot/conversations",
        json={},
        headers={"Authorization": "Bearer user-api-key"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Dashboard session required"


@pytest.mark.asyncio
async def test_copilot_conversation_access_is_user_scoped(client, db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="copilot-other", email="copilot-other@apptrail.test", name="Other"))
    other_conversation = CopilotConversation(user_id=other_user_id, title="Other user")
    db_session.add(other_conversation)
    await db_session.commit()

    response = await client.get(f"/api/copilot/conversations/{other_conversation.id}", headers=AUTH_HEADER)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_copilot_citations_never_include_other_users_documents(client, db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="copilot-search-other", email="copilot-search-other@apptrail.test", name="Other"))
    user_app = Application(user_id=TEST_USER_ID, company="TraceBank", role_title="Assistant Search DS", description_text="NLP search")
    other_app = Application(user_id=other_user_id, company="OtherBank", role_title="Assistant Search DS", description_text="NLP search")
    db_session.add_all([user_app, other_app])
    await db_session.flush()
    await index_record(db_session, user_app)
    await index_record(db_session, other_app)
    await db_session.commit()

    conversation_resp = await client.post("/api/copilot/conversations", json={}, headers=AUTH_HEADER)
    conversation_id = conversation_resp.json()["conversation"]["id"]
    message_resp = await client.post(
        f"/api/copilot/conversations/{conversation_id}/messages",
        json={"content": "assistant search"},
        headers=AUTH_HEADER,
    )

    citations = message_resp.json()["assistant_message"]["citations"]
    assert [citation["source_id"] for citation in citations] == [str(user_app.id)]


@pytest.mark.asyncio
async def test_copilot_feedback_cannot_target_other_users_messages(client, db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="copilot-feedback-other", email="copilot-feedback-other@apptrail.test", name="Other"))
    conversation = CopilotConversation(user_id=other_user_id, title="Other")
    db_session.add(conversation)
    await db_session.flush()
    message = CopilotMessage(conversation_id=conversation.id, user_id=other_user_id, role="assistant", content="Nope")
    db_session.add(message)
    await db_session.commit()

    response = await client.post(
        f"/api/copilot/messages/{message.id}/feedback",
        json={"rating": "thumbs_down"},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_copilot_other_user_can_only_read_own_conversation(client, db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="copilot-own-other", email="copilot-own-other@apptrail.test", name="Other"))
    conversation = CopilotConversation(user_id=TEST_USER_ID, title="Mine")
    db_session.add(conversation)
    await db_session.commit()

    response = await client.get(
        f"/api/copilot/conversations/{conversation.id}",
        headers=make_auth_header(other_user_id, email="copilot-own-other@apptrail.test"),
    )

    assert response.status_code == 404
