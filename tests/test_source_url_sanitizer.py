from backend.services.source_intelligence.url_sanitizer import sanitize_public_job_url, sanitize_url, source_link_hash


def test_sanitizer_removes_tracking_params_and_fragments():
    url = "https://jobs.example.com/acme/backend/?utm_source=linkedin&gh_jid=123&ref=email#apply"

    assert sanitize_public_job_url(url) == "https://jobs.example.com/acme/backend"


def test_sanitizer_privatises_tokenized_urls():
    result = sanitize_url("https://jobs.example.com/acme/backend?applicationId=abc&token=secret")

    assert result.sanitization_status == "private_user_only"
    assert result.canonical_public_url is None
    assert "private" in (result.rejection_reason or "")


def test_sanitizer_offline_unwraps_safe_tracking_redirects_without_fetching():
    redirect = (
        "https://click.email.provider/redirect?"
        "url=https%3A%2F%2Fboards.greenhouse.io%2Facme%2Fjobs%2F123%3Futm_source%3Demail"
    )

    assert sanitize_public_job_url(redirect) == "https://boards.greenhouse.io/acme/jobs/123"


def test_sanitizer_does_not_unwrap_private_redirect_destination():
    redirect = (
        "https://click.email.provider/redirect?"
        "url=https%3A%2F%2Fexample.com%2Fcandidate-home%3Ftoken%3Dabc"
    )

    result = sanitize_url(redirect)

    assert result.sanitization_status == "private_user_only"
    assert result.canonical_public_url is None


def test_source_link_hash_uses_keyed_hmac():
    value = "https://boards.greenhouse.io/acme/jobs/123"
    digest_a, version_a = source_link_hash(value, key="key-a", version="v9")
    digest_b, _ = source_link_hash(value, key="key-b", version="v9")

    assert version_a == "v9"
    assert digest_a != digest_b
    assert digest_a != __import__("hashlib").sha256(value.encode("utf-8")).hexdigest()

