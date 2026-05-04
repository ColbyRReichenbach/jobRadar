from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import select

from tests.conftest import AUTH_HEADER, TEST_USER_ID, make_auth_header


@pytest.mark.asyncio
async def test_admin_job_sources_are_admin_only_and_redacted(client, db_session):
    from backend.models import CompanyJobSource, User

    non_admin_id = uuid.uuid4()
    db_session.add(User(id=non_admin_id, google_id="non-admin-google-id", email="non-admin@apptrail.test", name="Non Admin", is_admin=False))
    source = CompanyJobSource(
        company_name="Acme",
        provider_type="greenhouse",
        provider_key="acme",
        access_mode="public",
        career_url="https://boards.greenhouse.io/acme",
        public_jobs_endpoint="https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        source_config={"board_token": "acme", "api_key": "secret", "headers": {"Authorization": "Bearer secret"}},
        verification_status="pending",
        discovered_from="unit",
        first_seen_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(source)
    await db_session.commit()

    denied = await client.get("/api/admin/job-sources", headers=make_auth_header(non_admin_id, "non-admin@apptrail.test"))
    allowed = await client.get("/api/admin/job-sources", headers=AUTH_HEADER)

    assert denied.status_code == 403
    assert allowed.status_code == 200
    payload = allowed.json()["sources"][0]
    assert payload["source_config"] == {"board_token": "acme"}


@pytest.mark.asyncio
async def test_admin_source_verify_approve_block_flow(client, db_session):
    from backend.models import CompanyJobSource, SourceDiscoveryEvent, SourceVerificationRun
    from sqlalchemy import func, select

    source = CompanyJobSource(
        company_name="Mystery",
        provider_type="unknown",
        provider_key="mystery",
        access_mode="unknown",
        verification_status="pending",
        discovered_from="unit",
    )
    db_session.add(source)
    await db_session.commit()

    verify = await client.post(f"/api/admin/job-sources/{source.id}/verify", headers=AUTH_HEADER)
    assert verify.status_code == 200
    assert verify.json()["verification_result"]["error_type"] == "adapter_missing"
    run_count = (await db_session.execute(select(func.count(SourceVerificationRun.id)))).scalar_one()
    assert run_count == 1

    approve = await client.post(f"/api/admin/job-sources/{source.id}/approve", headers=AUTH_HEADER, json={"access_mode": "public"})
    assert approve.status_code == 200
    assert approve.json()["source"]["verification_status"] == "verified"
    assert approve.json()["source"]["access_mode"] == "public"

    block = await client.post(f"/api/admin/job-sources/{source.id}/block", headers=AUTH_HEADER, json={"reason": "terms risk"})
    assert block.status_code == 200
    assert block.json()["source"]["verification_status"] == "blocked"
    assert block.json()["source"]["access_mode"] == "blocked"
    event_types = {
        row[0]
        for row in (await db_session.execute(select(SourceDiscoveryEvent.event_type))).all()
    }
    assert {"source_verification_forced", "source_approved", "source_blocked"} <= event_types


@pytest.mark.asyncio
async def test_private_link_list_does_not_show_raw_urls(client, db_session):
    from backend.models import SourceDiscoveryEvent
    from backend.services.source_intelligence.link_store import store_user_application_link

    stored = await store_user_application_link(
        db_session,
        user_id=TEST_USER_ID,
        raw_url="https://example.com/status?token=secret&candidateId=private",
        created_from="unit",
    )
    await db_session.commit()

    resp = await client.get("/api/settings/source-intelligence/private-links", headers=AUTH_HEADER)

    assert resp.status_code == 200
    payload = resp.json()[0]
    assert set(payload) == {"id", "provider", "link_type", "company_domain", "created_at", "sanitization_status"}
    assert "secret" not in str(payload)
    assert "candidateId" not in str(payload)

    delete_resp = await client.delete(f"/api/settings/source-intelligence/private-links/{stored.user_link.id}", headers=AUTH_HEADER)
    assert delete_resp.status_code == 204
    audit_event = (await db_session.execute(select(SourceDiscoveryEvent).where(SourceDiscoveryEvent.event_type == "private_link_deleted"))).scalar_one()
    assert "secret" not in str(audit_event.redacted_evidence)
