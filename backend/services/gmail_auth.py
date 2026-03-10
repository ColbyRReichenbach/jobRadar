import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "http://localhost:8000/api/auth/gmail/callback")


def get_oauth_flow():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GMAIL_CLIENT_ID,
                "client_secret": GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GMAIL_REDIRECT_URI],
            }
        },
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        redirect_uri=GMAIL_REDIRECT_URI,
    )
    return flow


async def get_valid_token(db: AsyncSession):
    from google.oauth2.credentials import Credentials

    from backend.models import GmailToken

    stmt = select(GmailToken).limit(1)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        raise RuntimeError("No Gmail tokens found. Run OAuth flow first.")

    creds = Credentials(
        token=row.access_token,
        refresh_token=row.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
    )

    # Refresh if expiring within 5 minutes
    if row.expires_at.timestamp() - time.time() < 300:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
        row.access_token = creds.token
        row.expires_at = datetime.fromtimestamp(creds.expiry.timestamp(), tz=timezone.utc) if creds.expiry else row.expires_at
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()

    return creds


async def store_tokens(db: AsyncSession, access_token: str, refresh_token: str, expires_at: datetime):
    from backend.models import GmailToken

    stmt = select(GmailToken).limit(1)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token = access_token
        existing.refresh_token = refresh_token
        existing.expires_at = expires_at
        existing.updated_at = datetime.now(timezone.utc)
    else:
        token = GmailToken(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )
        db.add(token)

    await db.commit()
