import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_feedback_moves_conversation_to_inbox(client, db_session):
    from backend.models import EmailEvent, EmailFeedback
    from sqlalchemy import select

    email = EmailEvent(
        gmail_message_id="feedback-move-inbox-1",
        sender="Recruiter",
        sender_email="recruiter@example.com",
        subject="Your interview is scheduled",
        classification="conversation",
        email_type="conversation",
        is_human=True,
    )
    db_session.add(email)
    await db_session.commit()
    await db_session.refresh(email)

    resp = await client.post(
        "/api/emails/feedback",
        json={
            "email_id": str(email.id),
            "is_job_related": True,
            "feedback_action": "move_to_inbox",
            "corrected_route": "application_inbox",
            "corrected_subtype": "interview_request",
            "feedback_label": "interview_request",
            "source_surface": "conversation",
        },
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 201
    assert resp.json()["email_type"] == "decision"
    assert resp.json()["classification"] == "interview_request"

    await db_session.refresh(email)
    assert email.email_type == "decision"
    assert email.classification == "interview_request"
    assert email.hidden is False

    feedback = (await db_session.execute(select(EmailFeedback))).scalar_one()
    assert feedback.predicted_route == "conversation"
    assert feedback.corrected_route == "application_inbox"
    assert feedback.corrected_subtype == "interview_request"


@pytest.mark.asyncio
async def test_feedback_filters_not_conversation_related_email(client, db_session):
    from backend.models import EmailEvent

    email = EmailEvent(
        gmail_message_id="feedback-filter-1",
        sender="Marketing",
        sender_email="promo@example.com",
        subject="Weekly opportunities digest",
        classification="conversation",
        email_type="conversation",
        is_human=True,
    )
    db_session.add(email)
    await db_session.commit()
    await db_session.refresh(email)

    resp = await client.post(
        "/api/emails/feedback",
        json={
            "email_id": str(email.id),
            "is_job_related": False,
            "feedback_action": "not_relevant",
            "corrected_route": "filter",
            "corrected_subtype": "job_board_promo",
            "feedback_label": "job_board_promo",
            "source_surface": "conversation",
        },
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 201
    await db_session.refresh(email)
    assert email.hidden is True
    assert email.collapsed is True
    assert email.email_type is None
    assert email.classification == "not_relevant"
