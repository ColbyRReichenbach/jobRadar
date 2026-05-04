import logging
import os
import time
import uuid
import hashlib
import secrets
from datetime import datetime, timezone

import jwt
from fastapi import Cookie, Header, HTTPException, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db

_logger = logging.getLogger(__name__)

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


# --- Token Blacklist (Redis-backed with in-memory fallback) ---

_BLACKLIST_KEY_PREFIX = "apptrail:blacklist:"
_token_blacklist: set[str] = set()  # in-memory fallback
_redis_client = None


def _get_redis_client():
    global _redis_client
    if os.getenv("TESTING") == "1":
        return None
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        _logger.info("Token blacklist using Redis")
        return _redis_client
    except Exception as exc:
        _logger.warning("Redis unavailable for token blacklist, using in-memory fallback: %s", exc)
        _redis_client = None
        return None


def blacklist_token(jti: str) -> None:
    """Add a token's JTI to the blacklist (Redis with in-memory fallback)."""
    client = _get_redis_client()
    if client:
        try:
            client.setex(f"{_BLACKLIST_KEY_PREFIX}{jti}", ACCESS_TOKEN_EXPIRY, "1")
            return
        except Exception:
            _logger.warning("Redis blacklist write failed, falling back to in-memory")
    _token_blacklist.add(jti)


def is_token_blacklisted(jti: str) -> bool:
    """Check if a token JTI has been revoked."""
    client = _get_redis_client()
    if client:
        try:
            return bool(client.exists(f"{_BLACKLIST_KEY_PREFIX}{jti}"))
        except Exception:
            _logger.warning("Redis blacklist read failed, falling back to in-memory")
    return jti in _token_blacklist


# --- One-Time Auth Code Exchange ---
# After Google OAuth, we store a short-lived code in Redis/memory that the
# frontend exchanges for the real JWT. This avoids putting the JWT in the URL.

_AUTH_CODE_PREFIX = "apptrail:authcode:"
_AUTH_CODE_TTL = 120  # 2 minutes
_auth_code_store: dict[str, tuple[str, float]] = {}  # local dev/test fallback: code -> (payload, expires_at)


class AuthCodeStoreUnavailableError(RuntimeError):
    """Raised when production auth-code storage cannot safely issue or consume codes."""


def _auth_code_memory_fallback_allowed() -> bool:
    environment = os.getenv("ENVIRONMENT", "development").lower()
    return os.getenv("TESTING") == "1" or environment == "development"


def _require_auth_code_store_available() -> None:
    if not _auth_code_memory_fallback_allowed():
        raise AuthCodeStoreUnavailableError(
            "Redis is required for OAuth auth-code exchange outside development."
        )


def _purge_expired_auth_codes(*, now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired_codes = [code for code, (_, expires_at) in _auth_code_store.items() if expires_at <= current]
    for code in expired_codes:
        _auth_code_store.pop(code, None)


def store_auth_code(code: str, payload_json: str) -> None:
    """Store a one-time auth code that maps to a JWT payload."""
    client = _get_redis_client()
    if client:
        try:
            client.setex(f"{_AUTH_CODE_PREFIX}{code}", _AUTH_CODE_TTL, payload_json)
            return
        except Exception:
            _logger.warning("Redis auth code store failed")
    _require_auth_code_store_available()
    _purge_expired_auth_codes()
    _auth_code_store[code] = (payload_json, time.time() + _AUTH_CODE_TTL)


def consume_auth_code(code: str) -> str | None:
    """Retrieve and delete a one-time auth code. Returns the payload JSON or None."""
    client = _get_redis_client()
    if client:
        try:
            pipe = client.pipeline()
            pipe.get(f"{_AUTH_CODE_PREFIX}{code}")
            pipe.delete(f"{_AUTH_CODE_PREFIX}{code}")
            results = pipe.execute()
            return results[0]
        except Exception:
            _logger.warning("Redis auth code consume failed")
    _require_auth_code_store_available()
    _purge_expired_auth_codes()
    stored = _auth_code_store.pop(code, None)
    if not stored:
        return None
    payload_json, expires_at = stored
    if expires_at <= time.time():
        return None
    return payload_json


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


def decode_access_token(token: str) -> dict:
    """Decode and validate a dashboard access token specifically."""
    payload = decode_jwt(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid access token")
    return payload


# --- Auth Dependencies ---

async def verify_api_key(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Accepts either a Bearer API key or a Bearer JWT token.

    Returns a dict with user context:
    - For JWT: {"user_id": <uuid>, "auth_type": "jwt"}
    - For API key: {"user_id": <uuid>, "auth_type": "api_key"}
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization[7:]

    # Try JWT (dashboard auth)
    try:
        payload = decode_access_token(token)
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


async def get_current_user(authorization: str | None = Header(None), db: AsyncSession = Depends(get_db)):
    """Extract current user from JWT. Raises 401 if not a valid JWT session."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization[7:]
    payload = decode_access_token(token)

    from backend.models import User
    user_id = uuid.UUID(payload["sub"])
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _admin_email_set() -> set[str]:
    raw = os.getenv("APPTRAIL_ADMIN_EMAILS", "")
    return {
        item.strip().lower()
        for item in raw.split(",")
        if item.strip()
    }


def is_admin_user(user) -> bool:
    """Return whether a user should receive dashboard admin access."""
    email = (getattr(user, "email", "") or "").lower()
    return bool(getattr(user, "is_admin", False) or email in _admin_email_set())


async def require_admin_user(
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Require an authenticated user with admin privileges."""
    from backend.models import User

    if auth.get("auth_type") != "jwt":
        raise HTTPException(status_code=403, detail="Dashboard session required")

    user_id = auth.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user context")

    try:
        user_uuid = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid user context") from exc

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if is_admin_user(user):
        return user

    raise HTTPException(status_code=403, detail="Admin access required")


def set_refresh_cookie(response, refresh_token: str) -> None:
    """Set the refresh token as an HttpOnly secure cookie on the response."""
    is_prod = os.getenv("ENVIRONMENT", "development") != "development"
    same_site = "none" if is_prod else "lax"
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite=same_site,
        max_age=REFRESH_TOKEN_EXPIRY,
        path="/api/auth",
    )


def clear_refresh_cookie(response) -> None:
    """Clear the refresh token cookie."""
    is_prod = os.getenv("ENVIRONMENT", "development") != "development"
    same_site = "none" if is_prod else "lax"
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        secure=is_prod,
        samesite=same_site,
        path="/api/auth",
    )


async def check_ai_consent(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Return True if the user has granted ai_processing consent."""
    from backend.models import DataConsent
    result = await db.execute(
        select(DataConsent).where(
            DataConsent.user_id == user_id,
            DataConsent.consent_type == "ai_processing",
            DataConsent.granted == True,
        )
    )
    return result.scalar_one_or_none() is not None


async def check_enrichment_consent(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Return True if the user has granted third_party_enrichment consent."""
    from backend.models import DataConsent
    result = await db.execute(
        select(DataConsent).where(
            DataConsent.user_id == user_id,
            DataConsent.consent_type == "third_party_enrichment",
            DataConsent.granted == True,
        )
    )
    return result.scalar_one_or_none() is not None


async def check_web_research_consent(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Return True if the user has granted web_research consent."""
    from backend.models import DataConsent
    result = await db.execute(
        select(DataConsent).where(
            DataConsent.user_id == user_id,
            DataConsent.consent_type == "web_research",
            DataConsent.granted == True,
        )
    )
    return result.scalar_one_or_none() is not None


async def check_source_intelligence_consent(user_id: uuid.UUID, db: AsyncSession) -> bool:
    """Return True if the user has granted source_intelligence consent."""
    from backend.models import DataConsent
    result = await db.execute(
        select(DataConsent).where(
            DataConsent.user_id == user_id,
            DataConsent.consent_type == "source_intelligence",
            DataConsent.granted == True,
        )
    )
    return result.scalar_one_or_none() is not None
