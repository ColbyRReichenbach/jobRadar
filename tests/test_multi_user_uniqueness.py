import uuid

import pytest

from backend.models import Application, EmailEvent, User


@pytest.mark.asyncio
async def test_same_job_url_is_allowed_for_different_users(db_session):
    user_a = User(id=uuid.uuid4(), google_id="multi-user-a", email="a@apptrail.test")
    user_b = User(id=uuid.uuid4(), google_id="multi-user-b", email="b@apptrail.test")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    db_session.add_all(
        [
            Application(user_id=user_a.id, company="Acme", role_title="Engineer", job_url="https://jobs.example.com/1"),
            Application(user_id=user_b.id, company="Acme", role_title="Engineer", job_url="https://jobs.example.com/1"),
        ]
    )

    await db_session.commit()


@pytest.mark.asyncio
async def test_same_gmail_message_id_is_allowed_for_different_users(db_session):
    user_a = User(id=uuid.uuid4(), google_id="email-user-a", email="email-a@apptrail.test")
    user_b = User(id=uuid.uuid4(), google_id="email-user-b", email="email-b@apptrail.test")
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    db_session.add_all(
        [
            EmailEvent(user_id=user_a.id, gmail_message_id="provider-message-1", sender="a@example.com"),
            EmailEvent(user_id=user_b.id, gmail_message_id="provider-message-1", sender="b@example.com"),
        ]
    )

    await db_session.commit()
