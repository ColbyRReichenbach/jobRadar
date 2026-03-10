"""Tests for Sprint 3: Role Taxonomy & Classification."""
import pytest
from backend.models import RoleUmbrella
from backend.services.role_classifier import classify_role, clear_cache
from tests.conftest import AUTH_HEADER


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear the role classifier cache before each test."""
    clear_cache()
    yield
    clear_cache()


async def _seed_umbrellas(db_session):
    """Insert a few umbrella categories for testing."""
    umbrellas = [
        RoleUmbrella(name="Software Engineer", aliases=["SWE", "Software Developer", "Programmer"]),
        RoleUmbrella(name="Product Manager", aliases=["PM", "Product Owner"]),
        RoleUmbrella(name="Data Scientist", aliases=["Data Science", "ML Scientist"]),
        RoleUmbrella(name="Frontend Engineer", aliases=["Frontend Developer", "Front-End Engineer", "UI Engineer"]),
    ]
    for u in umbrellas:
        db_session.add(u)
    await db_session.commit()
    return umbrellas


@pytest.mark.asyncio
async def test_exact_name_match(db_session):
    await _seed_umbrellas(db_session)
    result = await classify_role(db_session, "Software Engineer")
    assert result["umbrella_name"] == "Software Engineer"
    assert result["confidence"] == 1.0


@pytest.mark.asyncio
async def test_alias_match(db_session):
    await _seed_umbrellas(db_session)
    result = await classify_role(db_session, "SWE")
    assert result["umbrella_name"] == "Software Engineer"
    assert result["confidence"] == 0.95


@pytest.mark.asyncio
async def test_substring_match(db_session):
    await _seed_umbrellas(db_session)
    result = await classify_role(db_session, "Senior Software Engineer")
    assert result["umbrella_name"] == "Software Engineer"
    assert result["confidence"] > 0.3


@pytest.mark.asyncio
async def test_no_match(db_session):
    await _seed_umbrellas(db_session)
    result = await classify_role(db_session, "Janitor")
    assert result["umbrella_id"] is None
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_empty_umbrella_table(db_session):
    result = await classify_role(db_session, "Software Engineer")
    assert result["umbrella_id"] is None


@pytest.mark.asyncio
async def test_create_job_auto_classifies(client, db_session):
    """POST /api/jobs should auto-classify into an umbrella."""
    await _seed_umbrellas(db_session)

    res = await client.post("/api/jobs", json={
        "company": "TestCo",
        "role_title": "Software Engineer",
    }, headers=AUTH_HEADER)
    assert res.status_code == 201
    data = res.json()
    assert data["umbrella_id"] is not None


@pytest.mark.asyncio
async def test_umbrella_filter(client, db_session):
    """GET /api/jobs?umbrella_id=xxx should filter correctly."""
    umbrellas = await _seed_umbrellas(db_session)

    # Create two jobs with different roles
    await client.post("/api/jobs", json={
        "company": "Co1",
        "role_title": "Software Engineer",
    }, headers=AUTH_HEADER)
    await client.post("/api/jobs", json={
        "company": "Co2",
        "role_title": "Product Manager",
    }, headers=AUTH_HEADER)

    # Get umbrella IDs
    umbrella_res = await client.get("/api/umbrellas", headers=AUTH_HEADER)
    umbrella_list = umbrella_res.json()
    swe_umbrella = next(u for u in umbrella_list if u["name"] == "Software Engineer")

    # Filter
    filtered_res = await client.get(f"/api/jobs?umbrella_id={swe_umbrella['id']}", headers=AUTH_HEADER)
    filtered = filtered_res.json()
    assert all(j["umbrella_id"] == swe_umbrella["id"] for j in filtered)


@pytest.mark.asyncio
async def test_list_umbrellas(client, db_session):
    """GET /api/umbrellas returns the list."""
    await _seed_umbrellas(db_session)
    res = await client.get("/api/umbrellas", headers=AUTH_HEADER)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 4
    names = {u["name"] for u in data}
    assert "Software Engineer" in names
    assert "Product Manager" in names
