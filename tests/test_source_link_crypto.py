from cryptography.fernet import Fernet

from backend.services.source_intelligence.link_crypto import (
    decrypt_source_link,
    encrypt_source_link,
    hash_source_link,
    validate_source_link_crypto_config,
)


def test_source_link_crypto_uses_source_specific_key_and_versions(monkeypatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("SOURCE_LINK_ENCRYPTION_KEY", key)
    monkeypatch.setenv("SOURCE_LINK_ENCRYPTION_KEY_VERSION", "source-v2")
    monkeypatch.setenv("SOURCE_LINK_HASH_KEY", "hash-key")
    monkeypatch.setenv("SOURCE_LINK_HASH_KEY_VERSION", "hash-v2")

    raw_url = "https://jobs.example.com/status?candidateId=abc&token=secret"
    encrypted = encrypt_source_link(raw_url)
    digest, hash_version = hash_source_link(raw_url)

    assert encrypted.startswith("fernet:")
    assert raw_url not in encrypted
    assert decrypt_source_link(encrypted) == raw_url
    assert hash_version == "hash-v2"
    assert len(digest) == 64


def test_source_link_crypto_validation_requires_config(monkeypatch):
    monkeypatch.delenv("SOURCE_LINK_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("SOURCE_LINK_HASH_KEY", raising=False)

    try:
        validate_source_link_crypto_config(require_encryption=True)
    except RuntimeError as exc:
        assert "SOURCE_LINK_ENCRYPTION_KEY" in str(exc)
    else:
        raise AssertionError("Expected source-link encryption validation to fail")

    try:
        validate_source_link_crypto_config(require_hash=True)
    except RuntimeError as exc:
        assert "SOURCE_LINK_HASH_KEY" in str(exc)
    else:
        raise AssertionError("Expected source-link hash validation to fail")
