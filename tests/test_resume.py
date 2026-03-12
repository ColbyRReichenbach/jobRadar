"""Sprint 5: Tests for resume parsing and match scoring."""

import pytest
import pytest_asyncio

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_parse_resume_text(client):
    """POST /api/resume/parse creates a user profile from text."""
    resume_text = """
    John Doe
    Software Engineer

    Skills: Python, JavaScript, React, PostgreSQL, Docker, AWS

    Experience:
    Senior Software Engineer at Acme Corp (2020-2024)
    - Built microservices with Python and FastAPI
    - Managed PostgreSQL databases

    Software Engineer at StartupX (2018-2020)
    - Frontend development with React and TypeScript

    Education:
    BS Computer Science, MIT, 2018
    """
    resp = await client.post(
        "/api/resume/parse",
        json={"text": resume_text},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert isinstance(data["skills"], list)
    assert len(data["skills"]) > 0
    # Should extract Python, React, etc from the fallback parser
    skill_names = [s.lower() for s in data["skills"]]
    assert "python" in skill_names


@pytest.mark.asyncio
async def test_get_profile(client):
    """GET /api/profile returns the parsed profile."""
    # First create a profile
    await client.post(
        "/api/resume/parse",
        json={"text": "Skills: Python, React, Docker"},
        headers=AUTH_HEADER,
    )

    resp = await client.get("/api/profile", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data is not None
    assert "skills" in data
    assert "linkedin_url" in data
    assert "resume_text" in data


@pytest.mark.asyncio
async def test_profile_upsert(client):
    """Uploading a new resume updates the existing profile."""
    await client.post(
        "/api/resume/parse",
        json={"text": "Skills: Python"},
        headers=AUTH_HEADER,
    )
    resp1 = await client.get("/api/profile", headers=AUTH_HEADER)
    id1 = resp1.json()["id"]

    await client.post(
        "/api/resume/parse",
        json={"text": "Skills: JavaScript, TypeScript"},
        headers=AUTH_HEADER,
    )
    resp2 = await client.get("/api/profile", headers=AUTH_HEADER)
    id2 = resp2.json()["id"]

    # Same profile, updated
    assert id1 == id2


@pytest.mark.asyncio
async def test_update_and_clear_profile(client):
    update_resp = await client.patch(
        "/api/profile",
        json={
            "linkedin_url": "https://linkedin.com/in/test-user",
            "skills": ["Python", "FastAPI"],
            "tools": ["Docker"],
            "certifications": ["AWS CCP"],
            "education": ["BS Computer Science — Test University — 2020"],
            "experience_years": 4,
            "resume_text": "Test resume text",
        },
        headers=AUTH_HEADER,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["linkedin_url"] == "https://linkedin.com/in/test-user"
    assert data["experience_years"] == 4
    assert data["skills"] == ["Python", "FastAPI"]
    assert data["resume_text"] == "Test resume text"

    clear_resp = await client.delete("/api/profile", headers=AUTH_HEADER)
    assert clear_resp.status_code == 200

    get_resp = await client.get("/api/profile", headers=AUTH_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json() is None


@pytest.mark.asyncio
async def test_match_score_endpoint(client):
    """GET /api/jobs/{id}/match returns match score."""
    # Create profile
    await client.post(
        "/api/resume/parse",
        json={"text": "Skills: Python, React, Docker, AWS, PostgreSQL"},
        headers=AUTH_HEADER,
    )

    # Create a job with tech in description
    job_resp = await client.post(
        "/api/jobs",
        json={
            "company": "TestCo",
            "role_title": "Software Engineer",
            "description_text": "We need Python, React, and PostgreSQL experience. Docker is a plus.",
        },
        headers=AUTH_HEADER,
    )
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]

    # Get match
    match_resp = await client.get(f"/api/jobs/{job_id}/match", headers=AUTH_HEADER)
    assert match_resp.status_code == 200
    data = match_resp.json()
    assert "score" in data
    assert data["score"] > 0
    assert "matched_skills" in data
    assert "missing_skills" in data


@pytest.mark.asyncio
async def test_match_no_profile(client):
    """GET /api/jobs/{id}/match returns 404 if no profile."""
    job_resp = await client.post(
        "/api/jobs",
        json={"company": "TestCo", "role_title": "SWE"},
        headers=AUTH_HEADER,
    )
    job_id = job_resp.json()["id"]

    match_resp = await client.get(f"/api/jobs/{job_id}/match", headers=AUTH_HEADER)
    assert match_resp.status_code == 404


# --- Unit tests for match scorer ---

from backend.services.match_scorer import score_match


def test_score_match_perfect():
    """User has all required skills."""
    profile = {"skills": ["Python", "React", "Docker"], "tools": []}
    result = score_match(profile, ["Python", "React", "Docker"])
    assert result["score"] == 100
    assert len(result["missing_skills"]) == 0


def test_score_match_partial():
    """User has some required skills."""
    profile = {"skills": ["Python"], "tools": []}
    result = score_match(profile, ["Python", "React", "Docker"])
    assert 0 < result["score"] < 100
    assert "react" in result["missing_skills"]


def test_score_match_no_overlap():
    """User has none of the required skills."""
    profile = {"skills": ["Java", "Spring"], "tools": []}
    result = score_match(profile, ["Python", "React"])
    assert result["score"] == 0


def test_score_match_empty_job():
    """Job has no tech stack."""
    profile = {"skills": ["Python"], "tools": []}
    result = score_match(profile, [])
    assert result["score"] == 0


def test_score_match_transferable():
    """Transferable skills detected from same category."""
    profile = {"skills": ["Vue.js", "React"], "tools": []}
    # Job asks for Angular (Frontend category) — Vue.js should be transferable
    result = score_match(profile, ["Angular", "React"])
    assert "vue.js" in result["transferable_skills"]
