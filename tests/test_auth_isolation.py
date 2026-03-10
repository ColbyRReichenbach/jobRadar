import uuid

import pytest

from tests.conftest import AUTH_HEADER, TEST_USER_ID, make_auth_header


@pytest.mark.asyncio
async def test_jobs_list_is_scoped_to_authenticated_user(client, db_session):
    from backend.models import Application, User

    other_user_id = uuid.uuid4()
    db_session.add(
        User(
            id=other_user_id,
            google_id="other-google-id",
            email="other-user@apptrail.test",
            name="Other User",
        )
    )
    db_session.add_all(
        [
            Application(user_id=TEST_USER_ID, company="MyCo", role_title="Engineer"),
            Application(user_id=other_user_id, company="OtherCo", role_title="Designer"),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/jobs", headers=AUTH_HEADER)

    assert response.status_code == 200
    companies = {row["company"] for row in response.json()}
    assert "MyCo" in companies
    assert "OtherCo" not in companies


@pytest.mark.asyncio
async def test_cannot_update_another_users_application(client, db_session):
    from backend.models import Application, User

    other_user_id = uuid.uuid4()
    db_session.add(
        User(
            id=other_user_id,
            google_id="mutate-google-id",
            email="mutate-user@apptrail.test",
            name="Mutate User",
        )
    )
    app = Application(user_id=other_user_id, company="PrivateCo", role_title="Analyst")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    response = await client.patch(
        f"/api/jobs/{app.id}",
        json={"status": "offer"},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_shared_api_key_cannot_access_user_owned_routes(client):
    from tests.conftest import API_KEY_HEADER

    response = await client.get("/api/jobs", headers=API_KEY_HEADER)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_other_users_contact_detail_is_hidden(client, db_session):
    from backend.models import Application, Contact, User

    other_user_id = uuid.uuid4()
    other_auth = make_auth_header(other_user_id, email="contact-user@apptrail.test", name="Contact User")
    db_session.add(
        User(
            id=other_user_id,
            google_id="contact-google-id",
            email="contact-user@apptrail.test",
            name="Contact User",
        )
    )
    app = Application(user_id=other_user_id, company="ContactCo", role_title="Recruiter")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    db_session.add(
        Contact(
            user_id=other_user_id,
            application_id=app.id,
            name="Hidden Person",
            email="hidden@contactco.com",
        )
    )
    await db_session.commit()

    own_response = await client.get("/api/network/hidden@contactco.com", headers=AUTH_HEADER)
    other_response = await client.get("/api/network/hidden@contactco.com", headers=other_auth)

    assert own_response.status_code == 200
    assert own_response.json()["contact"] == {"email": "hidden@contactco.com"}
    assert other_response.status_code == 200
    assert other_response.json()["contact"]["name"] == "Hidden Person"
