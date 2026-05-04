from datetime import datetime, timezone

import pytest

from tests.conftest import AUTH_HEADER


@pytest.mark.asyncio
async def test_private_job_url_is_not_stored_on_application(client, db_session):
    from sqlalchemy import select

    from backend.models import ApplicationSourceLink, UserApplicationLink
    from backend.services.source_intelligence.link_crypto import decrypt_source_link

    private_url = "https://jobs.example.com/candidate-home?candidateId=abc&token=secret"
    response = await client.post(
        "/api/jobs",
        json={
            "company": "PrivateCo",
            "role_title": "Engineer",
            "job_url": private_url,
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 201
    assert response.json()["job_url"] is None
    private_link = (await db_session.execute(select(UserApplicationLink))).scalar_one()
    assert private_link.raw_url_encrypted
    assert decrypt_source_link(private_link.raw_url_encrypted) == private_url
    assert private_link.contains_private_token is True
    assert private_link.sanitization_status == "private_user_only"
    app_link = (await db_session.execute(select(ApplicationSourceLink))).scalar_one()
    assert app_link.relationship_type == "private_status_link"


@pytest.mark.asyncio
async def test_private_job_url_is_not_indexed_or_exported(client, db_session):
    from sqlalchemy import select

    from backend.models import SearchDocument

    private_url = "https://jobs.example.com/status?candidateId=abc&token=secret"
    response = await client.post(
        "/api/jobs",
        json={
            "company": "ExportPrivateCo",
            "role_title": "Engineer",
            "job_url": private_url,
        },
        headers=AUTH_HEADER,
    )
    assert response.status_code == 201

    documents = (await db_session.execute(select(SearchDocument))).scalars().all()
    assert documents
    assert private_url not in str(documents[0].metadata_json)

    export_response = await client.get("/api/export/csv", headers=AUTH_HEADER)
    assert export_response.status_code == 200
    assert private_url not in export_response.text

    account_export_response = await client.get("/api/account/export", headers=AUTH_HEADER)
    assert account_export_response.status_code == 200
    account_export = account_export_response.json()
    assert private_url not in account_export_response.text
    assert account_export["user_application_links"][0]["sanitization_status"] == "private_user_only"
    assert "raw_url_encrypted" not in account_export["user_application_links"][0]
    assert "raw_url_hash" not in account_export["user_application_links"][0]


@pytest.mark.asyncio
async def test_application_update_clears_private_job_url(client, db_session):
    from sqlalchemy import select

    from backend.models import ApplicationSourceLink, UserApplicationLink

    created = await client.post(
        "/api/jobs",
        json={
            "company": "PrivateCo",
            "role_title": "Engineer",
            "job_url": "https://jobs.example.com/privateco/engineer",
        },
        headers=AUTH_HEADER,
    )
    assert created.status_code == 201

    response = await client.patch(
        f"/api/jobs/{created.json()['id']}",
        json={"job_url": "https://jobs.example.com/status?applicationId=abc"},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 200
    assert response.json()["job_url"] is None
    private_link = (
        await db_session.execute(
            select(UserApplicationLink).where(UserApplicationLink.sanitization_status == "private_user_only")
        )
    ).scalar_one()
    assert private_link.link_type == "unknown"
    app_link = (
        await db_session.execute(
            select(ApplicationSourceLink).where(ApplicationSourceLink.user_application_link_id == private_link.id)
        )
    ).scalar_one()
    assert app_link.relationship_type == "private_status_link"


@pytest.mark.asyncio
async def test_application_suggestions_do_not_surface_private_urls(client, db_session):
    from backend.models import EmailEvent

    email = EmailEvent(
        sender="Acme Recruiting",
        sender_email="recruiting@acme.com",
        sender_domain="acme.com",
        subject="Thank you for applying for Data Scientist role at Acme",
        body=(
            "Track status at https://jobs.example.com/candidate-home?candidateId=abc "
            "or view the role at https://boards.greenhouse.io/acme/jobs/123?utm_source=email"
        ),
        action_url="https://calendly.com/recruiter/screen",
        classification="job_update",
        company_name="Acme",
        received_at=datetime(2026, 3, 12, 15, 30, tzinfo=timezone.utc),
    )
    db_session.add(email)
    await db_session.commit()

    response = await client.get("/api/application-suggestions", headers=AUTH_HEADER)

    assert response.status_code == 200
    suggestions = response.json()
    assert suggestions[0]["job_url"] == "https://boards.greenhouse.io/acme/jobs/123"


@pytest.mark.asyncio
async def test_parse_job_rejects_private_candidate_url(client):
    response = await client.post(
        "/api/jobs/parse",
        json={"url": "https://boards.greenhouse.io/application?token=secret"},
        headers=AUTH_HEADER,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Private or unsafe job URLs cannot be parsed."


def test_log_redaction_covers_private_url_indicators():
    from backend.logging_config import _redact_string

    value = "url=https://calendly.com/recruiter/screen?candidateId=abc\nnext token=secret&api_key=hidden"
    redacted = _redact_string(value)

    assert "\n" not in redacted
    assert "candidateId=abc" not in redacted
    assert "token=secret" not in redacted
    assert "api_key=hidden" not in redacted


def test_source_config_redaction_is_recursive_and_drops_urls():
    from backend.services.source_intelligence.redaction import redact_source_config

    config = {
        "tenant": "acme",
        "headers": {"Authorization": "Bearer secret"},
        "nested": {
            "apiKey": "secret",
            "site": "careers",
            "candidateId": "abc",
        },
        "cxs_jobs_endpoint": "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/site/jobs",
    }

    redacted = redact_source_config(config)

    assert redacted == {"tenant": "acme", "nested": {"site": "careers"}}


def test_audit_evidence_redaction_strips_crlf_and_private_values():
    from backend.services.source_intelligence.redaction import redact_audit_evidence

    evidence = {
        "rule_id": "private_token_query_param\nnext",
        "url": "https://example.com/job?token=secret",
        "nested": {"query": "token=secret", "provider_type": "workday\r"},
    }

    redacted = redact_audit_evidence(evidence)

    assert redacted["rule_id"] == "private_token_query_param next"
    assert "url" not in redacted
    assert redacted["nested"] == {"provider_type": "workday "}
