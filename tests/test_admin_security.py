import uuid

import pytest
from sqlalchemy import select

from backend.models import ExtractionReport, User
from tests.conftest import make_auth_header


async def _create_non_admin_user(db_session):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        google_id=f"google-{user_id}",
        email=f"user-{user_id}@apptrail.test",
        name="Normal User",
        is_admin=False,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_non_admin_cannot_read_extraction_admin_views(client, db_session):
    user = await _create_non_admin_user(db_session)

    response = await client.get(
        "/api/extraction-reports",
        headers=make_auth_header(user.id, user.email, user.name),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_read_ai_metrics(client, db_session):
    user = await _create_non_admin_user(db_session)

    response = await client.get(
        "/api/ai/metrics",
        headers=make_auth_header(user.id, user.email, user.name),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_auth_me_reports_env_admin_allowlist(client, db_session, monkeypatch):
    user = await _create_non_admin_user(db_session)
    monkeypatch.setenv("APPTRAIL_ADMIN_EMAILS", user.email)

    response = await client.get(
        "/api/auth/me",
        headers=make_auth_header(user.id, user.email, user.name),
    )

    assert response.status_code == 200
    assert response.json()["is_admin"] is True


@pytest.mark.asyncio
async def test_authenticated_user_can_create_owned_extraction_report(client, db_session):
    user = await _create_non_admin_user(db_session)

    response = await client.post(
        "/api/extraction-reports",
        json={"report_type": "missing_data", "url": "https://example.com/jobs/123"},
        headers=make_auth_header(user.id, user.email, user.name),
    )

    assert response.status_code == 201
    report_id = uuid.UUID(response.json()["id"])
    result = await db_session.execute(select(ExtractionReport).where(ExtractionReport.id == report_id))
    report = result.scalar_one()
    assert report.user_id == user.id
