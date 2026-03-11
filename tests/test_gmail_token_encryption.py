from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select

from backend.gmail_token_crypto import (
    decrypt_gmail_token,
    encrypt_gmail_token,
    is_gmail_token_encrypted,
)
from tests.conftest import AUTH_HEADER, TEST_USER_ID


@pytest.mark.asyncio
async def test_store_tokens_encrypts_gmail_tokens_at_rest(db_session):
    from backend.models import GmailToken
    from backend.services.gmail_auth import store_tokens

    await store_tokens(
        db_session,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        user_id=TEST_USER_ID,
    )

    result = await db_session.execute(
        select(GmailToken).where(GmailToken.user_id == TEST_USER_ID)
    )
    token = result.scalar_one()

    assert is_gmail_token_encrypted(token.access_token)
    assert is_gmail_token_encrypted(token.refresh_token)
    assert token.access_token != "access-token"
    assert token.refresh_token != "refresh-token"
    assert decrypt_gmail_token(token.access_token) == "access-token"
    assert decrypt_gmail_token(token.refresh_token) == "refresh-token"


@pytest.mark.asyncio
async def test_send_email_migrates_legacy_plaintext_gmail_tokens(client, db_session):
    from backend.models import GmailToken

    legacy_token = GmailToken(
        user_id=TEST_USER_ID,
        access_token="legacy-access-token",
        refresh_token="legacy-refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(legacy_token)
    await db_session.commit()

    with patch("googleapiclient.discovery.build", return_value=Mock()):
        with patch(
            "backend.services.email_sender.send_email",
            new=AsyncMock(return_value={"status": "ok"}),
        ):
            response = await client.post(
                "/api/emails/send",
                headers=AUTH_HEADER,
                json={
                    "to": "recruiter@example.com",
                    "subject": "Checking in",
                    "body": "Just following up on my application.",
                },
            )

    assert response.status_code == 201

    await db_session.refresh(legacy_token)
    assert is_gmail_token_encrypted(legacy_token.access_token)
    assert is_gmail_token_encrypted(legacy_token.refresh_token)
    assert decrypt_gmail_token(legacy_token.access_token) == "legacy-access-token"
    assert decrypt_gmail_token(legacy_token.refresh_token) == "legacy-refresh-token"


def test_encrypt_gmail_token_prefixes_ciphertext():
    encrypted = encrypt_gmail_token("access-token")
    assert is_gmail_token_encrypted(encrypted)
    assert decrypt_gmail_token(encrypted) == "access-token"
