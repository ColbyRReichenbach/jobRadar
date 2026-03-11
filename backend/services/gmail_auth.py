import logging
import os
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.gmail_token_crypto import (
    decrypt_gmail_token,
    encrypt_gmail_token,
    is_gmail_token_encrypted,
)

logger = logging.getLogger(__name__)

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")


async def get_valid_token(db: AsyncSession, user_id: uuid.UUID | None = None):
    from google.oauth2.credentials import Credentials

    from backend.models import GmailToken

    stmt = select(GmailToken).where(GmailToken.user_id == user_id) if user_id else select(GmailToken).limit(1)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        raise RuntimeError("No Gmail tokens found. Run OAuth flow first.")

    access_token = decrypt_gmail_token(row.access_token)
    refresh_token = decrypt_gmail_token(row.refresh_token)
    if not is_gmail_token_encrypted(row.access_token) or not is_gmail_token_encrypted(row.refresh_token):
        row.access_token = encrypt_gmail_token(access_token)
        row.refresh_token = encrypt_gmail_token(refresh_token)
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
    )

    # Refresh if expiring within 5 minutes
    if row.expires_at.timestamp() - time.time() < 300:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
        row.access_token = encrypt_gmail_token(creds.token)
        row.expires_at = datetime.fromtimestamp(creds.expiry.timestamp(), tz=timezone.utc) if creds.expiry else row.expires_at
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()

    return creds


async def store_tokens(
    db: AsyncSession,
    access_token: str,
    refresh_token: str,
    expires_at: datetime,
    user_id: uuid.UUID | None = None,
):
    from backend.models import GmailToken

    stmt = select(GmailToken).where(GmailToken.user_id == user_id) if user_id else select(GmailToken).limit(1)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    encrypted_access_token = encrypt_gmail_token(access_token)
    encrypted_refresh_token = encrypt_gmail_token(refresh_token)

    if existing:
        existing.access_token = encrypted_access_token
        existing.refresh_token = encrypted_refresh_token
        existing.expires_at = expires_at
        existing.updated_at = datetime.now(timezone.utc)
    else:
        token = GmailToken(
            user_id=user_id,
            access_token=encrypted_access_token,
            refresh_token=encrypted_refresh_token,
            expires_at=expires_at,
        )
        db.add(token)

    await db.commit()
