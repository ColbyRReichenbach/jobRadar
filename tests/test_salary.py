"""Sprint 16: Tests for salary intelligence."""

import pytest
from tests.conftest import AUTH_HEADER


def test_extract_salary_range():
    """extract_salary finds salary ranges in text."""
    from backend.services.salary_extractor import extract_salary

    result = extract_salary("The salary for this role is $120,000 - $150,000 per year.")
    assert result is not None
    assert result["salary_min"] == 120000
    assert result["salary_max"] == 150000
    assert result["salary_currency"] == "USD"
    assert result["salary_period"] == "yearly"


def test_extract_salary_k_notation():
    """extract_salary handles k shorthand."""
    from backend.services.salary_extractor import extract_salary

    result = extract_salary("Compensation: $120k - $180k")
    assert result is not None
    assert result["salary_min"] == 120000
    assert result["salary_max"] == 180000


def test_extract_salary_hourly():
    """extract_salary detects hourly rates."""
    from backend.services.salary_extractor import extract_salary

    result = extract_salary("Pay: $45 - $65 per hour")
    assert result is not None
    assert result["salary_min"] == 45
    assert result["salary_max"] == 65
    assert result["salary_period"] == "hourly"


def test_extract_salary_single():
    """extract_salary handles single salary values."""
    from backend.services.salary_extractor import extract_salary

    result = extract_salary("Salary: $130,000")
    assert result is not None
    assert result["salary_min"] == 130000
    assert result["salary_max"] == 130000


def test_extract_salary_none():
    """extract_salary returns None when no salary found."""
    from backend.services.salary_extractor import extract_salary

    assert extract_salary("This is a great role at a growing company.") is None
    assert extract_salary("") is None
    assert extract_salary(None) is None


def test_aggregate_salaries():
    """aggregate_salaries computes percentiles."""
    from backend.services.salary_extractor import aggregate_salaries

    salaries = [
        {"salary_min": 100000, "salary_max": 120000},
        {"salary_min": 110000, "salary_max": 130000},
        {"salary_min": 130000, "salary_max": 150000},
        {"salary_min": 140000, "salary_max": 160000},
    ]
    result = aggregate_salaries(salaries)
    assert result["count"] == 4
    assert result["avg"] > 0
    assert result["p25"] <= result["p50"] <= result["p75"]


def test_aggregate_salaries_empty():
    """aggregate_salaries handles empty input."""
    from backend.services.salary_extractor import aggregate_salaries

    result = aggregate_salaries([])
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_extract_salary_endpoint(client, db_session):
    """POST /api/jobs/{id}/extract-salary extracts and stores salary."""
    from backend.models import Application

    app = Application(
        company="SalaryCo",
        role_title="Engineer",
        description_text="This role pays $130,000 - $160,000 per year plus equity.",
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.post(
        f"/api/jobs/{app.id}/extract-salary",
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["extracted"] is True
    assert data["salary_min"] == 130000
    assert data["salary_max"] == 160000


@pytest.mark.asyncio
async def test_extract_salary_no_description(client, db_session):
    """extract-salary returns false when no description."""
    from backend.models import Application

    app = Application(company="NoCo", role_title="Dev")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    resp = await client.post(f"/api/jobs/{app.id}/extract-salary", headers=AUTH_HEADER)
    data = resp.json()
    assert data["extracted"] is False


@pytest.mark.asyncio
async def test_salary_intelligence_endpoint(client, db_session):
    """GET /api/intelligence/salary returns aggregated salary data."""
    from backend.models import Application

    for salary_min, salary_max in [(100000, 120000), (130000, 150000)]:
        app = Application(
            company="PayCo",
            role_title="Dev",
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency="USD",
            salary_period="yearly",
        )
        db_session.add(app)
    await db_session.commit()

    resp = await client.get("/api/intelligence/salary", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_count"] == 2
    assert data["stats"]["count"] == 2
    assert data["stats"]["avg"] > 0


@pytest.mark.asyncio
async def test_salary_model_fields(db_session):
    """Application stores salary intelligence fields."""
    from backend.models import Application

    app = Application(
        company="FieldCo",
        role_title="PM",
        salary_min=90000,
        salary_max=120000,
        salary_currency="USD",
        salary_period="yearly",
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    assert app.salary_min == 90000
    assert app.salary_max == 120000
    assert app.salary_currency == "USD"
    assert app.salary_period == "yearly"
