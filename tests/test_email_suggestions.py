from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_application_suggestion_accept_links_source_emails(client, db_session):
    from backend.models import Application, ApplicationSuggestionDecision, EmailEvent

    email = EmailEvent(
        sender="Acme Recruiting",
        sender_email="recruiting@acme.com",
        sender_domain="acme.com",
        subject="Thank you for applying for Data Scientist role at Acme Analytics",
        body="We received your application for the Data Scientist role at Acme Analytics.",
        snippet="We received your application for the Data Scientist role.",
        classification="job_update",
        company_name="Acme Analytics",
        confidence=0.91,
        received_at=datetime(2026, 3, 12, 15, 30, tzinfo=timezone.utc),
    )
    db_session.add(email)
    await db_session.commit()
    await db_session.refresh(email)

    list_resp = await client.get("/api/application-suggestions", headers=AUTH_HEADER)
    assert list_resp.status_code == 200
    suggestions = list_resp.json()
    assert len(suggestions) == 1
    assert suggestions[0]["company"] == "Acme Analytics"
    assert "Data Scientist" in suggestions[0]["role_title"]

    accept_resp = await client.post(
        "/api/application-suggestions/accept",
        headers=AUTH_HEADER,
        json={
            "suggestion_key": suggestions[0]["suggestion_key"],
            "email_ids": suggestions[0]["email_ids"],
            "company": suggestions[0]["company"],
            "role_title": suggestions[0]["role_title"],
            "status": suggestions[0]["status"],
            "source": suggestions[0]["source"],
            "notes": suggestions[0]["notes"],
        },
    )
    assert accept_resp.status_code == 201
    data = accept_resp.json()
    assert data["linked_email_count"] == 1
    assert data["application"]["company"] == "Acme Analytics"

    await db_session.refresh(email)
    app = (await db_session.execute(select(Application))).scalar_one()
    refreshed_email = email
    decision = (await db_session.execute(select(ApplicationSuggestionDecision))).scalar_one()
    assert refreshed_email.application_id == app.id
    assert refreshed_email.resolved is True
    assert decision.decision == "accepted"
    assert decision.application_id == app.id

    after_resp = await client.get("/api/application-suggestions", headers=AUTH_HEADER)
    assert after_resp.status_code == 200
    assert after_resp.json() == []


@pytest.mark.asyncio
async def test_application_suggestion_dismiss_is_persistent(client, db_session):
    from backend.models import ApplicationSuggestionDecision, EmailEvent

    email = EmailEvent(
        sender="Globex Careers",
        sender_email="jobs@globex.com",
        sender_domain="globex.com",
        subject="Application update for Machine Learning Engineer role",
        body="Your Machine Learning Engineer application is under review.",
        classification="job_update",
        company_name="Globex",
        received_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(email)
    await db_session.commit()

    suggestions = (await client.get("/api/application-suggestions", headers=AUTH_HEADER)).json()
    assert len(suggestions) == 1

    dismiss_resp = await client.post(
        "/api/application-suggestions/dismiss",
        headers=AUTH_HEADER,
        json={
            "suggestion_key": suggestions[0]["suggestion_key"],
            "email_ids": suggestions[0]["email_ids"],
        },
    )
    assert dismiss_resp.status_code == 200

    decision = (await db_session.execute(select(ApplicationSuggestionDecision))).scalar_one()
    assert decision.decision == "dismissed"
    assert (await client.get("/api/application-suggestions", headers=AUTH_HEADER)).json() == []


@pytest.mark.asyncio
async def test_interview_suggestion_accept_creates_calendar_item(client, db_session):
    from backend.models import EmailEvent, Interview, InterviewSuggestionDecision

    email = EmailEvent(
        sender="Jane Recruiter",
        sender_email="jane@bankco.com",
        sender_domain="bankco.com",
        subject="Interview scheduled - January 15, 2026 at 2:00 PM",
        body="Your interview is scheduled for January 15, 2026 at 2:00 PM for 45 minutes. Join at https://zoom.us/j/test123",
        snippet="Your interview is scheduled for January 15, 2026 at 2:00 PM.",
        classification="interview_request",
        company_name="BankCo",
        confidence=0.93,
        received_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(email)
    await db_session.commit()
    await db_session.refresh(email)

    suggestions_resp = await client.get("/api/interview-suggestions", headers=AUTH_HEADER)
    assert suggestions_resp.status_code == 200
    suggestions = suggestions_resp.json()
    assert len(suggestions) == 1
    assert suggestions[0]["email_id"] == str(email.id)
    assert suggestions[0]["duration_minutes"] == 45

    accept_resp = await client.post(
        f"/api/interview-suggestions/{email.id}/accept",
        headers=AUTH_HEADER,
        json={},
    )
    assert accept_resp.status_code == 201
    interview_data = accept_resp.json()
    assert interview_data["interviewer_email"] == "jane@bankco.com"
    assert interview_data["duration_minutes"] == 45

    await db_session.refresh(email)
    interview = (await db_session.execute(select(Interview))).scalar_one()
    refreshed_email = email
    decision = (await db_session.execute(select(InterviewSuggestionDecision))).scalar_one()
    assert refreshed_email.resolved is True
    assert decision.decision == "accepted"
    assert decision.interview_id == interview.id
    assert (await client.get("/api/interview-suggestions", headers=AUTH_HEADER)).json() == []


@pytest.mark.asyncio
async def test_interview_suggestion_dismiss_is_persistent(client, db_session):
    from backend.models import EmailEvent, InterviewSuggestionDecision

    email = EmailEvent(
        sender="Recruiter",
        sender_email="recruiter@examplecorp.com",
        subject="Interview request",
        body="Can you interview on January 15, 2026 at 2:00 PM?",
        classification="interview_request",
        company_name="Example Corp",
    )
    db_session.add(email)
    await db_session.commit()
    await db_session.refresh(email)

    dismiss_resp = await client.post(
        f"/api/interview-suggestions/{email.id}/dismiss",
        headers=AUTH_HEADER,
    )
    assert dismiss_resp.status_code == 200

    decision = (await db_session.execute(select(InterviewSuggestionDecision))).scalar_one()
    assert decision.decision == "dismissed"
    assert (await client.get("/api/interview-suggestions", headers=AUTH_HEADER)).json() == []
