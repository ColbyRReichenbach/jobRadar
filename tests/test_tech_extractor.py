"""Tests for Sprint 4: Tech Stack Extraction."""
import uuid

import pytest
from backend.services.tech_extractor import extract_tech_stack
from tests.conftest import AUTH_HEADER, TEST_USER_ID


def test_extract_from_description():
    text = """
    We are looking for a Software Engineer proficient in Python, React, and PostgreSQL.
    Experience with Docker, Kubernetes, and AWS is preferred.
    """
    result = extract_tech_stack(text)
    names = {t["name"] for t in result}
    assert "Python" in names
    assert "React" in names
    assert "PostgreSQL" in names
    assert "Docker" in names
    assert "Kubernetes" in names
    assert "AWS" in names


def test_empty_text():
    assert extract_tech_stack("") == []
    assert extract_tech_stack(None) == []


def test_no_tech_found():
    result = extract_tech_stack("Looking for a friendly person to join our team")
    assert len(result) == 0


def test_java_not_javascript():
    """Java should not match JavaScript and vice versa."""
    java_text = "Must have 5 years of Java experience"
    result = extract_tech_stack(java_text)
    names = {t["name"] for t in result}
    assert "Java" in names
    assert "JavaScript" not in names


def test_javascript_standalone():
    js_text = "Experience with JavaScript and TypeScript required"
    result = extract_tech_stack(js_text)
    names = {t["name"] for t in result}
    assert "JavaScript" in names
    assert "TypeScript" in names


def test_categories():
    result = extract_tech_stack("Python, React, PostgreSQL, Docker, AWS")
    categories = {t["name"]: t["category"] for t in result}
    assert categories.get("Python") == "Languages"
    assert categories.get("React") == "Frontend"
    assert categories.get("PostgreSQL") == "Databases"
    assert categories.get("Docker") == "DevOps"
    assert categories.get("AWS") == "Cloud"


def test_react_native_separate():
    """React Native should not also match React."""
    text = "Experience with React Native for mobile development"
    result = extract_tech_stack(text)
    names = {t["name"] for t in result}
    assert "React Native" in names
    # React should NOT match because we exclude it when followed by "native"
    assert "React" not in names


@pytest.mark.asyncio
async def test_create_job_extracts_tech(client):
    """POST /api/jobs with description should auto-extract tech stack."""
    res = await client.post("/api/jobs", json={
        "company": "TechCorp",
        "role_title": "Full Stack Developer",
        "description_text": "We need someone with Python, React, PostgreSQL and Docker experience.",
    }, headers=AUTH_HEADER)
    assert res.status_code == 201
    data = res.json()
    assert "Python" in data["tech_stack"]
    assert "React" in data["tech_stack"]
    assert "PostgreSQL" in data["tech_stack"]
    assert "Docker" in data["tech_stack"]


@pytest.mark.asyncio
async def test_job_without_description_no_tech(client):
    """Job without description should have empty tech stack."""
    res = await client.post("/api/jobs", json={
        "company": "NoCorp",
        "role_title": "Manager",
    }, headers=AUTH_HEADER)
    assert res.status_code == 201
    data = res.json()
    assert data["tech_stack"] == []


@pytest.mark.asyncio
async def test_company_tech_endpoint_anonymizes_product_wide_counts(client, db_session):
    from backend.models import Application, Company, CompanyTechProfile, User

    company = Company(domain="aggregate-tech.com", name="AggregateTech")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    db_session.add(
        CompanyTechProfile(
            company_id=company.id,
            tech_name="Python",
            category="Languages",
            mention_count=12,
        )
    )
    db_session.add(
        Application(
            user_id=TEST_USER_ID,
            company="AggregateTech",
            role_title="Engineer",
            company_id=company.id,
        )
    )
    await db_session.commit()

    insufficient = await client.get("/api/companies/aggregate-tech.com/tech", headers=AUTH_HEADER)
    assert insufficient.status_code == 200
    assert insufficient.json()["aggregate_status"] == "insufficient_data"
    assert insufficient.json()["tech_stack"] == []

    extra_users = []
    for idx in range(2):
        user_id = uuid.uuid4()
        extra_users.append(user_id)
        db_session.add(
            User(
                id=user_id,
                google_id=f"tech-user-{user_id}",
                email=f"tech-{idx}@apptrail.test",
                name=f"Tech User {idx}",
            )
        )
        db_session.add(
            Application(
                user_id=user_id,
                company="AggregateTech",
                role_title=f"Engineer {idx}",
                company_id=company.id,
            )
        )
    await db_session.commit()

    available = await client.get("/api/companies/aggregate-tech.com/tech", headers=AUTH_HEADER)
    assert available.status_code == 200
    tech = available.json()["tech_stack"][0]
    assert available.json()["aggregate_status"] == "available"
    assert tech["name"] == "Python"
    assert tech["mention_bucket"] == "10-24"
    assert "mentions" not in tech
