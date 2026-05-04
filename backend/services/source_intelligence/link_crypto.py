from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

from backend.services.source_intelligence.url_sanitizer import source_link_hash


SOURCE_LINK_ENCRYPTION_KEY_ENV = "SOURCE_LINK_ENCRYPTION_KEY"
SOURCE_LINK_ENCRYPTION_KEY_VERSION_ENV = "SOURCE_LINK_ENCRYPTION_KEY_VERSION"
SOURCE_LINK_HASH_KEY_ENV = "SOURCE_LINK_HASH_KEY"
SOURCE_LINK_HASH_KEY_VERSION_ENV = "SOURCE_LINK_HASH_KEY_VERSION"
SOURCE_LINK_ENCRYPTION_PREFIX = "fernet:"


def _get_fernet() -> Fernet:
    key = os.getenv(SOURCE_LINK_ENCRYPTION_KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(f"{SOURCE_LINK_ENCRYPTION_KEY_ENV} is required to encrypt source links at rest.")
    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{SOURCE_LINK_ENCRYPTION_KEY_ENV} must be a valid Fernet key.") from exc


def source_link_encryption_key_version() -> str:
    return os.getenv(SOURCE_LINK_ENCRYPTION_KEY_VERSION_ENV, "v1")


def source_link_hash_key_version() -> str:
    return os.getenv(SOURCE_LINK_HASH_KEY_VERSION_ENV, "v1")


def validate_source_link_crypto_config(*, require_encryption: bool = False, require_hash: bool = False) -> None:
    if require_encryption or os.getenv(SOURCE_LINK_ENCRYPTION_KEY_ENV):
        _get_fernet()
    if require_hash and not os.getenv(SOURCE_LINK_HASH_KEY_ENV, "").strip():
        raise RuntimeError(f"{SOURCE_LINK_HASH_KEY_ENV} is required for source-link hashing.")
    if not source_link_encryption_key_version().strip():
        raise RuntimeError(f"{SOURCE_LINK_ENCRYPTION_KEY_VERSION_ENV} cannot be empty.")
    if not source_link_hash_key_version().strip():
        raise RuntimeError(f"{SOURCE_LINK_HASH_KEY_VERSION_ENV} cannot be empty.")


def encrypt_source_link(raw_url: str) -> str:
    encrypted = _get_fernet().encrypt(raw_url.encode("utf-8")).decode("utf-8")
    return f"{SOURCE_LINK_ENCRYPTION_PREFIX}{encrypted}"


def decrypt_source_link(encrypted_url: str) -> str:
    if not encrypted_url.startswith(SOURCE_LINK_ENCRYPTION_PREFIX):
        raise RuntimeError("Stored source link is not encrypted with the expected prefix.")
    encrypted = encrypted_url[len(SOURCE_LINK_ENCRYPTION_PREFIX):]
    try:
        return _get_fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored source link could not be decrypted. Check SOURCE_LINK_ENCRYPTION_KEY.") from exc


def hash_source_link(raw_url: str) -> tuple[str, str]:
    return source_link_hash(raw_url, version=source_link_hash_key_version())
