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
async def test_generated_api_key_validates_and_authenticates_user_owned_route(client):
    create_response = await client.post("/api/auth/api-key", headers=AUTH_HEADER)
    api_key = create_response.json()["api_key"]
    api_key_header = {"Authorization": f"Bearer {api_key}"}

    validate_response = await client.post("/api/auth/api-key/validate", headers=api_key_header)
    prefs_response = await client.get("/api/notifications/preferences", headers=api_key_header)

    assert validate_response.status_code == 200
    assert validate_response.json()["auth_type"] == "api_key"
    assert prefs_response.status_code == 200


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
