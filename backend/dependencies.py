import os
import uuid
import hashlib
import secrets
from datetime import datetime, timezone

import jwt
from fastapi import Cookie, Header, HTTPException, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db


# --- JWT Configuration ---

ACCESS_TOKEN_EXPIRY = 60 * 60  # 1 hour
REFRESH_TOKEN_EXPIRY = 60 * 60 * 24 * 30  # 30 days
REFRESH_COOKIE_NAME = "apptrail_refresh"


def _get_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        # Allow APPTRAIL_API_KEY as fallback ONLY in testing
        if os.getenv("TESTING") == "1":
            return os.getenv("APPTRAIL_API_KEY", "test-secret")
        raise RuntimeError(
            "JWT_SECRET environment variable is required. "
            "Set it to a random 256-bit secret before starting the server."
        )
    return secret


JWT_SECRET = _get_jwt_secret()
JWT_ALGORITHM = "HS256"


# --- Token Blacklist (in-memory for now, Redis in GAP-003) ---

_token_blacklist: set[str] = set()


def blacklist_token(jti: str) -> None:
    """Add a token's JTI to the blacklist."""
    _token_blacklist.add(jti)


def is_token_blacklisted(jti: str) -> bool:
    """Check if a token JTI has been revoked."""
    return jti in _token_blacklist


# --- Token Creation ---

def create_jwt(user_id: str, email: str, name: str | None = None, picture: str | None = None) -> str:
    """Create a short-lived access token (1 hour)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name or "",
        "picture": picture or "",
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now.timestamp() + ACCESS_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token (30 days)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now.timestamp() + REFRESH_TOKEN_EXPIRY,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"aptk_{secrets.token_urlsafe(32)}"


# --- Token Decoding ---

def decode_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Check blacklist
        jti = payload.get("jti")
        if jti and is_token_blacklisted(jti):
            raise HTTPException(status_code=401, detail="Token has been revoked")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token specifically."""
    payload = decode_jwt(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return payload


# --- Auth Dependencies ---

async def verify_api_key(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Accepts either a Bearer API key or a Bearer JWT token.

    Returns a dict with user context:
    - For JWT: {"user_id": <uuid>, "auth_type": "jwt"}
    - For API key: {"user_id": <uuid>, "auth_type": "api_key"}
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization[7:]

    # Try JWT (dashboard auth)
    try:
        payload = decode_jwt(token)
        return {"auth_type": "jwt", "user_id": payload["sub"]}
    except HTTPException:
        pass

    # Fallback to per-user API key lookup
    from backend.models import User

    hashed = hash_api_key(token)
    stmt = select(User).where(User.api_key_hash == hashed)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        user.api_key_last_used_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return {"auth_type": "api_key", "user_id": str(user.id)}

    raise HTTPException(status_code=401, detail="Invalid credentials")


async def get_current_user(authorization: str = Header(...), db: AsyncSession = Depends(get_db)):
    """Extract current user from JWT. Raises 401 if not a valid JWT session."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization[7:]
    payload = decode_jwt(token)

    from backend.models import User
    user_id = uuid.UUID(payload["sub"])
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def set_refresh_cookie(response, refresh_token: str) -> None:
    """Set the refresh token as an HttpOnly secure cookie on the response."""
    is_prod = os.getenv("ENVIRONMENT", "development") != "development"
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRY,
        path="/api/auth",
    )


def clear_refresh_cookie(response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
    )
