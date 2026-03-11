from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_jobs_list_supports_limit_and_offset(client, db_session):
    from backend.models import Application

    base_time = datetime.now(timezone.utc)
    apps = [
        Application(company="Page One", role_title="Engineer", applied_at=base_time),
        Application(company="Page Two", role_title="Engineer", applied_at=base_time + timedelta(minutes=1)),
        Application(company="Page Three", role_title="Engineer", applied_at=base_time + timedelta(minutes=2)),
    ]
    db_session.add_all(apps)
    await db_session.commit()

    resp = await client.get("/api/jobs?limit=2&offset=1", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["company"] for item in data] == ["Page Two", "Page One"]


@pytest.mark.asyncio
async def test_jobs_list_rejects_page_size_above_max(client):
    resp = await client.get("/api/jobs?limit=101", headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_emails_list_supports_limit_and_offset(client, db_session):
    from backend.models import EmailEvent

    base_time = datetime.now(timezone.utc)
    emails = [
        EmailEvent(gmail_message_id="page-email-1", sender="one@example.com", sender_email="one@example.com", subject="One", received_at=base_time),
        EmailEvent(gmail_message_id="page-email-2", sender="two@example.com", sender_email="two@example.com", subject="Two", received_at=base_time + timedelta(minutes=1)),
        EmailEvent(gmail_message_id="page-email-3", sender="three@example.com", sender_email="three@example.com", subject="Three", received_at=base_time + timedelta(minutes=2)),
    ]
    db_session.add_all(emails)
    await db_session.commit()

    resp = await client.get("/api/emails?limit=2&offset=1", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["subject"] for item in data] == ["Two", "One"]


@pytest.mark.asyncio
async def test_alerts_list_supports_limit_and_offset(client, db_session):
    from backend.models import Alert

    base_time = datetime.now(timezone.utc)
    alerts = [
        Alert(alert_type="test", title="Alert One", created_at=base_time),
        Alert(alert_type="test", title="Alert Two", created_at=base_time + timedelta(minutes=1)),
        Alert(alert_type="test", title="Alert Three", created_at=base_time + timedelta(minutes=2)),
    ]
    db_session.add_all(alerts)
    await db_session.commit()

    resp = await client.get("/api/alerts?limit=2&offset=1", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["title"] for item in data] == ["Alert Two", "Alert One"]


@pytest.mark.asyncio
async def test_company_visits_support_limit_and_offset(client, db_session):
    from backend.models import CompanyVisit

    base_time = datetime.now(timezone.utc)
    visits = [
        CompanyVisit(domain="first.example", visit_count=1, first_visited_at=base_time, last_visited_at=base_time),
        CompanyVisit(domain="second.example", visit_count=2, first_visited_at=base_time, last_visited_at=base_time + timedelta(minutes=1)),
        CompanyVisit(domain="third.example", visit_count=3, first_visited_at=base_time, last_visited_at=base_time + timedelta(minutes=2)),
    ]
    db_session.add_all(visits)
    await db_session.commit()

    resp = await client.get("/api/company-visits?limit=2&offset=1", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["domain"] for item in data] == ["second.example", "first.example"]


@pytest.mark.asyncio
async def test_resume_drafts_support_limit_and_offset(client, db_session):
    from backend.models import Application, ResumeDraft

    app = Application(company="Draft Page Co", role_title="Engineer", status="applied")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    base_time = datetime.now(timezone.utc)
    drafts = [
        ResumeDraft(application_id=app.id, tailored_text="Draft One", created_at=base_time),
        ResumeDraft(application_id=app.id, tailored_text="Draft Two", created_at=base_time + timedelta(minutes=1)),
        ResumeDraft(application_id=app.id, tailored_text="Draft Three", created_at=base_time + timedelta(minutes=2)),
    ]
    db_session.add_all(drafts)
    await db_session.commit()

    resp = await client.get(
        f"/api/resume/drafts/{app.id}?limit=2&offset=1",
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["tailored_text"] for item in data] == ["Draft Two", "Draft One"]
