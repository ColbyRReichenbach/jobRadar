"""Sprint 10: Tests for network page endpoints."""

import pytest
from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_network_empty(client):
    """GET /api/network returns empty list when no contacts."""
    resp = await client.get("/api/network", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_network_with_contacts(client, db_session):
    """GET /api/network returns contacts from Contact table."""
    from backend.models import Application, Contact

    app = Application(company="NetCo", role_title="SWE")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    contact = Contact(
        application_id=app.id,
        name="Jane Doe",
        email="jane@netco.com",
        title="Engineering Manager",
        source="hunter",
    )
    db_session.add(contact)
    await db_session.commit()

    resp = await client.get("/api/network", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(c["name"] == "Jane Doe" for c in data)


@pytest.mark.asyncio
async def test_network_search(client, db_session):
    """GET /api/network?q= filters by name."""
    from backend.models import Application, Contact

    app = Application(company="SearchCo", role_title="PM")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    c1 = Contact(application_id=app.id, name="Alice", email="alice@searchco.com", source="hunter")
    c2 = Contact(application_id=app.id, name="Bob", email="bob@searchco.com", source="hunter")
    db_session.add_all([c1, c2])
    await db_session.commit()

    resp = await client.get("/api/network?q=alice", headers=AUTH_HEADER)
    data = resp.json()
    assert any(c["name"] == "Alice" for c in data)


@pytest.mark.asyncio
async def test_network_dedupes_emails(client, db_session):
    """Contacts with same email are deduped."""
    from backend.models import Application, Contact

    app = Application(company="DupeCo", role_title="Eng")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    c1 = Contact(application_id=app.id, name="Same Person", email="same@dupeco.com", source="hunter")
    c2 = Contact(application_id=app.id, name="Same Person", email="same@dupeco.com", source="email")
    db_session.add_all([c1, c2])
    await db_session.commit()

    resp = await client.get("/api/network", headers=AUTH_HEADER)
    data = resp.json()
    same_emails = [c for c in data if c.get("email") == "same@dupeco.com"]
    assert len(same_emails) == 1


@pytest.mark.asyncio
async def test_network_contact_detail(client, db_session):
    """GET /api/network/{email} returns contact profile."""
    from backend.models import Application, Contact

    app = Application(company="DetailCo", role_title="Eng")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    contact = Contact(
        application_id=app.id,
        name="Detail Person",
        email="detail@detailco.com",
        source="hunter",
    )
    db_session.add(contact)
    await db_session.commit()

    resp = await client.get("/api/network/detail@detailco.com", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["contact"]["name"] == "Detail Person"
