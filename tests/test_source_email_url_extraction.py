import base64

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_gmail_href_extraction_stores_classified_links(db_session):
    from backend.models import EmailEvent, UserApplicationLink
    from backend.services.source_intelligence.link_store import store_many_user_application_links
    from backend.services.source_intelligence.url_classifier import extract_urls_from_gmail_payload
    from tests.conftest import TEST_USER_ID

    html = """
    <html><body>
      <a href="https://click.email.provider/redirect?url=https%3A%2F%2Fboards.greenhouse.io%2Facme%2Fjobs%2F123%3Futm_source%3Demail">View role</a>
      <a href="https://calendly.com/recruiter/screen?invite=abc">Schedule</a>
    </body></html>
    """
    payload = {
        "mimeType": "text/html",
        "body": {"data": base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")},
    }
    event = EmailEvent(subject="Application update", classification="job_update")
    db_session.add(event)
    await db_session.flush()

    urls = extract_urls_from_gmail_payload(payload)
    await store_many_user_application_links(
        db_session,
        user_id=TEST_USER_ID,
        raw_urls=urls,
        email_event_id=event.id,
        created_from="unit_test_gmail",
    )
    await db_session.commit()

    links = (await db_session.execute(select(UserApplicationLink).order_by(UserApplicationLink.created_at))).scalars().all()
    assert len(links) == 2
    assert links[0].canonical_public_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert links[0].raw_url_encrypted is None
    assert links[1].link_type == "interview_scheduler"
    assert links[1].raw_url_encrypted is not None
