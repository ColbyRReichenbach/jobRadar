from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_source_intelligence_tables_are_createable(db_session):
    from backend.models import (
        Application,
        ApplicationSourceLink,
        CompanyJobSource,
        JobPosting,
        JobSearchProviderUsage,
        SourceDiscoveryEvent,
        SourceVerificationRun,
        UserApplicationLink,
    )

    app = Application(company="SourceCo", role_title="Engineer")
    db_session.add(app)
    await db_session.flush()

    source = CompanyJobSource(
        company_name="SourceCo",
        company_domain="sourceco.com",
        provider_type="greenhouse",
        provider_key="sourceco",
        access_mode="public",
        discovered_from="unit_test",
    )
    db_session.add(source)
    await db_session.flush()

    private_link = UserApplicationLink(
        application_id=app.id,
        raw_url_hash="h1",
        raw_url_hash_version="v1",
        link_type="candidate_home",
        provider_type="greenhouse",
        provider_key="sourceco",
        contains_private_token=True,
        sanitization_status="private_user_only",
    )
    posting = JobPosting(
        source_id=source.id,
        dedupe_key="greenhouse:sourceco:123",
        company_name="SourceCo",
        title="Engineer",
        canonical_url="https://boards.greenhouse.io/sourceco/jobs/123",
        source_type="greenhouse",
    )
    db_session.add_all([private_link, posting])
    await db_session.flush()

    db_session.add_all(
        [
            ApplicationSourceLink(
                application_id=app.id,
                job_posting_id=posting.id,
                company_job_source_id=source.id,
                relationship_type="canonical_posting",
                created_from="unit_test",
            ),
            SourceDiscoveryEvent(
                source_id=source.id,
                application_id=app.id,
                event_type="application_url_classified",
                provider_type="greenhouse",
                redacted_evidence={"provider_type": "greenhouse", "rule_ids": ["safe_public_provider_url"]},
            ),
            SourceVerificationRun(
                source_id=source.id,
                status="verified",
                http_status=200,
                job_count=1,
            ),
            JobSearchProviderUsage(
                user_key="global",
                provider="serpapi",
                request_mode="fallback",
                query_hash="query-hmac",
                month_bucket=date(2026, 5, 1),
            ),
        ]
    )
    await db_session.commit()

    rows = (await db_session.execute(select(JobPosting))).scalars().all()
    assert rows[0].canonical_url == "https://boards.greenhouse.io/sourceco/jobs/123"


@pytest.mark.asyncio
async def test_user_application_link_dedupes_by_user_and_hmac(db_session):
    from backend.models import UserApplicationLink

    db_session.add_all(
        [
            UserApplicationLink(raw_url_hash="same-hmac", link_type="magic_login", sanitization_status="private_user_only"),
            UserApplicationLink(raw_url_hash="same-hmac", link_type="magic_login", sanitization_status="private_user_only"),
        ]
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_private_link_endpoint_redacts_raw_values(client, db_session):
    from backend.models import UserApplicationLink

    db_session.add(
        UserApplicationLink(
            raw_url_encrypted="fernet:encrypted",
            raw_url_hash="private-hmac",
            link_type="interview_scheduler",
            provider_type="unknown",
            company_domain="example.com",
            sanitization_status="private_user_only",
        )
    )
    await db_session.commit()

    response = await client.get("/api/settings/source-intelligence/private-links", headers=AUTH_HEADER)

    assert response.status_code == 200
    data = response.json()
    assert data[0]["link_type"] == "interview_scheduler"
    assert "raw_url_encrypted" not in data[0]
    assert "private-hmac" not in str(data[0])

