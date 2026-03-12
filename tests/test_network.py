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


@pytest.mark.asyncio
async def test_network_contact_detail_rejects_invalid_email(client):
    """GET /api/network/{email} rejects invalid email path values."""
    resp = await client.get("/api/network/not-an-email", headers=AUTH_HEADER)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_network_excludes_non_human_email_senders(client, db_session):
    from backend.models import EmailEvent

    db_session.add_all(
        [
            EmailEvent(
                gmail_message_id="network-human-1",
                sender="Jane Doe",
                sender_email="jane.doe@company.com",
                subject="Following up on your interview",
                classification="conversation",
                is_human=True,
                email_type="conversation",
            ),
            EmailEvent(
                gmail_message_id="network-noise-1",
                sender="GitHub",
                sender_email="noreply@github.com",
                subject="Build failed",
                classification="not_relevant",
                is_human=False,
            ),
            EmailEvent(
                gmail_message_id="network-team-1",
                sender="Talent Team",
                sender_email="talent@company.com",
                subject="Application received",
                classification="job_update",
                is_human=True,
                email_type="conversation",
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/network", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()

    emails = {contact["email"] for contact in data}
    assert "jane.doe@company.com" in emails
    assert "noreply@github.com" not in emails
    assert "talent@company.com" not in emails


@pytest.mark.asyncio
async def test_network_excludes_inbox_updates_even_if_human(client, db_session):
    from backend.models import EmailEvent

    db_session.add(
        EmailEvent(
            gmail_message_id="network-update-1",
            sender="Hiring Team",
            sender_email="hiring@company.com",
            subject="Application received",
            classification="job_update",
            is_human=True,
            email_type="decision",
        )
    )
    await db_session.commit()

    resp = await client.get("/api/network", headers=AUTH_HEADER)
    assert resp.status_code == 200
    emails = {contact["email"] for contact in resp.json()}
    assert "hiring@company.com" not in emails


@pytest.mark.asyncio
async def test_delete_network_contact_hides_future_email_derived_contact(client, db_session):
    from backend.models import Application, Contact, EmailEvent

    app = Application(company="DeleteCo", role_title="Engineer")
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)

    db_session.add_all(
        [
            Contact(
                application_id=app.id,
                email="jane@deleteco.com",
                name="Jane Delete",
                source="manual",
            ),
            EmailEvent(
                gmail_message_id="delete-network-email-1",
                sender="Jane Delete",
                sender_email="jane@deleteco.com",
                subject="Following up",
                classification="conversation",
                is_human=True,
                email_type="conversation",
            ),
        ]
    )
    await db_session.commit()

    before = await client.get("/api/network", headers=AUTH_HEADER)
    assert before.status_code == 200
    assert "jane@deleteco.com" in {contact["email"] for contact in before.json()}

    resp = await client.delete("/api/network/jane@deleteco.com", headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    after = await client.get("/api/network", headers=AUTH_HEADER)
    assert after.status_code == 200
    assert "jane@deleteco.com" not in {contact["email"] for contact in after.json()}


@pytest.mark.asyncio
async def test_network_auto_fills_email_derived_contact_fields(client, db_session):
    from backend.models import EmailEvent
    from datetime import datetime, timezone

    db_session.add(
        EmailEvent(
            gmail_message_id="network-enrich-1",
            sender="Jane Doe",
            sender_email="jane.doe@stripe.com",
            subject="Following up on the Staff Engineer role",
            body=(
                "Hi Colby,\n\n"
                "Great speaking today.\n"
                "Jane Doe\n"
                "Senior Technical Recruiter at Stripe\n"
                "https://www.linkedin.com/in/jane-doe/\n"
            ),
            snippet="Great speaking today.",
            classification="conversation",
            is_human=True,
            email_type="conversation",
            company_name="Stripe",
            received_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/network", headers=AUTH_HEADER)
    assert resp.status_code == 200
    contacts = resp.json()
    contact = next(c for c in contacts if c["email"] == "jane.doe@stripe.com")
    assert contact["name"] == "Jane Doe"
    assert contact["company"] == "Stripe"
    assert contact["title"] == "Senior Technical Recruiter at Stripe"
    assert contact["linkedin_url"] == "https://www.linkedin.com/in/jane-doe/"


@pytest.mark.asyncio
async def test_network_contact_detail_infers_missing_fields_from_email_history(client, db_session):
    from backend.models import EmailEvent
    from datetime import datetime, timezone

    db_session.add(
        EmailEvent(
            gmail_message_id="network-detail-enrich-1",
            sender="John Smith",
            sender_email="john.smith@company.com",
            subject="Quick follow-up",
            body=(
                "Thanks again.\n"
                "John Smith\n"
                "Engineering Manager at Company\n"
                "https://www.linkedin.com/in/john-smith/\n"
            ),
            snippet="Engineering Manager at Company",
            classification="conversation",
            is_human=True,
            email_type="conversation",
            received_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/network/john.smith@company.com", headers=AUTH_HEADER)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["contact"]["name"] == "John Smith"
    assert payload["contact"]["title"] == "Engineering Manager at Company"
    assert payload["contact"]["company"] == "Company"
    assert payload["contact"]["linkedin_url"] == "https://www.linkedin.com/in/john-smith/"
