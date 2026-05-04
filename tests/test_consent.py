import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_get_consent_defaults_include_web_research(client):
    resp = await client.get("/api/consent", headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["consents"] == {
        "core": False,
        "ai_processing": False,
        "third_party_enrichment": False,
        "web_research": False,
        "source_intelligence": False,
    }
    assert data["accepted_at"] is None


@pytest.mark.asyncio
async def test_update_consent_persists_web_research(client):
    resp = await client.put(
        "/api/consent",
        json={
            "core": True,
            "ai_processing": True,
            "third_party_enrichment": False,
            "web_research": True,
            "source_intelligence": True,
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consents"]["core"] is True
    assert data["consents"]["ai_processing"] is True
    assert data["consents"]["third_party_enrichment"] is False
    assert data["consents"]["web_research"] is True
    assert data["consents"]["source_intelligence"] is True
    assert data["accepted_at"] is not None

    get_resp = await client.get("/api/consent", headers=AUTH_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json()["consents"]["web_research"] is True
    assert get_resp.json()["consents"]["source_intelligence"] is True


@pytest.mark.asyncio
async def test_source_intelligence_settings_endpoint_updates_only_source_consent(client):
    resp = await client.put(
        "/api/settings/source-intelligence",
        json={"source_intelligence": True},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    assert resp.json()["source_intelligence"] is True

    get_resp = await client.get("/api/settings/source-intelligence", headers=AUTH_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json()["source_intelligence"] is True
    assert get_resp.json()["private_link_count"] == 0


@pytest.mark.asyncio
async def test_source_intelligence_consent_change_writes_redacted_audit_event(client, db_session):
    from sqlalchemy import select
    from backend.models import SourceDiscoveryEvent

    resp = await client.put(
        "/api/consent",
        json={
            "core": True,
            "ai_processing": False,
            "third_party_enrichment": False,
            "web_research": False,
            "source_intelligence": True,
        },
        headers=AUTH_HEADER,
    )

    assert resp.status_code == 200
    event = (
        await db_session.execute(
            select(SourceDiscoveryEvent).where(SourceDiscoveryEvent.event_type == "source_intelligence_consent_changed")
        )
    ).scalar_one()
    assert event.redacted_evidence == {"granted": True, "surface": "consent"}
