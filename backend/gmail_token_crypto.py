import os

from cryptography.fernet import Fernet, InvalidToken

GMAIL_TOKEN_ENCRYPTION_KEY_ENV = "APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY"
GMAIL_TOKEN_ENCRYPTION_PREFIX = "fernet:"


def _get_fernet() -> Fernet:
    key = os.getenv(GMAIL_TOKEN_ENCRYPTION_KEY_ENV, "").strip()
    if not key:
        raise RuntimeError(
            f"{GMAIL_TOKEN_ENCRYPTION_KEY_ENV} environment variable is required "
            "to encrypt Gmail tokens at rest."
        )

    try:
        return Fernet(key.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"{GMAIL_TOKEN_ENCRYPTION_KEY_ENV} must be a valid Fernet key."
        ) from exc


def validate_gmail_token_encryption_config() -> None:
    if not (os.getenv("GMAIL_CLIENT_ID") or os.getenv("GMAIL_CLIENT_SECRET")):
        return
    _get_fernet()


def encrypt_gmail_token(token: str) -> str:
    encrypted = _get_fernet().encrypt(token.encode("utf-8")).decode("utf-8")
    return f"{GMAIL_TOKEN_ENCRYPTION_PREFIX}{encrypted}"


def decrypt_gmail_token(token: str) -> str:
    if not token.startswith(GMAIL_TOKEN_ENCRYPTION_PREFIX):
        return token

    encrypted = token[len(GMAIL_TOKEN_ENCRYPTION_PREFIX):]
    try:
        return _get_fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Stored Gmail token could not be decrypted. Check "
            f"{GMAIL_TOKEN_ENCRYPTION_KEY_ENV}."
        ) from exc


def is_gmail_token_encrypted(token: str) -> bool:
    return token.startswith(GMAIL_TOKEN_ENCRYPTION_PREFIX)
