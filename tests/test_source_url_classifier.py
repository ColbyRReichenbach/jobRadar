import base64

from backend.services.source_intelligence.url_classifier import (
    classify_url,
    extract_urls_from_gmail_payload,
)


def test_classifier_identifies_public_provider_urls():
    fixtures = [
        ("https://boards.greenhouse.io/acme/jobs/123", "public_job_posting", "greenhouse", "acme"),
        ("https://jobs.lever.co/acme/abc", "public_job_posting", "lever", "acme"),
        ("https://jobs.ashbyhq.com/acme/abc", "public_job_posting", "ashby", "acme"),
        (
            "https://company.wd5.myworkdayjobs.com/en-US/site/job/location/title_JR123",
            "public_job_posting",
            "workday",
            "company",
        ),
        ("https://apply.workable.com/acme/j/ABC123", "public_job_posting", "workable", "acme"),
    ]

    for url, link_type, provider_type, provider_key in fixtures:
        result = classify_url(url)
        assert result.link_type == link_type
        assert result.provider_type == provider_type
        assert result.provider_key == provider_key
        assert result.safe_to_share is True
        assert result.contains_private_token is False


def test_classifier_rejects_private_and_scheduler_urls():
    fixtures = [
        ("https://company.wd5.myworkdayjobs.com/site/candidate-home", "candidate_home"),
        ("https://calendly.com/recruiter/screen", "interview_scheduler"),
        ("https://example.com?token=abc", "unknown"),
        ("https://example.com?applicationId=abc", "unknown"),
        ("https://example.com?candidateId=abc", "unknown"),
        ("https://example.com?auth=abc&session=xyz", "unknown"),
    ]

    for url, link_type in fixtures:
        result = classify_url(url)
        assert result.link_type == link_type
        assert result.safe_to_share is False
        assert result.rejection_reason is not None


def test_extract_urls_from_gmail_payload_preserves_html_hrefs():
    html = '<html><body><a href="https://boards.greenhouse.io/acme/jobs/123?utm_source=email">Apply</a></body></html>'
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": base64.urlsafe_b64encode(b"Plain text without link").decode("ascii")},
            },
            {
                "mimeType": "text/html",
                "body": {"data": base64.urlsafe_b64encode(html.encode("utf-8")).decode("ascii")},
            },
        ],
    }

    assert extract_urls_from_gmail_payload(payload) == [
        "https://boards.greenhouse.io/acme/jobs/123?utm_source=email"
    ]

