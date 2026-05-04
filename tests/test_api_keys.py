import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_generate_api_key_stores_hash_only(client, db_session):
    from backend.dependencies import hash_api_key
    from backend.models import User
    from tests.conftest import TEST_USER_ID

    response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)

    assert response.status_code == 201
    data = response.json()
    assert data["api_key"].startswith("aptk_")
    assert data["last4"] == data["api_key"][-4:]

    user = await db_session.get(User, TEST_USER_ID)
    assert user is not None
    assert user.api_key_hash == hash_api_key(data["api_key"])
    assert user.api_key_hash != data["api_key"]
    assert user.api_key_last4 == data["last4"]


@pytest.mark.asyncio
async def test_generated_api_key_validates_and_can_create_extension_job(client):
    create_response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)
    api_key = create_response.json()["api_key"]
    api_key_header = {"Authorization": f"Bearer {api_key}"}

    validate_response = await client.post("/api/auth/api-key/validate", headers=api_key_header)
    job_response = await client.post(
        "/api/jobs",
        headers=api_key_header,
        json={"company": "ExtensionCo", "role_title": "Engineer", "job_url": "https://extensionco.com/jobs/1"},
    )

    assert validate_response.status_code == 200
    assert validate_response.json()["auth_type"] == "api_key"
    assert job_response.status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("GET", "/api/notifications/preferences", None),
        ("GET", "/api/emails", None),
        ("GET", "/api/profile", None),
        ("POST", "/api/resume/parse", {"text": "Python engineer with backend experience."}),
        ("GET", "/api/export/csv", None),
    ],
)
async def test_generated_api_key_cannot_access_dashboard_only_routes(client, method, path, json_body):
    create_response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)
    api_key = create_response.json()["api_key"]
    api_key_header = {"Authorization": f"Bearer {api_key}"}

    response = await client.request(method, path, headers=api_key_header, json=json_body)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_generated_api_key_can_only_patch_contact_outreach_fields(client):
    contact_response = await client.post(
        "/api/contacts",
        headers=AUTH_HEADER,
        json={"name": "Taylor Recruiter", "email": "taylor@example.com"},
    )
    create_response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)
    api_key = create_response.json()["api_key"]
    api_key_header = {"Authorization": f"Bearer {api_key}"}
    contact_id = contact_response.json()["id"]

    outreach_response = await client.patch(
        f"/api/contacts/{contact_id}",
        headers=api_key_header,
        json={"reached_out": True},
    )
    name_response = await client.patch(
        f"/api/contacts/{contact_id}",
        headers=api_key_header,
        json={"name": "Changed Name"},
    )

    assert outreach_response.status_code == 200
    assert outreach_response.json()["reached_out"] is True
    assert name_response.status_code == 403


@pytest.mark.asyncio
async def test_rotating_api_key_invalidates_previous_key(client):
    first_response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)
    second_response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)

    first_key_header = {"Authorization": f"Bearer {first_response.json()['api_key']}"}
    second_key_header = {"Authorization": f"Bearer {second_response.json()['api_key']}"}

    old_validate = await client.post("/api/auth/api-key/validate", headers=first_key_header)
    new_validate = await client.post("/api/auth/api-key/validate", headers=second_key_header)

    assert old_validate.status_code == 401
    assert new_validate.status_code == 200


@pytest.mark.asyncio
async def test_revoking_api_key_invalidates_current_key(client):
    create_response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)
    api_key = create_response.json()["api_key"]
    api_key_header = {"Authorization": f"Bearer {api_key}"}

    revoke_response = await client.delete("/api/auth/api-key", headers=AUTH_HEADER)
    validate_response = await client.post("/api/auth/api-key/validate", headers=api_key_header)
    status_response = await client.get("/api/auth/api-key", headers=AUTH_HEADER)

    assert revoke_response.status_code == 204
    assert validate_response.status_code == 401
    assert status_response.json()["has_api_key"] is False
