"""Sprint 20: Tests for resume tailoring endpoints."""

import pytest
from unittest.mock import patch, AsyncMock
from tests.conftest import AUTH_HEADER


MOCK_TAILOR_RESULT = {
    "tailored_text": "Tailored resume content emphasizing Python and cloud experience",
    "changes_summary": "- Reordered skills to lead with Python\n- Emphasized cloud deployment experience",
    "match_improvements": "Python, AWS, distributed systems",
}

SAMPLE_RESUME = """John Doe
Software Engineer

Skills: Python, JavaScript, AWS, Docker, PostgreSQL

Experience:
- Built REST APIs using FastAPI
- Deployed services on AWS ECS
- Managed PostgreSQL databases
"""

SAMPLE_JOB_DESC = """We are looking for a Senior Python Developer with experience in:
- Python and FastAPI
- AWS cloud services
- Distributed systems
- PostgreSQL
"""


@pytest.mark.asyncio
async def test_tailor_resume_with_custom_text(client, db_session):
    """POST /api/resume/tailor/{id} with custom resume text."""
    from backend.models import Application

    app = Application(
        company="TailorCo",
        role_title="Python Developer",
        status="applied",
        description_text=SAMPLE_JOB_DESC,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    with patch("backend.services.resume_tailor.tailor_resume", new_callable=AsyncMock) as mock_tailor:
        mock_tailor.return_value = MOCK_TAILOR_RESULT

        resp = await client.post(
            f"/api/resume/tailor/{app.id}",
            json={"resume_text": SAMPLE_RESUME},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["tailored_text"] == MOCK_TAILOR_RESULT["tailored_text"]
        assert data["changes_summary"] == MOCK_TAILOR_RESULT["changes_summary"]
        assert data["application_id"] == str(app.id)

        mock_tailor.assert_called_once()
        call_kwargs = mock_tailor.call_args[1]
        assert call_kwargs["original_text"] == SAMPLE_RESUME
        assert "Python" in call_kwargs["job_description"]


@pytest.mark.asyncio
async def test_tailor_resume_from_profile(client, db_session):
    """POST /api/resume/tailor/{id} uses user profile when no custom text."""
    from backend.models import Application, UserProfile

    profile = UserProfile(raw_text=SAMPLE_RESUME, skills=["Python", "AWS", "Docker"])
    db_session.add(profile)

    app = Application(
        company="ProfileCo",
        role_title="DevOps Engineer",
        status="applied",
        description_text=SAMPLE_JOB_DESC,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    with patch("backend.services.resume_tailor.tailor_resume", new_callable=AsyncMock) as mock_tailor:
        mock_tailor.return_value = MOCK_TAILOR_RESULT

        resp = await client.post(
            f"/api/resume/tailor/{app.id}",
            json={},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 201

        call_kwargs = mock_tailor.call_args[1]
        assert call_kwargs["original_text"] == SAMPLE_RESUME
        assert call_kwargs["skills"] == ["Python", "AWS", "Docker"]


@pytest.mark.asyncio
async def test_tailor_no_resume_no_profile(client, db_session):
    """Returns 400 when no resume text and no profile."""
    from backend.models import Application

    app = Application(
        company="NoProfCo",
        role_title="Engineer",
        status="applied",
        description_text=SAMPLE_JOB_DESC,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.post(
        f"/api/resume/tailor/{app.id}",
        json={},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400
    assert "resume" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tailor_no_job_description(client, db_session):
    """Returns 400 when application has no job description."""
    from backend.models import Application, UserProfile

    profile = UserProfile(raw_text=SAMPLE_RESUME)
    db_session.add(profile)

    app = Application(
        company="NoDescCo",
        role_title="Engineer",
        status="applied",
        description_text=None,
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.post(
        f"/api/resume/tailor/{app.id}",
        json={},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 400
    assert "description" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_tailor_app_not_found(client):
    """Returns 404 for unknown application."""
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/resume/tailor/{fake_id}",
        json={"resume_text": "test"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_drafts(client, db_session):
    """GET /api/resume/drafts/{app_id} returns draft history."""
    from backend.models import Application, ResumeDraft

    app = Application(company="DraftCo", role_title="Dev", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    d1 = ResumeDraft(
        application_id=app.id,
        original_text="Original v1",
        tailored_text="Tailored v1",
        changes_summary="First version",
    )
    d2 = ResumeDraft(
        application_id=app.id,
        original_text="Original v2",
        tailored_text="Tailored v2",
        changes_summary="Second version",
    )
    db_session.add_all([d1, d2])
    await db_session.commit()

    resp = await client.get(f"/api/resume/drafts/{app.id}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_draft(client, db_session):
    """GET /api/resume/drafts/{app_id}/{draft_id} returns full draft."""
    from backend.models import Application, ResumeDraft

    app = Application(company="GetCo", role_title="Dev", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    draft = ResumeDraft(
        application_id=app.id,
        original_text="My original resume",
        tailored_text="My tailored resume",
        changes_summary="Reordered skills",
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(draft)

    resp = await client.get(
        f"/api/resume/drafts/{app.id}/{draft.id}", headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["original_text"] == "My original resume"
    assert data["tailored_text"] == "My tailored resume"
    assert data["changes_summary"] == "Reordered skills"


@pytest.mark.asyncio
async def test_delete_draft(client, db_session):
    """DELETE /api/resume/drafts/{app_id}/{draft_id} deletes a draft."""
    from backend.models import Application, ResumeDraft

    app = Application(company="DelCo", role_title="Dev", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    draft = ResumeDraft(
        application_id=app.id,
        tailored_text="To be deleted",
    )
    db_session.add(draft)
    await db_session.commit()
    await db_session.refresh(draft)

    resp = await client.delete(
        f"/api/resume/drafts/{app.id}/{draft.id}", headers=AUTH_HEADER
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify gone
    resp2 = await client.get(f"/api/resume/drafts/{app.id}", headers=AUTH_HEADER)
    assert len(resp2.json()) == 0


@pytest.mark.asyncio
async def test_delete_draft_not_found(client, db_session):
    """DELETE returns 404 for unknown draft."""
    import uuid
    from backend.models import Application

    app = Application(company="NotFoundCo", role_title="Dev", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.delete(
        f"/api/resume/drafts/{app.id}/{uuid.uuid4()}", headers=AUTH_HEADER
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fallback_tailor():
    """Test fallback when LLM is unavailable."""
    from backend.services.resume_tailor import _fallback_tailor

    result = _fallback_tailor("My resume text", "Engineer", "TestCo")
    assert result["tailored_text"] == "My resume text"
    assert "TestCo" in result["changes_summary"]
    assert result["is_fallback"] is True


@pytest.mark.asyncio
async def test_list_drafts_empty(client, db_session):
    """GET /api/resume/drafts/{app_id} returns empty list when no drafts."""
    from backend.models import Application

    app = Application(company="EmptyCo", role_title="Dev", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.get(f"/api/resume/drafts/{app.id}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json() == []
