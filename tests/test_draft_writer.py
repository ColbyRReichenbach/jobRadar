"""Sprint 14: Tests for AI-drafted communications."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_fallback_draft():
    """Fallback templates produce valid output."""
    from backend.services.draft_writer import _fallback_draft

    draft = _fallback_draft("follow_up", company="TestCo", role="Engineer")
    assert "TestCo" in draft["body"]
    assert "Engineer" in draft["subject"]
    assert draft["draft_type"] == "follow_up"

    intro = _fallback_draft("introduction", company="AcmeCo", role="Designer", contact_name="Jane")
    assert "Jane" in intro["body"]

    thank = _fallback_draft("thank_you", company="BigCo", role="PM")
    assert "Thank you" in thank["subject"]
    assert "BigCo" in thank["body"]


@pytest.mark.asyncio
async def test_generate_draft_uses_fallback():
    """generate_draft falls back to template when LLM unavailable."""
    from backend.services.draft_writer import generate_draft

    # With no API key set, it should fall back to template
    with patch("backend.services.draft_writer.with_retry", side_effect=Exception("No API key")):
        draft = await generate_draft(
            draft_type="follow_up",
            company="FallbackCo",
            role="SWE",
        )
    assert draft["draft_type"] == "follow_up"
    assert "FallbackCo" in draft["body"]
    assert draft.get("is_template") is True


@pytest.mark.asyncio
async def test_generate_draft_endpoint(client, db_session):
    """POST /api/drafts/generate returns a draft."""
    from backend.models import Application

    app = Application(company="DraftCo", role_title="Engineer")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    with patch("backend.services.draft_writer.with_retry", side_effect=Exception("No API")):
        resp = await client.post(
            "/api/drafts/generate",
            json={
                "application_id": str(app.id),
                "draft_type": "follow_up",
            },
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "subject" in data
    assert "body" in data
    assert "DraftCo" in data["body"]


@pytest.mark.asyncio
async def test_generate_draft_introduction(client):
    """Draft generation for introduction type."""
    with patch("backend.services.draft_writer.with_retry", side_effect=Exception("No API")):
        resp = await client.post(
            "/api/drafts/generate",
            json={
                "draft_type": "introduction",
                "contact_email": "recruiter@test.com",
            },
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["draft_type"] == "introduction"


@pytest.mark.asyncio
async def test_generate_draft_with_conversation_history(client, db_session):
    """Draft generation includes conversation history context."""
    from backend.models import Application, EmailEvent, Contact

    app = Application(company="HistoryCo", role_title="PM")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    contact = Contact(
        application_id=app.id,
        name="Sarah Recruiter",
        email="sarah@historyco.com",
        source="email",
    )
    db_session.add(contact)

    email = EmailEvent(
        application_id=app.id,
        sender="Sarah Recruiter",
        sender_email="sarah@historyco.com",
        subject="Re: PM Position",
        snippet="Thanks for applying!",
        is_from_user=False,
    )
    db_session.add(email)
    await db_session.commit()

    with patch("backend.services.draft_writer.with_retry", side_effect=Exception("No API")):
        resp = await client.post(
            "/api/drafts/generate",
            json={
                "application_id": str(app.id),
                "contact_email": "sarah@historyco.com",
                "draft_type": "reply",
            },
            headers=AUTH_HEADER,
        )
    assert resp.status_code == 200
