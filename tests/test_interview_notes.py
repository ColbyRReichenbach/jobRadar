"""Sprint 18: Tests for interview notes / second brain."""

import uuid

import pytest
from datetime import datetime, timezone, timedelta
from tests.conftest import AUTH_HEADER, make_auth_header


@pytest.mark.asyncio
async def test_create_interview_note(client, db_session):
    """POST /api/interviews/{id}/notes creates a note."""
    from backend.models import Interview, Application

    app = Application(company="NoteCo", role_title="Engineer", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    interview = Interview(
        application_id=app.id,
        interview_type="phone",
        scheduled_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    resp = await client.post(
        f"/api/interviews/{interview.id}/notes",
        json={
            "questions_asked": "Tell me about yourself",
            "went_well": "Good rapport with interviewer",
            "to_improve": "Should have asked more questions",
            "overall_feeling": "good",
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["questions_asked"] == "Tell me about yourself"
    assert data["went_well"] == "Good rapport with interviewer"
    assert data["overall_feeling"] == "good"
    assert data["interview_id"] == str(interview.id)


@pytest.mark.asyncio
async def test_list_interview_notes(client, db_session):
    """GET /api/interviews/{id}/notes returns notes for that interview."""
    from backend.models import Interview, InterviewNote

    interview = Interview(interview_type="technical")
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    note1 = InterviewNote(
        interview_id=interview.id,
        questions_asked="System design question",
        overall_feeling="great",
    )
    note2 = InterviewNote(
        interview_id=interview.id,
        went_well="Solved the coding challenge",
        overall_feeling="good",
    )
    db_session.add_all([note1, note2])
    await db_session.commit()

    resp = await client.get(f"/api/interviews/{interview.id}/notes", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_update_interview_note(client, db_session):
    """PATCH /api/interviews/notes/{id} updates a note."""
    from backend.models import Interview, InterviewNote

    interview = Interview(interview_type="onsite")
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    note = InterviewNote(
        interview_id=interview.id,
        overall_feeling="okay",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    resp = await client.patch(
        f"/api/interviews/notes/{note.id}",
        json={"overall_feeling": "great", "went_well": "Actually it went really well"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_feeling"] == "great"
    assert data["went_well"] == "Actually it went really well"


@pytest.mark.asyncio
async def test_delete_interview_note(client, db_session):
    """DELETE /api/interviews/notes/{id} deletes a note."""
    from backend.models import Interview, InterviewNote

    interview = Interview(interview_type="panel")
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    note = InterviewNote(interview_id=interview.id, overall_feeling="poor")
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)

    resp = await client.delete(f"/api/interviews/notes/{note.id}", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify it's gone
    resp2 = await client.get(f"/api/interviews/{interview.id}/notes", headers=AUTH_HEADER)
    assert resp2.status_code == 200
    assert len(resp2.json()) == 0


@pytest.mark.asyncio
async def test_create_note_interview_not_found(client):
    """POST /api/interviews/{bad_id}/notes returns 404."""
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/interviews/{fake_id}/notes",
        json={"overall_feeling": "good"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_past_due_interviews(client, db_session):
    """GET /api/interviews/past-due returns interviews without notes."""
    from backend.models import Interview, Application

    app = Application(company="PastDueCo", role_title="Dev", status="interviewing")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    # Past interview with no notes
    past_interview = Interview(
        application_id=app.id,
        interview_type="phone",
        scheduled_at=datetime.now(timezone.utc) - timedelta(days=1),
        outcome="pending",
    )
    db_session.add(past_interview)
    await db_session.commit()

    resp = await client.get("/api/interviews/past-due", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    ids = [d["id"] for d in data]
    assert str(past_interview.id) in ids
    # Should include company_name from the application
    match = [d for d in data if d["id"] == str(past_interview.id)][0]
    assert match["company_name"] == "PastDueCo"


@pytest.mark.asyncio
async def test_past_due_excludes_noted(client, db_session):
    """Past-due interviews with notes are not returned."""
    from backend.models import Interview, InterviewNote

    interview = Interview(
        interview_type="technical",
        scheduled_at=datetime.now(timezone.utc) - timedelta(days=2),
        outcome="pending",
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    # Add a note
    note = InterviewNote(interview_id=interview.id, overall_feeling="good")
    db_session.add(note)
    await db_session.commit()

    resp = await client.get("/api/interviews/past-due", headers=AUTH_HEADER)
    data = resp.json()
    ids = [d["id"] for d in data]
    assert str(interview.id) not in ids


@pytest.mark.asyncio
async def test_interview_prep(client, db_session):
    """GET /api/interviews/{id}/prep returns past notes for same company."""
    from backend.models import Interview, Application, InterviewNote

    app1 = Application(company="PrepCo", role_title="Engineer", status="interviewing")
    db_session.add(app1)
    await db_session.commit()
    await db_session.refresh(app1)

    # Old interview with notes
    old_interview = Interview(
        application_id=app1.id,
        interview_type="phone",
        scheduled_at=datetime.now(timezone.utc) - timedelta(days=30),
        outcome="passed",
    )
    db_session.add(old_interview)
    await db_session.commit()
    await db_session.refresh(old_interview)

    old_note = InterviewNote(
        interview_id=old_interview.id,
        application_id=app1.id,
        questions_asked="Why PrepCo?",
        went_well="Great culture discussion",
        overall_feeling="great",
    )
    db_session.add(old_note)
    await db_session.commit()

    # New interview at same company
    app2 = Application(company="PrepCo", role_title="Senior Engineer", status="interviewing")
    db_session.add(app2)
    await db_session.commit()
    await db_session.refresh(app2)

    new_interview = Interview(
        application_id=app2.id,
        interview_type="technical",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(new_interview)
    await db_session.commit()
    await db_session.refresh(new_interview)

    resp = await client.get(f"/api/interviews/{new_interview.id}/prep", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["past_notes"]) >= 1
    assert data["past_notes"][0]["questions_asked"] == "Why PrepCo?"


@pytest.mark.asyncio
async def test_interview_prep_scopes_company_context_to_user(client, db_session):
    """GET /api/interviews/{id}/prep should not leak another user's company context."""
    from backend.models import Application, Company, Contact, EmailEvent, Interview, InterviewNote, User, WarmConnection

    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000020")
    db_session.add(
        User(
            id=other_user_id,
            google_id="prep-other-user",
            email="prep-other@apptrail.test",
            name="Prep Other",
        )
    )

    company = Company(domain="prepco.com", name="PrepCo")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    own_app = Application(company="PrepCo", role_title="Engineer", status="interviewing", company_id=company.id)
    other_app = Application(user_id=other_user_id, company="PrepCo", role_title="Other Engineer", status="interviewing", company_id=company.id)
    db_session.add_all([own_app, other_app])
    await db_session.commit()
    await db_session.refresh(own_app)

    old_interview = Interview(
        application_id=own_app.id,
        interview_type="phone",
        scheduled_at=datetime.now(timezone.utc) - timedelta(days=10),
        outcome="passed",
    )
    next_interview = Interview(
        application_id=own_app.id,
        interview_type="technical",
        scheduled_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    db_session.add_all([old_interview, next_interview])
    await db_session.commit()
    await db_session.refresh(next_interview)

    db_session.add(
        InterviewNote(
            interview_id=old_interview.id,
            application_id=own_app.id,
            questions_asked="Why us?",
            went_well="Good examples",
            overall_feeling="good",
        )
    )
    db_session.add_all([
        Contact(
            application_id=own_app.id,
            company_id=company.id,
            name="Own Contact",
            email="own@prepco.com",
            source="hunter",
        ),
        Contact(
            user_id=other_user_id,
            application_id=other_app.id,
            company_id=company.id,
            name="Other Contact",
            email="other@prepco.com",
            source="hunter",
        ),
        EmailEvent(
            company_id=company.id,
            application_id=own_app.id,
            gmail_message_id="prep-own-email",
            sender="Own Sender",
            classification="update",
            color_code="blue",
            urgency="low",
        ),
        EmailEvent(
            user_id=other_user_id,
            company_id=company.id,
            application_id=other_app.id,
            gmail_message_id="prep-other-email",
            sender="Other Sender",
            classification="update",
            color_code="blue",
            urgency="low",
        ),
        WarmConnection(
            company_domain="prepco.com",
            contact_email="own@prepco.com",
            contact_name="Own Warm Path",
            email_count=2,
        ),
        WarmConnection(
            user_id=other_user_id,
            company_domain="prepco.com",
            contact_email="other@prepco.com",
            contact_name="Other Warm Path",
            email_count=5,
        ),
    ])
    await db_session.commit()

    resp = await client.get(f"/api/interviews/{next_interview.id}/prep", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_context"] is not None
    assert [app["role_title"] for app in data["company_context"]["applications"]] == ["Engineer"]
    assert [contact["email"] for contact in data["company_context"]["contacts"]] == ["own@prepco.com"]
    assert [email["sender"] for email in data["company_context"]["emails"]] == ["Own Sender"]
    assert [warm["contact_email"] for warm in data["company_context"]["warm_connections"]] == ["own@prepco.com"]

    other_resp = await client.get(
        f"/api/interviews/{next_interview.id}/prep",
        headers=make_auth_header(other_user_id, "prep-other@apptrail.test", "Prep Other"),
    )
    assert other_resp.status_code == 404


@pytest.mark.asyncio
async def test_interview_patterns_empty(client):
    """GET /api/interviews/patterns returns empty when no notes exist."""
    resp = await client.get("/api/interviews/patterns", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_notes"] == 0


@pytest.mark.asyncio
async def test_interview_patterns_with_data(client, db_session):
    """GET /api/interviews/patterns returns aggregated insights."""
    from backend.models import Interview, Application, InterviewNote

    app = Application(company="PatternCo", role_title="Dev", status="interviewing")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    for feeling, outcome in [("great", "passed"), ("good", "passed"), ("okay", "failed")]:
        interview = Interview(
            application_id=app.id,
            interview_type="phone",
            outcome=outcome,
        )
        db_session.add(interview)
        await db_session.commit()
        await db_session.refresh(interview)

        note = InterviewNote(
            interview_id=interview.id,
            application_id=app.id,
            overall_feeling=feeling,
        )
        db_session.add(note)
    await db_session.commit()

    resp = await client.get("/api/interviews/patterns", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_notes"] == 3
    assert "great" in data["feeling_distribution"]
    assert "phone" in data["outcome_by_type"]
    assert data["outcome_by_type"]["phone"]["total"] == 3
    assert len(data["company_performance"]) >= 1
    assert data["company_performance"][0]["company"] == "PatternCo"
