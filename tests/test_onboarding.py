"""Sprint 6: Tests for onboarding preferences."""

import pytest
import pytest_asyncio
from tests.conftest import API_KEY_HEADER, AUTH_HEADER


@pytest.mark.asyncio
async def test_preferences_requires_jwt(client):
    """POST /api/profile/preferences rejects shared API key auth."""
    resp = await client.post(
        "/api/profile/preferences",
        json={"preferred_locations": ["NYC", "SF"]},
        headers=API_KEY_HEADER,
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_preferences_returns_seeded_user_defaults(client):
    """GET /api/profile/preferences returns defaults for the authenticated JWT user."""
    resp = await client.get("/api/profile/preferences", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["preferred_locations"] is None
    assert data["preferred_remote_type"] is None
    assert data["target_salary_min"] is None
    assert data["target_salary_max"] is None
    assert data["onboarding_complete"] is False
    assert data["role_interest_ids"] == []


@pytest.mark.asyncio
async def test_user_has_onboarding_fields(db_session):
    """User model has onboarding preference columns."""
    from backend.models import User

    user = User(
        google_id="test-google-123",
        email="test@example.com",
        name="Test User",
        onboarding_complete=False,
        preferred_locations=["NYC", "SF"],
        preferred_remote_type="hybrid",
        target_salary_min=100000,
        target_salary_max=150000,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.onboarding_complete is False
    assert user.preferred_locations == ["NYC", "SF"]
    assert user.preferred_remote_type == "hybrid"
    assert user.target_salary_min == 100000
    assert user.target_salary_max == 150000


@pytest.mark.asyncio
async def test_user_role_interest(db_session):
    """UserRoleInterest many-to-many works."""
    from backend.models import User, RoleUmbrella, UserRoleInterest

    user = User(google_id="test-google-456", email="test2@example.com", name="Test2")
    umbrella = RoleUmbrella(name="Software Engineer Test")
    db_session.add_all([user, umbrella])
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(umbrella)

    interest = UserRoleInterest(user_id=user.id, umbrella_id=umbrella.id)
    db_session.add(interest)
    await db_session.commit()
    await db_session.refresh(interest)

    assert interest.user_id == user.id
    assert interest.umbrella_id == umbrella.id
