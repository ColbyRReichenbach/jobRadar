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
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consents"]["core"] is True
    assert data["consents"]["ai_processing"] is True
    assert data["consents"]["third_party_enrichment"] is False
    assert data["consents"]["web_research"] is True
    assert data["accepted_at"] is not None

    get_resp = await client.get("/api/consent", headers=AUTH_HEADER)
    assert get_resp.status_code == 200
    assert get_resp.json()["consents"]["web_research"] is True
