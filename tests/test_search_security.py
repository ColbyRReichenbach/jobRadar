import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_global_search_escapes_like_wildcards(client, db_session):
    from backend.models import Application

    db_session.add_all(
        [
            Application(company="100% Real Co", role_title="Engineer"),
            Application(company="Ordinary Co", role_title="Designer"),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/search/global?q=100%25", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    companies = {row["company"] for row in data["applications"]}
    assert companies == {"100% Real Co"}


@pytest.mark.asyncio
async def test_network_search_escapes_like_wildcards(client, db_session):
    from backend.models import Application, Contact

    app = Application(company="Wildcard Co", role_title="PM")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    db_session.add_all(
        [
            Contact(application_id=app.id, name="Under_score", email="under@example.com", source="hunter"),
            Contact(application_id=app.id, name="Plain Person", email="plain@example.com", source="hunter"),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/network?q=_", headers=AUTH_HEADER)

    assert response.status_code == 200
    names = {row["name"] for row in response.json()}
    assert names == {"Under_score"}


@pytest.mark.asyncio
async def test_salary_location_filter_escapes_like_wildcards(client, db_session):
    from backend.models import Application

    db_session.add_all(
        [
            Application(
                company="Salary Match",
                role_title="Engineer",
                location="Remote_Only",
                salary_min=100000,
                salary_max=120000,
                salary_currency="USD",
                salary_period="yearly",
            ),
            Application(
                company="Salary No Match",
                role_title="Engineer",
                location="RemoteXOnly",
                salary_min=130000,
                salary_max=150000,
                salary_currency="USD",
                salary_period="yearly",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get("/api/intelligence/salary?location=_", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["raw_count"] == 1
