import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_create_application_rejects_overlong_description(client):
    response = await client.post(
        "/api/jobs",
        json={
            "company": "TooLongCo",
            "role_title": "Engineer",
            "description_text": "x" * 10001,
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_email_rejects_overlong_body(client):
    response = await client.post(
        "/api/emails/send",
        json={
            "to": "person@example.com",
            "subject": "Hello",
            "body": "x" * 10001,
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_resume_parse_rejects_overlong_text(client):
    response = await client.post(
        "/api/resume/parse",
        json={"text": "x" * 50001},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 422
