import csv
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import inspect as sa_inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import NO_VALUE

load_dotenv(override=os.getenv("TESTING") != "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from backend.database import async_session_factory, get_db
from backend.dependencies import verify_api_key, create_jwt, create_refresh_token, decode_jwt, decode_refresh_token, get_current_user, set_refresh_cookie, clear_refresh_cookie, blacklist_token, REFRESH_COOKIE_NAME, generate_api_key, hash_api_key, store_auth_code, consume_auth_code
from backend.gmail_token_crypto import decrypt_gmail_token, encrypt_gmail_token, is_gmail_token_encrypted, validate_gmail_token_encryption_config
from backend.logging_config import configure_logging
from backend.metrics import (
    REQUESTS_IN_PROGRESS,
    metrics_headers,
    metrics_payload,
    observe_request,
)
from backend.models import Application, Contact, ContactDistinctDecision, EmailEvent, EmailFeedback, User, GmailToken, Company, RoleUmbrella, CompanyTechProfile, UserProfile, UserRoleInterest, AtsBehavior, WarmConnection, Alert, Interview, CompanyVisit, InterviewNote, NotificationPreference, ResumeDraft, IgnoredNetworkContact, ExtractionReport, ExtractionChangelog, DataConsent, ResearchProfile, ResearchRun, ResearchSourceItem, OpportunitySignal, OpportunityScore, OpportunityBrief, RecommendedAction, ResearchFeedback
from backend.services.alerts import create_user_alert
from backend.services.ai_orchestrator import get_metrics_snapshot
from backend.monitoring import configure_sentry
from backend.services.hunter import find_contacts, generate_linkedin_search_url
from backend.services.opportunity_radar.action_generator import generate_actions
from backend.services.opportunity_radar.brief_generator import generate_briefs
from backend.services.opportunity_radar.signal_extractor import extract_signals
from backend.services.opportunity_radar.signal_scorer import score_signal
from backend.services.opportunity_radar.sources import collect_internal_sources
from backend.services.notification_preferences import is_alert_enabled, serialize_notification_preferences
from backend.services.scraper import extract_job, validate_job_parse_url
import structlog

configure_logging()
configure_sentry()
validate_gmail_token_encryption_config()

app = FastAPI(title="AppTrail API")
request_logger = structlog.get_logger("backend.request")
LOCAL_DEV_AUTH_ENABLED = os.getenv("LOCAL_DEV_AUTH", "").lower() in {"1", "true", "yes", "on"}

_cors_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
_dashboard_url = os.getenv("DASHBOARD_URL")
if _dashboard_url:
    _cors_origins.append(_dashboard_url.rstrip("/"))

_VERCEL_PREVIEW_ORIGIN_RE = re.compile(r"^https://apptrail[a-z0-9-]*\.vercel\.app$")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"^(chrome-extension://.*|https://apptrail[a-z0-9-]*\.vercel\.app)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_request_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _is_allowed_frontend_origin(origin: str | None) -> bool:
    if not origin:
        return False

    parsed = urlparse(origin)
    normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    if normalized in _cors_origins:
        return True

    return bool(_VERCEL_PREVIEW_ORIGIN_RE.fullmatch(normalized))


def _resolve_frontend_origin(frontend_origin: str | None, request: Request) -> str:
    candidates = [
        frontend_origin,
        request.headers.get("origin"),
        request.headers.get("referer"),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        parsed = urlparse(candidate)
        normalized = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if _is_allowed_frontend_origin(normalized):
            return normalized

    return os.getenv("DASHBOARD_URL", "http://localhost:5173").rstrip("/")


def _build_frontend_callback_url(frontend_url: str, auth_code: str) -> str:
    return f"{frontend_url}/auth/callback?code={quote(auth_code, safe='')}"


def _google_authorization_kwargs(connect_gmail: bool, connect_calendar: bool) -> dict:
    kwargs = {
        "prompt": "consent",
        "access_type": "offline",
    }
    if connect_gmail or connect_calendar:
        kwargs["include_granted_scopes"] = "true"
    return kwargs


def _encode_oauth_context(payload: dict) -> str:
    import base64
    import json

    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return encoded.rstrip("=")


def _decode_oauth_context(value: str) -> dict:
    import base64
    import json

    normalized = value + ("=" * (-len(value) % 4))
    return json.loads(base64.urlsafe_b64decode(normalized).decode())


def _build_google_authorization_response(request: Request, oauth_state: str | None = None) -> str:
    from urllib.parse import parse_qsl, urlencode

    query_items = parse_qsl(request.url.query, keep_blank_values=True)
    if oauth_state is not None:
        query_items = [
            ("state", oauth_state) if key == "state" else (key, value)
            for key, value in query_items
        ]
    query = urlencode(query_items)
    if query:
        return f"{GOOGLE_REDIRECT_URI}?{query}"
    return GOOGLE_REDIRECT_URI


_rate_limit_storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL")
limiter = Limiter(
    key_func=_get_request_ip,
    storage_uri=_rate_limit_storage_uri,
    in_memory_fallback_enabled=bool(_rate_limit_storage_uri),
)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse({"detail": str(exc.detail)}, status_code=429),
)
app.add_middleware(SlowAPIMiddleware)

MAX_REQUEST_BODY_BYTES = 1024 * 1024
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 100


def _metrics_path(request: Request) -> str:
    route = request.scope.get("route")
    if route and getattr(route, "path", None):
        return route.path
    return request.url.path


@app.middleware("http")
async def limit_request_body_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large. Limit is 1MB."},
                )
        except ValueError:
            pass

    if request.method in {"POST", "PUT", "PATCH"}:
        body = await request.body()
        if len(body) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large. Limit is 1MB."},
            )

    return await call_next(request)


@app.middleware("http")
async def bind_request_logging_context(request: Request, call_next):
    import structlog

    structlog.contextvars.clear_contextvars()
    request_id = (request.headers.get("x-request-id") or "").strip()[:255] or str(uuid4())
    start_time = time.perf_counter()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        request_logger.exception(
            "request_failed",
            duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
        )
        structlog.contextvars.clear_contextvars()
        raise

    response.headers["X-Request-ID"] = request_id
    request_logger.info(
        "request_completed",
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - start_time) * 1000, 2),
    )
    structlog.contextvars.clear_contextvars()
    return response


@app.middleware("http")
async def collect_request_metrics(request: Request, call_next):
    REQUESTS_IN_PROGRESS.inc()
    started_at = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        observe_request(
            method=request.method,
            path=_metrics_path(request),
            status_code=status_code,
            started_at=started_at,
        )
        REQUESTS_IN_PROGRESS.dec()


# --- Schemas ---

MAX_ID_LEN = 255
MAX_NAME_LEN = 255
MAX_URL_LEN = 2048
MAX_DOMAIN_LEN = 255
MAX_EMAIL_LEN = 320
MAX_PHONE_LEN = 32
MAX_STATUS_LEN = 64
MAX_PLATFORM_LEN = 100
MAX_SHORT_TEXT_LEN = 500
MAX_MEDIUM_TEXT_LEN = 2000
MAX_LONG_TEXT_LEN = 10000
MAX_RESUME_TEXT_LEN = 50000

class ApplicationCreate(BaseModel):
    company: str = Field(..., max_length=MAX_NAME_LEN)
    role_title: str = Field(..., max_length=MAX_NAME_LEN)
    job_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    source: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    department: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    description_text: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    salary: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    logo_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    location: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    status: Optional[str] = Field(None, max_length=MAX_STATUS_LEN)
    notes: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)


class ApplicationPatch(BaseModel):
    status: Optional[str] = Field(None, max_length=MAX_STATUS_LEN)
    notes: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    salary: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    location: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    logo_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    description_text: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    company: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    role_title: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    source: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    job_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)


class JobParseRequest(BaseModel):
    url: str = Field(..., max_length=MAX_URL_LEN)


class ContactsFindRequest(BaseModel):
    application_id: str = Field(..., max_length=MAX_ID_LEN)
    company: str = Field(..., max_length=MAX_NAME_LEN)
    domain: str = Field(..., max_length=MAX_DOMAIN_LEN)


class ContactCreate(BaseModel):
    name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    title: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    email: Optional[EmailStr] = None
    company_name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    phone_number: Optional[str] = Field(None, max_length=MAX_PHONE_LEN)
    linkedin_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    title: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    email: Optional[EmailStr] = None
    company_name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    phone_number: Optional[str] = Field(None, max_length=MAX_PHONE_LEN)
    linkedin_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    reached_out: Optional[bool] = None
    reached_out_at: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    response_received: Optional[bool] = None
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)


class EmailUpdate(BaseModel):
    collapsed: Optional[bool] = None
    read: Optional[bool] = None
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    classification: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    resolved: Optional[bool] = None
    hidden: Optional[bool] = None


class ResearchProfileCreate(BaseModel):
    name: str = Field(..., max_length=MAX_NAME_LEN)
    objective: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    selected_domains: list[str] = Field(default_factory=list)
    selected_roles: list[str] = Field(default_factory=list)
    selected_companies: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    mode: str = Field(default="internal", max_length=MAX_STATUS_LEN)
    frequency: str = Field(default="daily", max_length=MAX_STATUS_LEN)
    depth: str = Field(default="standard", max_length=MAX_STATUS_LEN)
    notification_mode: str = Field(default="in_app", max_length=MAX_STATUS_LEN)
    minimum_score: int = Field(default=70, ge=0, le=100)
    target_locations: list[str] = Field(default_factory=list)
    remote_types: list[str] = Field(default_factory=list)
    seniority_levels: list[str] = Field(default_factory=list)
    research_source_scopes: list[str] = Field(default_factory=list)
    use_profile_context: bool = True
    include_public_web_research: bool = False
    report_prompt_notes: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    max_search_queries: int = Field(default=8, ge=1, le=25)
    max_sources_per_run: int = Field(default=20, ge=1, le=100)
    active: bool = True


class ResearchProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    objective: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    selected_domains: Optional[list[str]] = None
    selected_roles: Optional[list[str]] = None
    selected_companies: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    excluded_keywords: Optional[list[str]] = None
    source_types: Optional[list[str]] = None
    mode: Optional[str] = Field(None, max_length=MAX_STATUS_LEN)
    frequency: Optional[str] = Field(None, max_length=MAX_STATUS_LEN)
    depth: Optional[str] = Field(None, max_length=MAX_STATUS_LEN)
    notification_mode: Optional[str] = Field(None, max_length=MAX_STATUS_LEN)
    minimum_score: Optional[int] = Field(None, ge=0, le=100)
    target_locations: Optional[list[str]] = None
    remote_types: Optional[list[str]] = None
    seniority_levels: Optional[list[str]] = None
    research_source_scopes: Optional[list[str]] = None
    use_profile_context: Optional[bool] = None
    include_public_web_research: Optional[bool] = None
    report_prompt_notes: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    max_search_queries: Optional[int] = Field(None, ge=1, le=25)
    max_sources_per_run: Optional[int] = Field(None, ge=1, le=100)
    active: Optional[bool] = None


class RecommendedActionUpdate(BaseModel):
    status: Literal["open", "accepted", "dismissed", "completed"]


class ResearchFeedbackCreate(BaseModel):
    signal_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    brief_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    action_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    report_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    run_step_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    feedback_scope: str = Field(default="signal", max_length=MAX_STATUS_LEN)
    rating: str = Field(..., max_length=MAX_STATUS_LEN)
    notes: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)


_ACTION_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "open": {"accepted", "dismissed", "completed"},
    "accepted": {"completed", "dismissed"},
    "dismissed": set(),
    "completed": set(),
}


class SearchMatchPreviewJob(BaseModel):
    id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    title: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    company: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    location: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    salary: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    description: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    url: Optional[str] = Field(None, max_length=MAX_URL_LEN)


class SearchMatchPreviewPayload(BaseModel):
    jobs: list[SearchMatchPreviewJob]


class JobDuplicateCheckPayload(BaseModel):
    company: str = Field(..., max_length=MAX_NAME_LEN)
    role_title: str = Field(..., max_length=MAX_NAME_LEN)
    job_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    location: Optional[str] = Field(None, max_length=MAX_NAME_LEN)


class ContactDuplicateCheckPayload(BaseModel):
    contact_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    email: Optional[EmailStr] = None


class ContactKeepSeparatePayload(BaseModel):
    name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    email: EmailStr
    match_email: EmailStr


class ContactMergePayload(BaseModel):
    target_contact_id: str = Field(..., max_length=MAX_ID_LEN)
    source_contact_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    title: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    email: Optional[EmailStr] = None
    company_name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    phone_number: Optional[str] = Field(None, max_length=MAX_PHONE_LEN)
    linkedin_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)


# --- Helpers ---

import uuid as _uuid


def _get_user_id(auth: dict) -> _uuid.UUID | None:
    """Extract user_id from auth context. Returns None for API-key auth."""
    uid = auth.get("user_id")
    if uid:
        return _uuid.UUID(uid) if isinstance(uid, str) else uid
    return None


def _require_user_id(auth: dict) -> _uuid.UUID:
    """Require a JWT-authenticated user context for user-owned routes."""
    user_id = _get_user_id(auth)
    if not user_id:
        raise HTTPException(status_code=401, detail="JWT authentication required")
    return user_id


def _infer_logo_domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    from backend.services.company_identity import is_company_domain
    if not is_company_domain(host):
        return None
    return host


async def _resolve_search_logo_url(
    db: AsyncSession,
    company_name: str | None,
    url: str | None,
    include_logo: bool,
) -> str | None:
    if not include_logo:
        return None

    from sqlalchemy import func
    from backend.services.company_identity import company_name_to_logo_url, get_logo_url

    normalized_company = (company_name or "").strip()
    if normalized_company:
        stmt = select(Company).where(func.lower(Company.name) == normalized_company.lower()).limit(1)
        result = await db.execute(stmt)
        company = result.scalar_one_or_none()
        if company:
            if company.logo_url:
                return company.logo_url
            if company.domain:
                return get_logo_url(company.domain)
        canonical_logo = company_name_to_logo_url(company_name)
        if canonical_logo:
            return canonical_logo

    inferred_domain = _infer_logo_domain_from_url(url)
    if inferred_domain:
        return get_logo_url(inferred_domain)
    return None


def _normalize_match_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _normalize_contact_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _sorted_contact_email_pair(email_a: str | None, email_b: str | None) -> tuple[str, str] | None:
    normalized_a = _normalize_contact_email(email_a)
    normalized_b = _normalize_contact_email(email_b)
    if not normalized_a or not normalized_b or normalized_a == normalized_b:
        return None
    return tuple(sorted((normalized_a, normalized_b)))


_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_PARAMS = {
    "gh_src",
    "gh_jid",
    "gh_src_id",
    "li_fat_id",
    "li_medium",
    "li_source",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
}


def _normalize_job_url(url: str | None) -> str | None:
    if not url:
        return None

    trimmed = url.strip()
    if not trimmed:
        return None

    parsed = urlparse(trimmed)
    if not parsed.scheme or not parsed.netloc:
        return trimmed

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(_TRACKING_QUERY_PREFIXES) and key.lower() not in _TRACKING_QUERY_PARAMS
    ]

    return urlunparse((
        scheme,
        netloc,
        path,
        "",
        urlencode(filtered_query, doseq=True),
        "",
    ))


async def _find_job_url_duplicate_for_user(db: AsyncSession, user_id: str, job_url: str | None) -> tuple[Application | None, str | None]:
    normalized_url = _normalize_job_url(job_url)
    if not normalized_url:
        return None, None

    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.job_url.is_not(None),
    )
    result = await db.execute(stmt)
    for app_row in result.scalars().all():
        if _normalize_job_url(app_row.job_url) == normalized_url:
            return app_row, normalized_url

    return None, normalized_url


def _parse_salary_numbers(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return (None, None)
    numbers = [int(part.replace(",", "")) for part in re.findall(r"[\d,]+", value)]
    if not numbers:
        return (None, None)
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    return (numbers[0], numbers[1])


def _fit_label(score: int) -> str:
    if score >= 75:
        return "best_fit"
    if score >= 45:
        return "good_fit"
    return "stretch"


def _score_search_preview(profile: UserProfile, user: User, preview: SearchMatchPreviewJob) -> dict:
    from backend.services.match_scorer import score_match

    profile_dict = {
        "skills": profile.skills or [],
        "tools": profile.tools or [],
        "experience_years": profile.experience_years,
    }
    description = preview.description or ""
    base_match = score_match(profile_dict, [], description)
    score = base_match["score"]
    preference_signals: list[str] = []

    normalized_location = _normalize_match_text(preview.location)
    preferred_locations = [_normalize_match_text(item) for item in (user.preferred_locations or []) if isinstance(item, str)]
    if normalized_location and preferred_locations and any(pref in normalized_location for pref in preferred_locations):
        score = min(100, score + 10)
        preference_signals.append("preferred_location")

    remote_pref = _normalize_match_text(user.preferred_remote_type)
    combined_text = _normalize_match_text(f"{preview.location or ''} {preview.description or ''}")
    if remote_pref and remote_pref != "onsite":
        if remote_pref == "remote" and "remote" in combined_text:
            score = min(100, score + 5)
            preference_signals.append("remote_match")
        elif remote_pref == "hybrid" and "hybrid" in combined_text:
            score = min(100, score + 5)
            preference_signals.append("hybrid_match")

    salary_min, salary_max = _parse_salary_numbers(preview.salary)
    if salary_min is not None and salary_max is not None:
        target_min = user.target_salary_min
        target_max = user.target_salary_max
        if target_min is not None and salary_max >= target_min:
            score = min(100, score + 5)
            preference_signals.append("salary_match")
        elif target_max is not None and salary_min <= target_max:
            score = min(100, score + 5)
            preference_signals.append("salary_match")

    return {
        **base_match,
        "score": score,
        "fit_label": _fit_label(score),
        "preference_signals": preference_signals,
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _contains_like(value: str) -> str:
    return f"%{_escape_like(value.lower())}%"


def _paginate(stmt, limit: int, offset: int):
    return stmt.limit(limit).offset(offset)


def _normalize_match_token(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _domain_match_tokens(domain: str | None) -> list[str]:
    if not domain:
        return []

    normalized_domain = domain.lower().strip()
    if not normalized_domain:
        return []

    parts = [part for part in normalized_domain.split(".") if part]
    candidates: list[str] = [normalized_domain]
    if len(parts) >= 2:
        candidates.append(".".join(parts[-2:]))
    candidates.extend(parts)

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        token = candidate.strip()
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _build_application_match_maps(app_rows: list[tuple[_uuid.UUID, str | None, str | None]]) -> tuple[dict[str, _uuid.UUID], dict[str, _uuid.UUID]]:
    domain_map: dict[str, _uuid.UUID] = {}
    token_map: dict[str, _uuid.UUID] = {}

    for app_id, company_name, company_domain in app_rows:
        for domain_token in _domain_match_tokens(company_domain):
            domain_map.setdefault(domain_token, app_id)

        for token in (
            _normalize_match_token(company_name),
            *[_normalize_match_token(domain_token) for domain_token in _domain_match_tokens(company_domain)],
        ):
            if token:
                token_map.setdefault(token, app_id)

    return domain_map, token_map


def _match_application_id_for_sender(
    sender_email_addr: str | None,
    domain_map: dict[str, _uuid.UUID],
    token_map: dict[str, _uuid.UUID],
) -> _uuid.UUID | None:
    if not sender_email_addr or "@" not in sender_email_addr:
        return None

    sender_domain = sender_email_addr.split("@", 1)[-1].lower()
    for domain_token in _domain_match_tokens(sender_domain):
        matched = domain_map.get(domain_token)
        if matched:
            return matched

    for token in (_normalize_match_token(domain_token) for domain_token in _domain_match_tokens(sender_domain)):
        matched = token_map.get(token)
        if matched:
            return matched

    return None


def _auth_rate_limit() -> str:
    return os.getenv("APPTRAIL_AUTH_RATE_LIMIT", "5/minute")


def _job_parse_rate_limit() -> str:
    return os.getenv("APPTRAIL_JOB_PARSE_RATE_LIMIT", "10/minute")


def _search_rate_limit() -> str:
    return os.getenv("APPTRAIL_SEARCH_RATE_LIMIT", "30/minute")


def _global_search_rate_limit() -> str:
    return os.getenv("APPTRAIL_GLOBAL_SEARCH_RATE_LIMIT", "60/minute")


def _contact_find_rate_limit() -> str:
    return os.getenv("APPTRAIL_CONTACT_FIND_RATE_LIMIT", "10/minute")


def _gmail_sync_rate_limit() -> str:
    return os.getenv("APPTRAIL_GMAIL_SYNC_RATE_LIMIT", "5/minute")


def _calendar_sync_rate_limit() -> str:
    return os.getenv("APPTRAIL_CALENDAR_SYNC_RATE_LIMIT", "5/minute")


def _send_email_rate_limit() -> str:
    return os.getenv("APPTRAIL_SEND_EMAIL_RATE_LIMIT", "10/minute")


def _serialize_app(app_row: Application, include_contacts: bool = False) -> dict:
    data = {
        "id": str(app_row.id),
        "company": app_row.company,
        "role_title": app_row.role_title,
        "department": app_row.department,
        "job_url": app_row.job_url,
        "source": app_row.source,
        "description_text": app_row.description_text,
        "salary": app_row.salary,
        "logo_url": app_row.logo_url,
        "location": app_row.location,
        "applied_at": app_row.applied_at.isoformat() if app_row.applied_at else None,
        "status": app_row.status,
        "status_updated_at": app_row.status_updated_at.isoformat() if app_row.status_updated_at else None,
        "archived_at": app_row.archived_at.isoformat() if app_row.archived_at else None,
        "follow_up_due": app_row.follow_up_due,
        "notes": app_row.notes,
        "company_id": str(app_row.company_id) if app_row.company_id else None,
        "umbrella_id": str(app_row.umbrella_id) if app_row.umbrella_id else None,
        "umbrella_name": app_row.umbrella.name if 'umbrella' in app_row.__dict__ and app_row.__dict__['umbrella'] is not None else None,
        "tech_stack": app_row.tech_stack or [],
        "match_score": app_row.match_score,
        "listing_alive": app_row.listing_alive,
        "listing_died_at": app_row.listing_died_at.isoformat() if app_row.listing_died_at else None,
        "first_response_days": app_row.first_response_days,
        "salary_min": app_row.salary_min,
        "salary_max": app_row.salary_max,
        "salary_currency": app_row.salary_currency,
        "salary_period": app_row.salary_period,
    }
    if include_contacts:
        data["contacts"] = [_serialize_contact(c) for c in app_row.contacts]
    return data


def _serialize_email_event(event: EmailEvent) -> dict:
    return {
        "id": str(event.id),
        "application_id": str(event.application_id) if event.application_id else None,
        "gmail_message_id": event.gmail_message_id,
        "thread_id": event.thread_id,
        "sender": event.sender,
        "sender_email": event.sender_email,
        "subject": event.subject,
        "body": event.body,
        "snippet": event.snippet or event.key_sentence,
        "received_at": event.received_at.isoformat() if event.received_at else None,
        "pipeline": event.pipeline,
        "classification": event.classification,
        "color_code": event.color_code,
        "urgency": event.urgency,
        "action_needed": event.action_needed,
        "action_url": event.action_url,
        "is_human": event.is_human,
        "is_from_user": event.is_from_user,
        "email_type": event.email_type,
        "key_sentence": event.key_sentence,
        "summary": event.summary,
        "read": event.read,
        "collapsed": event.collapsed,
        "hidden": event.hidden,
        "company_name": event.company_name,
        "company_logo_url": event.company_logo_url,
        "sender_domain": event.sender_domain,
        "confidence": event.confidence,
        "resolved": event.resolved,
        "company_id": str(event.company_id) if event.company_id else None,
        "application": {
            "company": event.application.company,
            "role_title": event.application.role_title,
        } if event.application else None,
    }


def _alert_action_url(path: str, **params: str | None) -> str:
    from urllib.parse import urlencode

    clean_params = {key: value for key, value in params.items() if value}
    query = urlencode(clean_params)
    return f"{path}?{query}" if query else path


def _email_alert_type(email_type: str | None, classification: str | None) -> str:
    if email_type == "conversation":
        return "conversation_message"
    return classification or "email_update"


def _serialize_contact(contact_row: Contact) -> dict:
    state = sa_inspect(contact_row)
    application = None
    company_ref = None

    application_value = state.attrs.application.loaded_value
    if application_value is not NO_VALUE:
        application = application_value

    company_value = state.attrs.company_ref.loaded_value
    if company_value is not NO_VALUE:
        company_ref = company_value

    company_name = contact_row.company_name
    if not company_name and company_ref:
        company_name = company_ref.name
    if not company_name and application:
        company_name = application.company

    return {
        "id": str(contact_row.id),
        "application_id": str(contact_row.application_id) if contact_row.application_id else None,
        "name": contact_row.name,
        "title": contact_row.title,
        "email": contact_row.email,
        "phone_number": contact_row.phone_number,
        "linkedin_url": contact_row.linkedin_url,
        "source": contact_row.source,
        "confidence_score": contact_row.confidence_score,
        "reached_out": contact_row.reached_out,
        "reached_out_at": contact_row.reached_out_at.isoformat() if contact_row.reached_out_at else None,
        "response_received": contact_row.response_received,
        "company": company_name,
        "company_id": str(contact_row.company_id) if contact_row.company_id else None,
    }


# --- Routes ---

@app.get("/api/health")
async def health(db: AsyncSession = Depends(get_db)):
    component_status = {
        "api": {"status": "ok"},
        "database": {"status": "ok"},
        "redis": {"status": "not_configured"},
    }
    overall_status = "ok"

    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        component_status["database"] = {"status": "error", "detail": str(exc)}
        overall_status = "degraded"

    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        import redis.asyncio as redis

        redis_client = redis.from_url(redis_url)
        try:
            await redis_client.ping()
            component_status["redis"] = {"status": "ok"}
        except Exception as exc:
            component_status["redis"] = {"status": "error", "detail": str(exc)}
            overall_status = "degraded"
        finally:
            await redis_client.aclose()

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": component_status,
    }


@app.get("/metrics")
async def prometheus_metrics():
    return Response(content=metrics_payload(), headers=metrics_headers())


@app.get("/api/ai/metrics")
async def ai_metrics(auth: dict = Depends(verify_api_key)):
    _require_user_id(auth)
    return get_metrics_snapshot()


@app.post("/api/jobs/parse", dependencies=[Depends(verify_api_key)])
@limiter.limit(_job_parse_rate_limit, error_message="Too many job parse requests. Try again in a minute.")
async def parse_job(request: Request, req: JobParseRequest):
    try:
        validated_url = await validate_job_parse_url(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = await extract_job(validated_url)
    return {"status": "ok", "data": result}


@app.post("/api/jobs", status_code=201)
async def create_application(payload: ApplicationCreate, auth: dict = Depends(verify_api_key), db: AsyncSession = Depends(get_db)):
    user_id = _require_user_id(auth)
    existing_job, normalized_job_url = await _find_job_url_duplicate_for_user(db, user_id, payload.job_url)

    # Check for duplicate job_url
    if existing_job:
        raise HTTPException(status_code=409, detail={"message": "Already tracked", "existing": _serialize_app(existing_job)})

    new_app = Application(
        user_id=user_id,
        company=payload.company,
        role_title=payload.role_title,
        job_url=normalized_job_url,
        source=payload.source,
        department=payload.department,
        description_text=payload.description_text,
        salary=payload.salary,
        logo_url=payload.logo_url,
        location=payload.location,
        notes=payload.notes,
    )
    if payload.status:
        new_app.status = payload.status

    # Sprint 2: Company upsert from job URL domain
    if normalized_job_url:
        from backend.services.company_service import upsert_company
        parsed_url = urlparse(normalized_job_url)
        domain = parsed_url.netloc.lower().replace("www.", "")
        if domain:
            company_entity = await upsert_company(db, domain)
            if company_entity:
                new_app.company_id = company_entity.id

    # Sprint 3: Role classification
    from backend.services.role_classifier import classify_role
    role_result = await classify_role(db, new_app.role_title, new_app.description_text or "")
    if role_result["umbrella_id"]:
        new_app.umbrella_id = role_result["umbrella_id"]

    # Sprint 4: Tech stack extraction
    if new_app.description_text:
        from backend.services.tech_extractor import extract_tech_stack
        tech = extract_tech_stack(new_app.description_text)
        new_app.tech_stack = [t["name"] for t in tech]

    db.add(new_app)
    try:
        await db.commit()
        await db.refresh(new_app)
    except IntegrityError:
        await db.rollback()
        # Race condition: another request for the same user inserted between our check and insert.
        existing, _ = await _find_job_url_duplicate_for_user(db, user_id, normalized_job_url)
        if existing:
            raise HTTPException(status_code=409, detail={"message": "Already tracked", "existing": _serialize_app(existing)})
        raise HTTPException(status_code=409, detail={"message": "Unable to create application for this job URL"})

    # Sprint 4: Update company tech profile
    if new_app.company_id and new_app.tech_stack:
        from backend.services.tech_extractor import extract_tech_stack as _extract
        tech_items = _extract(new_app.description_text or "")
        for t in tech_items:
            stmt = select(CompanyTechProfile).where(
                CompanyTechProfile.company_id == new_app.company_id,
                CompanyTechProfile.tech_name == t["name"],
            )
            result = await db.execute(stmt)
            profile = result.scalar_one_or_none()
            if profile:
                profile.mention_count += 1
                profile.last_seen_at = datetime.now(timezone.utc)
            else:
                db.add(CompanyTechProfile(
                    company_id=new_app.company_id,
                    tech_name=t["name"],
                    category=t["category"],
                ))
        await db.commit()

    return _serialize_app(new_app)


@app.post("/api/jobs/duplicates/check")
async def check_job_duplicates(
    payload: JobDuplicateCheckPayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)

    exact, normalized_job_url = await _find_job_url_duplicate_for_user(db, user_id, payload.job_url)
    if exact:
        return {
            "duplicate_type": "hard",
            "message": "This job URL is already in your pipeline.",
            "matches": [_serialize_app(exact)],
        }

    company_key = _normalize_match_text(payload.company)
    role_key = _normalize_match_text(payload.role_title)
    location_key = _normalize_match_text(payload.location)

    stmt = select(Application).where(Application.user_id == user_id)
    result = await db.execute(stmt)
    matches = []
    for app_row in result.scalars().all():
        if exact is not None and app_row.id == exact.id:
            continue
        if normalized_job_url and _normalize_job_url(app_row.job_url) == normalized_job_url:
            continue
        if _normalize_match_text(app_row.company) != company_key:
            continue
        if _normalize_match_text(app_row.role_title) != role_key:
            continue
        if location_key and _normalize_match_text(app_row.location) not in {"", location_key}:
            continue
        matches.append(_serialize_app(app_row))

    if matches:
        return {
            "duplicate_type": "soft",
            "message": "We found a similar role already in your pipeline. Review before saving a duplicate.",
            "matches": matches[:5],
        }

    return {
        "duplicate_type": "none",
        "message": None,
        "matches": [],
    }


@app.get("/api/jobs")
async def list_applications(
    status: Optional[str] = Query(None),
    archived: Optional[bool] = Query(None),
    umbrella_id: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload

    user_id = _require_user_id(auth)
    stmt = select(Application).options(
        selectinload(Application.contacts),
        selectinload(Application.umbrella),
    )
    stmt = stmt.where(Application.user_id == user_id)
    if not archived:
        stmt = stmt.where(Application.archived_at.is_(None))
    if status:
        stmt = stmt.where(Application.status == status)
    if umbrella_id:
        stmt = stmt.where(Application.umbrella_id == _uuid.UUID(umbrella_id))
    stmt = stmt.order_by(Application.applied_at.desc())
    stmt = _paginate(stmt, limit, offset)

    result = await db.execute(stmt)
    apps = result.scalars().unique().all()
    return [_serialize_app(a, include_contacts=True) for a in apps]


@app.patch("/api/jobs/{job_id}")
async def update_application(
    job_id: str,
    payload: ApplicationPatch,
    auth: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    user_id = _require_user_id(auth)
    jid = _uuid.UUID(job_id)
    stmt = select(Application).where(
        Application.id == jid,
        Application.user_id == user_id,
    )
    result = await db.execute(stmt)
    app_row = result.scalar_one_or_none()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")

    if payload.status is not None:
        app_row.status = payload.status
        app_row.status_updated_at = datetime.now(timezone.utc)
    if payload.notes is not None:
        app_row.notes = payload.notes
    if payload.salary is not None:
        app_row.salary = payload.salary
    if payload.location is not None:
        app_row.location = payload.location
    if payload.logo_url is not None:
        app_row.logo_url = payload.logo_url
    if payload.description_text is not None:
        app_row.description_text = payload.description_text
    if payload.company is not None:
        app_row.company = payload.company
    if payload.role_title is not None:
        app_row.role_title = payload.role_title
    if payload.source is not None:
        app_row.source = payload.source
    if payload.job_url is not None:
        app_row.job_url = _normalize_job_url(payload.job_url)

    await db.commit()
    await db.refresh(app_row)
    return _serialize_app(app_row)


@app.get("/api/contacts")
async def list_contacts(auth: dict = Depends(verify_api_key)):
    return []


@app.post("/api/contacts/find")
@limiter.limit(_contact_find_rate_limit, error_message="Too many contact lookup requests. Try again in a minute.")
async def find_contacts_endpoint(
    request: Request,
    req: ContactsFindRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    from backend.dependencies import check_enrichment_consent

    app_id = _uuid.UUID(req.application_id)
    app_stmt = select(Application).where(
        Application.id == app_id,
        Application.user_id == user_id,
    )
    app_result = await db.execute(app_stmt)
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Look up user's school for LinkedIn alumni search
    profile_stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    profile_result = await db.execute(profile_stmt)
    user_profile = profile_result.scalar_one_or_none()
    user_school = None
    if user_profile and user_profile.education:
        # education is a JSON list — use the first school name
        for edu in user_profile.education:
            school_name = edu if isinstance(edu, str) else edu.get("school") or edu.get("name")
            if school_name:
                user_school = school_name
                break

    # Check cache: existing contacts for this application fetched within 30 days
    stmt = select(Contact).where(
        Contact.application_id == app_id,
        Contact.user_id == user_id,
    )
    result = await db.execute(stmt)
    existing_contacts = result.scalars().all()
    if existing_contacts:
        linkedin_url = generate_linkedin_search_url(req.company, school=user_school)
        return {
            "contacts": [_serialize_contact(c) for c in existing_contacts],
            "linkedin_search_url": linkedin_url,
            "cached": True,
        }

    linkedin_url = generate_linkedin_search_url(req.company, school=user_school)
    enrichment_enabled = await check_enrichment_consent(user_id, db)
    if not enrichment_enabled:
        return {
            "contacts": [],
            "linkedin_search_url": linkedin_url,
            "cached": False,
            "enrichment_enabled": False,
        }

    # Call Hunter.io
    contacts_data = await find_contacts(req.domain, req.company)

    # Write to DB
    saved_contacts = []
    for c in contacts_data:
        contact = Contact(
            application_id=app_id,
            company_id=app.company_id,
            name=c.get("name"),
            title=c.get("title"),
            email=c.get("email"),
            confidence_score=c.get("confidence_score"),
            source="hunter",
            user_id=user_id,
        )
        db.add(contact)
        saved_contacts.append(contact)

    await db.commit()
    for c in saved_contacts:
        await db.refresh(c)

    return {
        "contacts": [_serialize_contact(c) for c in saved_contacts],
        "linkedin_search_url": linkedin_url,
        "cached": False,
        "enrichment_enabled": True,
    }


@app.patch("/api/contacts/{contact_id}")
async def update_contact(
    contact_id: str,
    payload: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    from datetime import datetime, timezone

    cid = _uuid.UUID(contact_id)
    stmt = select(Contact).where(
        Contact.id == cid,
        Contact.user_id == user_id,
    )
    result = await db.execute(stmt)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if payload.name is not None:
        contact.name = payload.name
    if payload.title is not None:
        contact.title = payload.title
    if payload.email is not None:
        contact.email = _normalize_contact_email(str(payload.email))
    if payload.company_name is not None:
        contact.company_name = payload.company_name
    if payload.phone_number is not None:
        contact.phone_number = payload.phone_number
    if payload.linkedin_url is not None:
        contact.linkedin_url = payload.linkedin_url
    if payload.reached_out is not None:
        contact.reached_out = payload.reached_out
    if payload.reached_out_at is not None:
        contact.reached_out_at = datetime.fromisoformat(payload.reached_out_at)
    elif payload.reached_out:
        contact.reached_out_at = datetime.now(timezone.utc)
    if payload.response_received is not None:
        contact.response_received = payload.response_received
    if payload.application_id is not None:
        if payload.application_id == "":
            contact.application_id = None
        else:
            app_id = _uuid.UUID(payload.application_id)
            app_stmt = select(Application).where(
                Application.id == app_id,
                Application.user_id == user_id,
            )
            app_result = await db.execute(app_stmt)
            app = app_result.scalar_one_or_none()
            if not app:
                raise HTTPException(status_code=404, detail="Application not found")
            contact.application_id = app.id

    if contact.email:
        ignored_stmt = select(IgnoredNetworkContact).where(
            IgnoredNetworkContact.user_id == user_id,
            IgnoredNetworkContact.email == contact.email.lower(),
        )
        ignored_result = await db.execute(ignored_stmt)
        ignored_contact = ignored_result.scalar_one_or_none()
        if ignored_contact:
            await db.delete(ignored_contact)

    await db.commit()
    contact_stmt = (
        select(Contact)
        .options(selectinload(Contact.application), selectinload(Contact.company_ref))
        .where(Contact.id == contact.id, Contact.user_id == user_id)
    )
    contact_result = await db.execute(contact_stmt)
    return _serialize_contact(contact_result.scalar_one())


@app.post("/api/contacts", status_code=201)
async def create_contact(
    payload: ContactCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)

    app_id = None
    if payload.application_id:
        app_id = _uuid.UUID(payload.application_id)
        app_stmt = select(Application).where(
            Application.id == app_id,
            Application.user_id == user_id,
        )
        app_result = await db.execute(app_stmt)
        if not app_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Application not found")

    contact = Contact(
        user_id=user_id,
        application_id=app_id,
        name=payload.name,
        title=payload.title,
        email=_normalize_contact_email(str(payload.email) if payload.email else None),
        company_name=payload.company_name,
        phone_number=payload.phone_number,
        linkedin_url=payload.linkedin_url,
        source="manual",
    )
    db.add(contact)

    if contact.email:
        ignored_stmt = select(IgnoredNetworkContact).where(
            IgnoredNetworkContact.user_id == user_id,
            IgnoredNetworkContact.email == contact.email.lower(),
        )
        ignored_result = await db.execute(ignored_stmt)
        ignored_contact = ignored_result.scalar_one_or_none()
        if ignored_contact:
            await db.delete(ignored_contact)

    await db.commit()
    contact_stmt = (
        select(Contact)
        .options(selectinload(Contact.application), selectinload(Contact.company_ref))
        .where(Contact.id == contact.id, Contact.user_id == user_id)
    )
    contact_result = await db.execute(contact_stmt)
    return _serialize_contact(contact_result.scalar_one())


@app.post("/api/contacts/duplicates/check")
async def check_contact_duplicates(
    payload: ContactDuplicateCheckPayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    exclude_contact_id = _uuid.UUID(payload.contact_id) if payload.contact_id else None
    email_value = _normalize_contact_email(str(payload.email) if payload.email else None)
    normalized_name = _normalize_match_text(payload.name)

    stmt = select(Contact).where(Contact.user_id == user_id)
    result = await db.execute(stmt)
    separate_pairs_result = await db.execute(
        select(ContactDistinctDecision.email_a, ContactDistinctDecision.email_b).where(
            ContactDistinctDecision.user_id == user_id
        )
    )
    separate_pairs = {
        tuple(sorted((email_a, email_b)))
        for email_a, email_b in separate_pairs_result.all()
        if email_a and email_b
    }

    hard_matches = []
    soft_matches = []
    for contact in result.scalars().all():
        if exclude_contact_id and contact.id == exclude_contact_id:
            continue
        serialized = _serialize_contact(contact)
        contact_email = _normalize_contact_email(contact.email)
        if email_value and contact_email == email_value:
            hard_matches.append(serialized)
            continue
        if normalized_name and _normalize_match_text(contact.name) == normalized_name:
            decision_pair = _sorted_contact_email_pair(email_value, contact_email)
            if decision_pair and decision_pair in separate_pairs:
                continue
            soft_matches.append(serialized)

    if hard_matches:
        return {
            "duplicate_type": "hard",
            "message": "A contact with this email already exists.",
            "matches": hard_matches[:5],
        }

    if soft_matches:
        return {
            "duplicate_type": "soft",
            "message": "We found another contact with this name. Review before saving.",
            "matches": soft_matches[:5],
        }

    return {
        "duplicate_type": "none",
        "message": None,
        "matches": [],
    }


@app.post("/api/contacts/duplicates/keep-separate", status_code=201)
async def keep_contacts_separate(
    payload: ContactKeepSeparatePayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    email_pair = _sorted_contact_email_pair(str(payload.email), str(payload.match_email))
    if not email_pair:
        raise HTTPException(status_code=400, detail="Two distinct contact emails are required")

    stmt = select(ContactDistinctDecision).where(
        ContactDistinctDecision.user_id == user_id,
        ContactDistinctDecision.email_a == email_pair[0],
        ContactDistinctDecision.email_b == email_pair[1],
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is None:
        db.add(
            ContactDistinctDecision(
                user_id=user_id,
                name_key=_normalize_match_text(payload.name),
                email_a=email_pair[0],
                email_b=email_pair[1],
            )
        )
        await db.commit()

    return {"status": "ok"}


@app.post("/api/contacts/merge")
async def merge_contacts(
    payload: ContactMergePayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    target_id = _uuid.UUID(payload.target_contact_id)
    source_id = _uuid.UUID(payload.source_contact_id) if payload.source_contact_id else None

    target_stmt = select(Contact).where(Contact.id == target_id, Contact.user_id == user_id)
    target_result = await db.execute(target_stmt)
    target_contact = target_result.scalar_one_or_none()
    if not target_contact:
        raise HTTPException(status_code=404, detail="Target contact not found")

    source_contact = None
    if source_id:
        source_stmt = select(Contact).where(Contact.id == source_id, Contact.user_id == user_id)
        source_result = await db.execute(source_stmt)
        source_contact = source_result.scalar_one_or_none()
        if not source_contact:
            raise HTTPException(status_code=404, detail="Source contact not found")
        if source_contact.id == target_contact.id:
            raise HTTPException(status_code=400, detail="Cannot merge a contact into itself")

    application_id = None
    if payload.application_id:
        application_id = _uuid.UUID(payload.application_id)
        app_stmt = select(Application).where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
        app_result = await db.execute(app_stmt)
        if not app_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Application not found")

    if payload.name is not None:
        target_contact.name = payload.name or None
    if payload.title is not None:
        target_contact.title = payload.title or None
    if payload.email is not None:
        target_contact.email = _normalize_contact_email(str(payload.email))
    if payload.company_name is not None:
        target_contact.company_name = payload.company_name or None
    if payload.phone_number is not None:
        target_contact.phone_number = payload.phone_number or None
    if payload.linkedin_url is not None:
        target_contact.linkedin_url = payload.linkedin_url or None
    if application_id is not None:
        target_contact.application_id = application_id

    if source_contact:
        if not target_contact.application_id and source_contact.application_id:
            target_contact.application_id = source_contact.application_id
        if not target_contact.company_name and source_contact.company_name:
            target_contact.company_name = source_contact.company_name
        if not target_contact.phone_number and source_contact.phone_number:
            target_contact.phone_number = source_contact.phone_number
        if not target_contact.linkedin_url and source_contact.linkedin_url:
            target_contact.linkedin_url = source_contact.linkedin_url

        await db.execute(
            update(EmailEvent)
            .where(EmailEvent.user_id == user_id, EmailEvent.contact_id == source_contact.id)
            .values(contact_id=target_contact.id)
        )
        await db.delete(source_contact)

    if target_contact.email:
        ignored_stmt = select(IgnoredNetworkContact).where(
            IgnoredNetworkContact.user_id == user_id,
            IgnoredNetworkContact.email == target_contact.email,
        )
        ignored_result = await db.execute(ignored_stmt)
        ignored_contact = ignored_result.scalar_one_or_none()
        if ignored_contact:
            await db.delete(ignored_contact)

    email_pair = _sorted_contact_email_pair(target_contact.email, source_contact.email if source_contact else None)
    if email_pair:
        decision_stmt = select(ContactDistinctDecision).where(
            ContactDistinctDecision.user_id == user_id,
            ContactDistinctDecision.email_a == email_pair[0],
            ContactDistinctDecision.email_b == email_pair[1],
        )
        decision_result = await db.execute(decision_stmt)
        decision = decision_result.scalar_one_or_none()
        if decision:
            await db.delete(decision)

    await db.commit()
    merged_stmt = (
        select(Contact)
        .options(selectinload(Contact.application), selectinload(Contact.company_ref))
        .where(Contact.id == target_contact.id, Contact.user_id == user_id)
    )
    merged_result = await db.execute(merged_stmt)
    return _serialize_contact(merged_result.scalar_one())


@app.delete("/api/contacts/{contact_id}")
async def delete_contact(
    contact_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    cid = _uuid.UUID(contact_id)
    stmt = select(Contact).where(
        Contact.id == cid,
        Contact.user_id == user_id,
    )
    result = await db.execute(stmt)
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    email_value = (contact.email or "").lower()
    await db.delete(contact)

    if email_value:
        ignored_stmt = select(IgnoredNetworkContact).where(
            IgnoredNetworkContact.user_id == user_id,
            IgnoredNetworkContact.email == email_value,
        )
        ignored_result = await db.execute(ignored_stmt)
        if not ignored_result.scalar_one_or_none():
            db.add(IgnoredNetworkContact(user_id=user_id, email=email_value))

    await db.commit()
    return {"status": "ok"}


@app.get("/api/emails")
async def list_emails(
    application_id: Optional[str] = Query(None),
    unmatched: Optional[bool] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    from sqlalchemy.orm import selectinload

    stmt = select(EmailEvent).options(selectinload(EmailEvent.application)).where(
        EmailEvent.user_id == user_id,
        EmailEvent.hidden.is_(False),
    )

    if application_id:
        stmt = stmt.where(EmailEvent.application_id == _uuid.UUID(application_id))
    elif unmatched:
        stmt = stmt.where(EmailEvent.application_id.is_(None))
    else:
        stmt = stmt.where(EmailEvent.collapsed.is_(False))

    stmt = stmt.order_by(EmailEvent.received_at.desc())
    stmt = _paginate(stmt, limit, offset)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [_serialize_email_event(e) for e in events]


@app.patch("/api/emails/{email_id}")
async def update_email(
    email_id: str,
    payload: EmailUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)

    eid = _uuid.UUID(email_id)
    stmt = select(EmailEvent).where(
        EmailEvent.id == eid,
        EmailEvent.user_id == user_id,
    )
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Email event not found")

    if payload.collapsed is not None:
        event.collapsed = payload.collapsed
    if payload.read is not None:
        event.read = payload.read
    if payload.application_id is not None:
        target_app_id = _uuid.UUID(payload.application_id)
        app_stmt = select(Application).where(
            Application.id == target_app_id,
            Application.user_id == user_id,
        )
        app_result = await db.execute(app_stmt)
        if not app_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Application not found")
        event.application_id = target_app_id
    if payload.classification is not None:
        event.classification = payload.classification
    if payload.resolved is not None:
        event.resolved = payload.resolved
        if payload.resolved:
            event.collapsed = True
        else:
            event.collapsed = False
    if payload.hidden is not None:
        event.hidden = payload.hidden
        if payload.hidden:
            event.collapsed = True

    await db.commit()
    await db.refresh(event)

    # Re-fetch with relationship loaded
    from sqlalchemy.orm import selectinload
    stmt = select(EmailEvent).options(selectinload(EmailEvent.application)).where(
        EmailEvent.id == eid,
        EmailEvent.user_id == user_id,
    )
    result = await db.execute(stmt)
    event = result.scalar_one()
    return _serialize_email_event(event)


class EmailFeedbackCreate(BaseModel):
    email_id: str = Field(..., max_length=MAX_ID_LEN)
    is_job_related: bool


@app.post("/api/emails/feedback", status_code=201)
async def create_email_feedback(
    payload: EmailFeedbackCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """User feedback: mark an email as job-related or not. Builds sender blocklist over time."""
    user_id = _require_user_id(auth)

    eid = _uuid.UUID(payload.email_id)
    stmt = select(EmailEvent).where(
        EmailEvent.id == eid,
        EmailEvent.user_id == user_id,
    )
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Email not found")

    # Extract pattern from subject for learning
    subject_pattern = None
    if event.subject:
        # Strip specific details, keep structural pattern
        import re
        pattern = re.sub(r'\b\d+\b', '#', event.subject)
        pattern = re.sub(r'\b[A-Z][a-z]+\b', '*', pattern)
        subject_pattern = pattern[:100]

    feedback = EmailFeedback(
        email_id=eid,
        is_job_related=payload.is_job_related,
        sender_domain=event.sender_domain,
        subject_pattern=subject_pattern,
    )
    db.add(feedback)

    # If not job related, collapse the email
    if not payload.is_job_related:
        event.collapsed = True
        event.classification = "not_relevant"

    await db.commit()
    return {"status": "ok", "feedback_id": str(feedback.id)}


@app.get("/api/emails/feedback/stats")
async def email_feedback_stats(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Aggregate stats on user email feedback — powers the classifier audit dashboard.

    Returns: total feedback, not-job-related count, top blocked domains,
    original classifications of false positives, and daily trend.
    """
    from sqlalchemy import func

    user_id = _require_user_id(auth)

    # All feedback for this user (join through EmailEvent for user scoping)
    base = (
        select(EmailFeedback, EmailEvent)
        .join(EmailEvent, EmailFeedback.email_id == EmailEvent.id)
        .where(EmailEvent.user_id == user_id)
    )
    result = await db.execute(base)
    rows = result.all()

    total = len(rows)
    not_job_count = 0
    domain_counts: dict[str, int] = {}
    original_classifications: dict[str, int] = {}
    daily_counts: dict[str, int] = {}

    for fb, ev in rows:
        if not fb.is_job_related:
            not_job_count += 1

            # Track blocked domains
            if fb.sender_domain:
                domain_counts[fb.sender_domain] = domain_counts.get(fb.sender_domain, 0) + 1

            # Track what the classifier originally called these
            # Before feedback, classification was set — but we just overwrote it to not_relevant.
            # Use the email's pipeline field as a proxy for original classifier decision,
            # or fall back to "unknown" since the classification was already overwritten.
            orig_cls = ev.pipeline or "unknown"
            original_classifications[orig_cls] = original_classifications.get(orig_cls, 0) + 1

        # Daily trend
        day = fb.created_at.strftime("%Y-%m-%d") if fb.created_at else "unknown"
        daily_counts[day] = daily_counts.get(day, 0) + 1

    # Sort domains by count desc, take top 20
    top_domains = sorted(domain_counts.items(), key=lambda x: -x[1])[:20]

    # Sort daily trend chronologically
    daily_trend = [{"date": d, "count": c} for d, c in sorted(daily_counts.items())]

    return {
        "total_feedback": total,
        "not_job_related": not_job_count,
        "job_related": total - not_job_count,
        "top_blocked_domains": [{"domain": d, "count": c} for d, c in top_domains],
        "original_classifications": original_classifications,
        "daily_trend": daily_trend,
    }


@app.get("/api/emails/{email_id}/pipeline-check")
async def check_email_pipeline(
    email_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Check if an email's sender company exists in the pipeline.

    Returns whether the company is tracked and suggests adding if not.
    """
    user_id = _require_user_id(auth)

    eid = _uuid.UUID(email_id)
    stmt = select(EmailEvent).where(
        EmailEvent.id == eid,
        EmailEvent.user_id == user_id,
    )
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Email not found")

    if event.application_id:
        return {"in_pipeline": True, "application_id": str(event.application_id)}

    # Check if company name matches any application
    company_name = event.company_name
    if company_name:
        from sqlalchemy import func
        app_stmt = select(Application).where(
            func.lower(Application.company).like(_contains_like(company_name), escape="\\"),
            Application.user_id == user_id,
        )
        app_result = await db.execute(app_stmt)
        matched_app = app_result.scalar_one_or_none()
        if matched_app:
            return {
                "in_pipeline": True,
                "application_id": str(matched_app.id),
                "company": matched_app.company,
            }

    return {
        "in_pipeline": False,
        "company_name": company_name,
        "sender_domain": event.sender_domain,
        "suggestion": f"I don't see {company_name or event.sender_domain} in your pipeline. Would you like to add it?",
    }


@app.get("/api/auth/gmail")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def gmail_auth_redirect(request: Request):
    raise HTTPException(
        status_code=410,
        detail="Legacy Gmail OAuth flow removed. Use /api/auth/google?connect_gmail=true instead.",
    )


@app.get("/api/auth/gmail/callback")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def gmail_auth_callback(
    request: Request,
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(
        status_code=410,
        detail="Legacy Gmail OAuth callback removed. Use /api/auth/google for account and service connections.",
    )


# --- Google Sign-In ---

GOOGLE_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")


def _google_oauth_scopes(connect_gmail: bool, connect_calendar: bool) -> list[str]:
    scopes = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]
    if connect_gmail:
        scopes.extend(
            [
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.compose",
            ]
        )
    if connect_calendar:
        scopes.append("https://www.googleapis.com/auth/calendar.readonly")
    return scopes


@app.get("/api/auth/google")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def google_auth_redirect(
    request: Request,
    connect_gmail: bool = Query(False),
    connect_calendar: bool = Query(False),
    redirect: bool = Query(False),
    frontend_origin: str | None = Query(None),
):
    """Redirect to Google OAuth for sign-in and optional Gmail/Calendar access."""
    from google_auth_oauthlib.flow import Flow
    from fastapi.responses import RedirectResponse

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI],
            }
        },
        scopes=_google_oauth_scopes(connect_gmail, connect_calendar),
        redirect_uri=GOOGLE_REDIRECT_URI,
    )

    # Generate auth URL first (this sets flow.code_verifier and returns the
    # OAuth state the callback must preserve for the exchange).
    auth_url, oauth_state = flow.authorization_url(
        **_google_authorization_kwargs(connect_gmail, connect_calendar)
    )

    resolved_frontend_origin = _resolve_frontend_origin(frontend_origin, request)
    oauth_context = {
        "connect_gmail": connect_gmail,
        "connect_calendar": connect_calendar,
        "code_verifier": flow.code_verifier,
        "frontend_origin": resolved_frontend_origin,
        "oauth_state": oauth_state,
    }
    encoded_state = _encode_oauth_context(oauth_context)

    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    parsed = urlparse(auth_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["state"] = [encoded_state]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    auth_url = urlunparse(parsed._replace(query=new_query))

    if redirect:
        return RedirectResponse(url=auth_url, status_code=302)

    return {"auth_url": auth_url}


@app.get("/api/auth/google/callback")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def google_auth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback. Creates/updates user and stores service scopes."""
    from google_auth_oauthlib.flow import Flow
    from fastapi.responses import RedirectResponse

    try:
        oauth_context = _decode_oauth_context(state)
        connect_gmail = bool(oauth_context.get("connect_gmail", False))
        connect_calendar = bool(oauth_context.get("connect_calendar", False))
        code_verifier = oauth_context.get("code_verifier")
        oauth_state = oauth_context.get("oauth_state")
        frontend_url = _resolve_frontend_origin(oauth_context.get("frontend_origin"), request)
    except Exception:
        connect_gmail = False
        connect_calendar = False
        code_verifier = None
        oauth_state = state
        frontend_url = _resolve_frontend_origin(None, request)
    authorization_response = _build_google_authorization_response(request, oauth_state)

    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [GOOGLE_REDIRECT_URI],
                }
            },
            scopes=_google_oauth_scopes(connect_gmail, connect_calendar),
            redirect_uri=GOOGLE_REDIRECT_URI,
            state=oauth_state,
        )
        flow.code_verifier = code_verifier
        flow.fetch_token(authorization_response=authorization_response)
    except Exception as e:
        import logging
        logging.exception("OAuth token exchange failed")
        return RedirectResponse(url=f"{frontend_url}/?auth_error=token_exchange_failed", status_code=302)
    credentials = flow.credentials

    # Get user info from Google
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests

    id_info = id_token.verify_oauth2_token(
        credentials.id_token,
        google_requests.Request(),
        GOOGLE_CLIENT_ID,
    )

    google_id = id_info["sub"]
    email = id_info.get("email", "")
    name = id_info.get("name", "")
    picture = id_info.get("picture", "")

    # Find or create user
    stmt = select(User).where(User.google_id == google_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        user.name = name
        user.picture = picture
        user.email = email
        user.updated_at = datetime.now(timezone.utc)
    else:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
        )
        db.add(user)
        await db.flush()

    if connect_gmail or connect_calendar:
        existing_token_stmt = select(GmailToken).where(GmailToken.user_id == user.id)
        existing_token_result = await db.execute(existing_token_stmt)
        existing_token = existing_token_result.scalar_one_or_none()

        refresh_token_value = credentials.refresh_token
        if not refresh_token_value and existing_token:
            refresh_token_value = decrypt_gmail_token(existing_token.refresh_token)

        if not refresh_token_value:
            return RedirectResponse(
                url=f"{frontend_url}/?auth_error=missing_refresh_token",
                status_code=302,
            )

        granted_scopes = set(credentials.granted_scopes or credentials.scopes or [])
        expires_at = datetime.fromtimestamp(
            credentials.expiry.timestamp(), tz=timezone.utc
        ) if credentials.expiry else datetime.now(timezone.utc)

        from backend.services.gmail_auth import store_tokens

        await store_tokens(
            db,
            access_token=credentials.token,
            refresh_token=refresh_token_value,
            expires_at=expires_at,
            user_id=user.id,
        )
        if connect_gmail and (
            not granted_scopes
            or "https://www.googleapis.com/auth/gmail.readonly" in granted_scopes
            or "https://www.googleapis.com/auth/gmail.compose" in granted_scopes
        ):
            user.gmail_connected = True
        if connect_calendar and (
            not granted_scopes
            or "https://www.googleapis.com/auth/calendar.readonly" in granted_scopes
        ):
            user.calendar_connected = True

    await db.commit()
    await db.refresh(user)

    # Create a one-time auth code that the frontend will exchange for tokens.
    # This avoids putting the JWT directly in the URL (browser history / logs).
    import json as _json

    auth_code = secrets.token_urlsafe(32)
    code_payload = _json.dumps({
        "user_id": str(user.id),
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
    })
    store_auth_code(auth_code, code_payload)

    from starlette.responses import RedirectResponse as _RedirectResponse
    redirect_url = _build_frontend_callback_url(frontend_url, auth_code)
    response = _RedirectResponse(url=redirect_url, status_code=302)
    return response


@app.get("/api/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return current user info for the active JWT session."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "gmail_connected": current_user.gmail_connected,
        "calendar_connected": current_user.calendar_connected,
        "data_consent_accepted_at": current_user.data_consent_accepted_at.isoformat() if current_user.data_consent_accepted_at else None,
    }


@app.post("/api/auth/refresh")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def refresh_access_token(request: Request, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token cookie for a new access token."""
    refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh:
        raise HTTPException(status_code=401, detail="No refresh token")

    payload = decode_refresh_token(refresh)
    user_id_str = payload["sub"]

    import uuid as _uuid
    stmt = select(User).where(User.id == _uuid.UUID(user_id_str))
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    new_access = create_jwt(str(user.id), user.email, user.name, user.picture)
    return {"access_token": new_access, "token_type": "bearer"}


class AuthCodeExchangeRequest(BaseModel):
    code: str


class LocalAuthRequest(BaseModel):
    email: EmailStr | None = None
    name: str | None = None


@app.post("/api/auth/exchange")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def exchange_auth_code(request: Request, body: AuthCodeExchangeRequest):
    """Exchange a one-time auth code (from OAuth callback) for access + refresh tokens."""
    payload_json = consume_auth_code(body.code)
    if not payload_json:
        raise HTTPException(status_code=400, detail="Invalid or expired auth code")

    payload = json.loads(payload_json)
    user_id = payload["user_id"]
    access_token = create_jwt(user_id, payload["email"], payload.get("name"), payload.get("picture"))
    refresh_token = create_refresh_token(user_id)

    response = JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
    })
    set_refresh_cookie(response, refresh_token)
    return response


@app.post("/api/auth/local-login")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def local_dev_login(
    request: Request,
    body: LocalAuthRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Create or reuse a dev-only local account and return JWT session tokens."""
    if not LOCAL_DEV_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Local development auth is disabled")

    email = (body.email if body else None) or os.getenv("LOCAL_DEV_AUTH_EMAIL", "me@apptrail.local")
    name = (body.name if body else None) or os.getenv("LOCAL_DEV_AUTH_NAME", "Local AppTrail User")
    google_id = f"local-dev:{email}"

    stmt = select(User).where(User.google_id == google_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user:
        user.email = email
        user.name = name
        user.updated_at = datetime.now(timezone.utc)
    else:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            picture="",
        )
        db.add(user)
        await db.flush()

    await db.commit()
    await db.refresh(user)

    access_token = create_jwt(str(user.id), user.email, user.name, user.picture)
    refresh_token = create_refresh_token(str(user.id))

    response = JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
        },
    })
    set_refresh_cookie(response, refresh_token)
    return response


@app.post("/api/auth/logout")
async def logout(request: Request, authorization: str = Header(default="")):
    """Revoke current tokens and clear refresh cookie."""
    from starlette.responses import JSONResponse

    # Blacklist current access token if present
    if authorization.startswith("Bearer "):
        token = authorization[7:]
        try:
            payload = decode_jwt(token)
            jti = payload.get("jti")
            if jti:
                blacklist_token(jti)
        except HTTPException:
            pass  # Already expired, fine

    # Blacklist refresh token if present
    refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh:
        try:
            payload = decode_refresh_token(refresh)
            jti = payload.get("jti")
            if jti:
                blacklist_token(jti)
        except HTTPException:
            pass

    response = JSONResponse({"status": "logged_out"})
    clear_refresh_cookie(response)
    return response


@app.get("/api/auth/api-key")
async def get_api_key_metadata(current_user: User = Depends(get_current_user)):
    """Return metadata for the current user's extension API key."""
    return {
        "has_api_key": bool(current_user.api_key_hash),
        "last4": current_user.api_key_last4,
        "created_at": current_user.api_key_created_at.isoformat() if current_user.api_key_created_at else None,
        "last_used_at": current_user.api_key_last_used_at.isoformat() if current_user.api_key_last_used_at else None,
    }


@app.post("/api/auth/api-key", status_code=201)
async def create_or_rotate_api_key(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a new per-user API key for extension auth and replace any existing key."""
    raw_key = generate_api_key()
    now = datetime.now(timezone.utc)

    current_user.api_key_hash = hash_api_key(raw_key)
    current_user.api_key_last4 = raw_key[-4:]
    current_user.api_key_created_at = now
    current_user.api_key_last_used_at = None
    current_user.updated_at = now

    await db.commit()
    await db.refresh(current_user)

    return {
        "api_key": raw_key,
        "last4": current_user.api_key_last4,
        "created_at": current_user.api_key_created_at.isoformat() if current_user.api_key_created_at else None,
    }


@app.post("/api/auth/api-key/validate")
@limiter.limit(_auth_rate_limit, error_message="Too many auth requests. Try again in a minute.")
async def validate_api_key(request: Request, auth: dict = Depends(verify_api_key), db: AsyncSession = Depends(get_db)):
    """Validate an extension API key and return the owning user metadata."""
    user_id = _require_user_id(auth)
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "status": "ok",
        "auth_type": auth["auth_type"],
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
        },
    }


# --- Gmail Sync ---

@app.post("/api/gmail/sync")
@limiter.limit(_gmail_sync_rate_limit, error_message="Too many Gmail sync requests. Try again in a minute.")
async def sync_gmail(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """On-demand Gmail sync. Fetches recent emails, classifies with Haiku LLM."""
    import uuid as _uuid
    import time
    from email.utils import parsedate_to_datetime
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from backend.services.email_parser import parse_email_body, extract_sender_parts
    from backend.services.email_classifier import (
        classify_email as classify_email_llm,
        CLASSIFICATION_TO_COLOR,
        CLASSIFICATION_TO_EMAIL_TYPE,
        is_likely_person_sender,
        should_create_network_contact,
    )
    from backend.services.company_identity import extract_domain, get_company_info
    from backend.services.email_filter import is_obvious_noise_email
    from backend.dependencies import check_ai_consent

    # Get Gmail credentials
    user_id = current_user.id
    user_email = current_user.email or ""
    stmt = select(GmailToken).where(GmailToken.user_id == user_id)
    result = await db.execute(stmt)
    gmail_token = result.scalar_one_or_none()
    if not gmail_token:
        raise HTTPException(status_code=400, detail="Gmail not connected. Please connect your Gmail account first.")

    access_token = decrypt_gmail_token(gmail_token.access_token)
    refresh_token = decrypt_gmail_token(gmail_token.refresh_token)
    if not is_gmail_token_encrypted(gmail_token.access_token) or not is_gmail_token_encrypted(gmail_token.refresh_token):
        gmail_token.access_token = encrypt_gmail_token(access_token)
        gmail_token.refresh_token = encrypt_gmail_token(refresh_token)
        gmail_token.updated_at = datetime.now(timezone.utc)
        await db.commit()

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )

    # Refresh if needed
    if gmail_token.expires_at.timestamp() - time.time() < 300:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        gmail_token.access_token = encrypt_gmail_token(creds.token)
        gmail_token.expires_at = datetime.fromtimestamp(
            creds.expiry.timestamp(), tz=timezone.utc
        ) if creds.expiry else gmail_token.expires_at
        gmail_token.updated_at = datetime.now(timezone.utc)
        await db.commit()

    service = build("gmail", "v1", credentials=creds)
    notifications_enabled = current_user.notifications_started_at is not None
    notification_pref = None
    if notifications_enabled:
        pref_stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        pref_result = await db.execute(pref_stmt)
        notification_pref = pref_result.scalar_one_or_none()

    ai_enabled = await check_ai_consent(user_id, db)
    from backend.dependencies import check_enrichment_consent
    enrichment_enabled = await check_enrichment_consent(user_id, db)

    # Get feedback blocklist
    feedback_stmt = (
        select(EmailFeedback.sender_domain)
        .join(EmailEvent, EmailFeedback.email_id == EmailEvent.id)
        .where(
            EmailEvent.user_id == user_id,
            EmailFeedback.is_job_related.is_(False),
            EmailFeedback.sender_domain.isnot(None),
        )
    )
    feedback_result = await db.execute(feedback_stmt)
    blocklist = {row[0] for row in feedback_result.all()}

    # Fetch last 30 days of emails — let classifier decide relevance
    messages_response = service.users().messages().list(
        userId="me", q="newer_than:30d", maxResults=50
    ).execute()

    messages = messages_response.get("messages", [])
    new_count = 0
    emails_synced = []

    app_match_stmt = (
        select(Application.id, Application.company, Company.domain)
        .join(Company, Application.company_id == Company.id, isouter=True)
        .where(Application.user_id == user_id)
    )
    app_match_result = await db.execute(app_match_stmt)
    app_domain_map, app_token_map = _build_application_match_maps(app_match_result.all())

    for msg_meta in messages:
        msg_id = msg_meta["id"]

        existing_stmt = select(EmailEvent).where(EmailEvent.gmail_message_id == msg_id)
        existing_result = await db.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            continue

        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

        headers_list = msg.get("payload", {}).get("headers", [])
        headers = {h["name"].lower(): h["value"] for h in headers_list}
        from_header = headers.get("from", "")
        subject = headers.get("subject", "")
        date_str = headers.get("date", "")

        sender_name, sender_email_addr = extract_sender_parts(from_header)
        sender_domain = extract_domain(sender_email_addr)

        # Skip blocked domains
        if sender_domain in blocklist:
            continue

        # Parse date
        received_at = datetime.now(timezone.utc)
        if date_str:
            try:
                received_at = parsedate_to_datetime(date_str)
                if received_at.tzinfo is None:
                    received_at = received_at.replace(tzinfo=timezone.utc)
            except Exception:
                pass

        # Parse body with improved MIME parser
        body_text = parse_email_body(msg.get("payload", {}))
        snippet = msg.get("snippet", "")

        is_from_user = sender_email_addr.lower() == user_email.lower() if user_email else False

        if is_obvious_noise_email({
            "sender": sender_email_addr,
            "sender_email": sender_email_addr,
            "sender_name": sender_name,
            "subject": subject,
            "body": body_text,
        }):
            continue

        # Classify with LLM (or fallback if AI consent not granted)
        classification = await classify_email_llm(
            subject=subject,
            body=body_text,
            sender=sender_name,
            sender_email=sender_email_addr,
            ai_enabled=ai_enabled,
        )

        cls = classification.get("classification", "job_update")

        # Skip not_relevant
        if cls == "not_relevant":
            continue

        # Company identity
        company_info = get_company_info(sender_email_addr, include_logo=enrichment_enabled)
        email_company_name = classification.get("company_name") or company_info.get("company_name")

        # Match to application
        app_id = _match_application_id_for_sender(sender_email_addr, app_domain_map, app_token_map)
        contact_id = None
        if sender_email_addr:
            contact_stmt = select(Contact).where(
                Contact.user_id == user_id,
                Contact.email == sender_email_addr,
            ).limit(1)
            contact_result = await db.execute(contact_stmt)
            matched_contact = contact_result.scalar_one_or_none()
            if matched_contact:
                contact_id = matched_contact.id
                if matched_contact.application_id and not app_id:
                    app_id = matched_contact.application_id

        should_alert_network_contact = False
        if (
            sender_email_addr
            and CLASSIFICATION_TO_EMAIL_TYPE.get(cls) == "conversation"
            and should_create_network_contact(sender_name, sender_email_addr, cls)
            and not contact_id
        ):
            prior_sender_stmt = select(EmailEvent.id).where(
                EmailEvent.user_id == user_id,
                EmailEvent.sender_email == sender_email_addr,
            ).limit(1)
            prior_sender_result = await db.execute(prior_sender_stmt)
            should_alert_network_contact = prior_sender_result.scalar_one_or_none() is None

        email_event = EmailEvent(
            user_id=user_id,
            application_id=app_id,
            contact_id=contact_id,
            gmail_message_id=msg_id,
            thread_id=msg.get("threadId", ""),
            sender=sender_name,
            sender_email=sender_email_addr,
            subject=subject,
            body=body_text[:10000] if body_text else None,
            snippet=snippet,
            received_at=received_at,
            classification=cls,
            color_code=CLASSIFICATION_TO_COLOR.get(cls, "gray"),
            email_type=CLASSIFICATION_TO_EMAIL_TYPE.get(cls),
            action_needed=classification.get("action_needed", False),
            key_sentence=classification.get("key_sentence"),
            summary=classification.get("summary"),
            is_from_user=is_from_user,
            is_human=is_likely_person_sender(sender_name, sender_email_addr) and not classification.get("is_automated", False),
            read=is_from_user,
            company_name=email_company_name,
            company_logo_url=company_info.get("logo_url"),
            sender_domain=sender_domain,
            confidence=classification.get("confidence"),
        )
        db.add(email_event)
        await db.flush()

        action_path = "/conversations" if email_event.email_type == "conversation" else "/emails"
        action_tab = "conversations" if email_event.email_type == "conversation" else "emails"
        if notifications_enabled:
            await create_user_alert(
                db,
                user_id=user_id,
                alert_type=_email_alert_type(email_event.email_type, cls),
                title=f"{sender_name or sender_email_addr or 'New update'}: {subject or '(no subject)'}",
                body=(classification.get("summary") or snippet or body_text[:160] if body_text else snippet),
                action_url=_alert_action_url(
                    action_path,
                    tab=action_tab,
                    email_id=str(email_event.id),
                    thread_id=email_event.thread_id or None,
                ),
                notification_pref=notification_pref,
            )

            if should_alert_network_contact:
                await create_user_alert(
                    db,
                    user_id=user_id,
                    alert_type="network_contact",
                    title=f"Added {sender_name or sender_email_addr} to your network",
                    body="Open their card to review contact details from this conversation.",
                    action_url=_alert_action_url("/network", email=sender_email_addr),
                    notification_pref=notification_pref,
                )

        new_count += 1
        emails_synced.append({
            "subject": subject,
            "sender": sender_name,
            "classification": cls,
            "company": email_company_name,
        })

    if current_user.notifications_started_at is None:
        current_user.notifications_started_at = datetime.now(timezone.utc)

    if new_count > 0 or current_user.notifications_started_at is not None:
        await db.commit()

    return {
        "status": "ok",
        "new_emails": new_count,
        "total_found": len(messages),
        "emails": emails_synced[:10],
    }


@app.post("/api/calendar/sync")
@limiter.limit(_calendar_sync_rate_limit, error_message="Too many Calendar sync requests. Try again in a minute.")
async def sync_calendar(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync interview-like Google Calendar events into Interview records."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    from backend.services.calendar_sync import sync_calendar_events
    from backend.services.gmail_auth import get_valid_token

    if not current_user.calendar_connected:
        raise HTTPException(
            status_code=400,
            detail="Google Calendar not connected. Please connect your Google Calendar first.",
        )

    try:
        creds = await get_valid_token(db, user_id=current_user.id)
        calendar_service = build("calendar", "v3", credentials=creds)
        result = await sync_calendar_events(
            db,
            calendar_service,
            user_id=current_user.id,
            user_email=current_user.email,
        )
        if current_user.notifications_started_at is not None:
            pref_stmt = select(NotificationPreference).where(NotificationPreference.user_id == current_user.id)
            pref_result = await db.execute(pref_stmt)
            notification_pref = pref_result.scalar_one_or_none()
            for item in result.get("synced", []):
                if item.get("status") not in {"created", "updated"}:
                    continue
                status_label = "added to your calendar" if item.get("status") == "created" else "updated on your calendar"
                await create_user_alert(
                    db,
                    user_id=current_user.id,
                    alert_type="interview_request",
                    title=f"Interview {status_label}",
                    body=item.get("summary") or "Open your calendar to review the interview details.",
                    action_url=_alert_action_url(
                        "/calendar",
                        interview_id=item.get("interview_id"),
                    ),
                    notification_pref=notification_pref,
                )
        if result.get("synced") and current_user.notifications_started_at is not None:
            await db.commit()
        return {
            "status": "ok",
            **result,
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HttpError as exc:
        if getattr(exc, "status_code", None) == 403 or getattr(getattr(exc, "resp", None), "status", None) == 403:
            error_text = ""
            try:
                content = getattr(exc, "content", b"")
                if isinstance(content, bytes):
                    error_text = content.decode("utf-8", errors="ignore")
                else:
                    error_text = str(content)
            except Exception:
                error_text = str(exc)

            lowered = error_text.lower()
            if (
                "insufficient authentication scopes" in lowered
                or "insufficientpermissions" in lowered
                or "access_token_scope_insufficient" in lowered
            ):
                current_user.calendar_connected = False
                current_user.updated_at = datetime.now(timezone.utc)
                await db.commit()
                raise HTTPException(
                    status_code=400,
                    detail="Google Calendar access is missing. Reconnect your Google account with Calendar access.",
                ) from exc
            if (
                "accessnotconfigured" in lowered
                or "service_disabled" in lowered
                or "google calendar api has not been used" in lowered
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Google Calendar API is not enabled for this Google Cloud project. Enable the Calendar API, then try again.",
                ) from exc
            raise HTTPException(
                status_code=400,
                detail="Google Calendar access failed. Check the Calendar API configuration in Google Cloud and try again.",
            ) from exc
        raise HTTPException(status_code=502, detail="Google Calendar sync failed.") from exc


@app.get("/api/search")
@limiter.limit(_search_rate_limit, error_message="Too many search requests. Try again in a minute.")
async def search_jobs_endpoint(
    request: Request,
    q: str = Query(""),
    location: str = Query(""),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    from datetime import timedelta

    from backend.models import JobListing
    from backend.dependencies import check_enrichment_consent
    from backend.services.job_search import search_jobs

    user_id = _require_user_id(auth)
    include_logo = await check_enrichment_consent(user_id, db)

    # Check cache: listings saved within 24h matching this query
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cache_source = f"search:{q}:{location}"
    stmt = select(JobListing).where(
        JobListing.source == cache_source,
        JobListing.saved_at > cutoff,
    )
    result = await db.execute(stmt)
    cached = result.scalars().all()

    if cached:
        serialized_cached = []
        for c in cached:
            serialized_cached.append({
                "id": str(c.id),
                "title": c.title,
                "company": c.company,
                "source": "cached",
                "url": c.url,
                "posted_at": c.posted_at.isoformat() if c.posted_at else None,
                "description": c.description_snippet,
                "logo_url": await _resolve_search_logo_url(db, c.company, c.url, include_logo),
            })
        return {
            "results": serialized_cached,
            "cached": True,
        }

    # Fresh search
    results = await search_jobs(q, location)

    # Cache results
    for r in results:
        listing = JobListing(
            title=r.get("title"),
            company=r.get("company"),
            source=cache_source,
            url=r.get("url"),
            description_snippet=r.get("description"),
        )
        db.add(listing)

    if results:
        await db.commit()

    serialized_results = []
    for r in results:
        serialized_results.append({
            **r,
            "description": r.get("description"),
            "logo_url": await _resolve_search_logo_url(db, r.get("company"), r.get("url"), include_logo),
        })

    return {"results": serialized_results, "cached": False}


@app.get("/api/search/global")
@limiter.limit(_global_search_rate_limit, error_message="Too many global search requests. Try again in a minute.")
async def global_search(
    request: Request,
    q: str = Query(""),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    if not q or len(q) < 2:
        return {"applications": [], "contacts": [], "emails": []}

    search_term = _contains_like(q)

    from sqlalchemy import or_, func

    # Search applications
    app_stmt = select(Application).where(
        Application.user_id == user_id,
        or_(
            func.lower(Application.company).like(search_term, escape="\\"),
            func.lower(Application.role_title).like(search_term, escape="\\"),
        )
    ).limit(20)
    app_result = await db.execute(app_stmt)
    apps = [_serialize_app(a) for a in app_result.scalars().all()]

    # Search contacts
    contact_stmt = select(Contact).where(
        Contact.user_id == user_id,
        or_(
            func.lower(Contact.name).like(search_term, escape="\\"),
            func.lower(Contact.email).like(search_term, escape="\\"),
        )
    ).limit(20)
    contact_result = await db.execute(contact_stmt)
    contacts = [_serialize_contact(c) for c in contact_result.scalars().all()]

    # Search emails
    from sqlalchemy.orm import selectinload
    email_stmt = select(EmailEvent).options(
        selectinload(EmailEvent.application)
    ).where(
        EmailEvent.user_id == user_id,
        func.lower(EmailEvent.summary).like(search_term, escape="\\")
    ).limit(20)
    email_result = await db.execute(email_stmt)
    emails = [_serialize_email_event(e) for e in email_result.scalars().all()]

    return {"applications": apps, "contacts": contacts, "emails": emails}


# --- Sprint 2: Company Endpoints ---

@app.get("/api/companies")
async def list_companies(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    from sqlalchemy import func
    user_id = _require_user_id(auth)

    stmt = select(
        Company,
        func.count(Application.id.distinct()).label("job_count"),
    ).join(
        Application,
        (Application.company_id == Company.id) & (Application.user_id == user_id),
    ).group_by(Company.id).order_by(Company.name)
    stmt = _paginate(stmt, limit, offset)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": str(c.id),
            "domain": c.domain,
            "name": c.name,
            "logo_url": c.logo_url,
            "industry": c.industry,
            "size": c.size,
            "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
            "last_activity_at": c.last_activity_at.isoformat() if c.last_activity_at else None,
            "job_count": job_count,
        }
        for c, job_count in rows
    ]


@app.get("/api/companies/{domain}")
async def get_company(domain: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)

    stmt = (
        select(Company)
        .join(Application, Application.company_id == Company.id)
        .where(Company.domain == domain, Application.user_id == user_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Get related jobs
    jobs_stmt = select(Application).where(
        Application.company_id == company.id,
        Application.user_id == user_id,
    ).order_by(Application.applied_at.desc()).limit(20)
    jobs_result = await db.execute(jobs_stmt)
    jobs = [_serialize_app(a) for a in jobs_result.scalars().all()]

    # Get related contacts
    contacts_stmt = select(Contact).where(
        Contact.company_id == company.id,
        Contact.user_id == user_id,
    ).limit(20)
    contacts_result = await db.execute(contacts_stmt)
    contacts = [_serialize_contact(c) for c in contacts_result.scalars().all()]

    # Get recent emails
    from sqlalchemy.orm import selectinload as _sel
    emails_stmt = select(EmailEvent).options(_sel(EmailEvent.application)).where(
        EmailEvent.company_id == company.id,
        EmailEvent.user_id == user_id,
    ).order_by(EmailEvent.received_at.desc()).limit(10)
    emails_result = await db.execute(emails_stmt)
    emails = [_serialize_email_event(e) for e in emails_result.scalars().all()]

    return {
        "id": str(company.id),
        "domain": company.domain,
        "name": company.name,
        "logo_url": company.logo_url,
        "industry": company.industry,
        "size": company.size,
        "first_seen_at": company.first_seen_at.isoformat() if company.first_seen_at else None,
        "last_activity_at": company.last_activity_at.isoformat() if company.last_activity_at else None,
        "jobs": jobs,
        "contacts": contacts,
        "emails": emails,
    }


# --- Sprint 3: Umbrella Endpoints ---

@app.get("/api/umbrellas", dependencies=[Depends(verify_api_key)])
async def list_umbrellas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RoleUmbrella).order_by(RoleUmbrella.name))
    return [
        {"id": str(u.id), "name": u.name, "aliases": u.aliases}
        for u in result.scalars().all()
    ]


# --- Sprint 4: Company Tech Endpoint ---

@app.get("/api/companies/{domain}/tech", dependencies=[Depends(verify_api_key)])
async def get_company_tech(domain: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Company).where(Company.domain == domain)
    result = await db.execute(stmt)
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    tech_stmt = select(CompanyTechProfile).where(
        CompanyTechProfile.company_id == company.id
    ).order_by(CompanyTechProfile.mention_count.desc())
    tech_result = await db.execute(tech_stmt)
    profiles = tech_result.scalars().all()

    return {
        "company": company.name,
        "domain": company.domain,
        "tech_stack": [
            {
                "name": p.tech_name,
                "category": p.category,
                "mentions": p.mention_count,
            }
            for p in profiles
        ],
    }


# --- Sprint 5: Resume Intelligence ---

class ResumeTextUpload(BaseModel):
    text: str = Field(..., max_length=MAX_RESUME_TEXT_LEN)


class ProfileUpdatePayload(BaseModel):
    linkedin_url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    skills: Optional[list[str]] = None
    education: Optional[list] = None
    experience_years: Optional[int] = None
    tools: Optional[list[str]] = None
    certifications: Optional[list[str]] = None
    resume_text: Optional[str] = Field(None, max_length=MAX_RESUME_TEXT_LEN)


@app.post("/api/resume/parse", status_code=201)
async def parse_resume_text(
    payload: ResumeTextUpload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Parse resume text into structured profile."""
    user_id = _require_user_id(auth)
    from backend.services.resume_parser import parse_resume
    from backend.dependencies import check_ai_consent
    ai_on = await check_ai_consent(user_id, db)

    parsed = await parse_resume(payload.text, ai_enabled=ai_on)

    # Upsert profile scoped by user_id
    stmt = select(UserProfile).where(UserProfile.user_id == user_id).limit(1)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if profile:
        profile.raw_text = payload.text[:50000]
        profile.skills = parsed.get("skills")
        profile.education = parsed.get("education")
        profile.experience_years = parsed.get("experience_years")
        profile.tools = parsed.get("tools")
        profile.certifications = parsed.get("certifications")
        profile.updated_at = datetime.now(timezone.utc)
    else:
        profile = UserProfile(
            raw_text=payload.text[:50000],
            skills=parsed.get("skills"),
            education=parsed.get("education"),
            experience_years=parsed.get("experience_years"),
            tools=parsed.get("tools"),
            certifications=parsed.get("certifications"),
            user_id=user_id,
        )
        db.add(profile)

    await db.commit()
    await db.refresh(profile)

    return {
        "id": str(profile.id),
        "linkedin_url": profile.linkedin_url,
        "skills": profile.skills or [],
        "education": profile.education or [],
        "experience_years": profile.experience_years,
        "tools": profile.tools or [],
        "certifications": profile.certifications or [],
        "resume_text": profile.raw_text,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@app.get("/api/profile")
async def get_profile(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Get current user profile."""
    user_id = _require_user_id(auth)
    stmt = select(UserProfile).where(UserProfile.user_id == user_id).limit(1)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        return None
    return {
        "id": str(profile.id),
        "linkedin_url": profile.linkedin_url,
        "skills": profile.skills or [],
        "education": profile.education or [],
        "experience_years": profile.experience_years,
        "tools": profile.tools or [],
        "certifications": profile.certifications or [],
        "resume_text": profile.raw_text,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@app.patch("/api/profile")
async def update_profile(
    payload: ProfileUpdatePayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create or update the current user's structured profile."""
    user_id = _require_user_id(auth)
    stmt = select(UserProfile).where(UserProfile.user_id == user_id).limit(1)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)

    if payload.linkedin_url is not None:
        profile.linkedin_url = payload.linkedin_url or None
    if payload.skills is not None:
        profile.skills = [item for item in payload.skills if item]
    if payload.education is not None:
        profile.education = [item for item in payload.education if item]
    if payload.experience_years is not None:
        profile.experience_years = payload.experience_years
    if payload.tools is not None:
        profile.tools = [item for item in payload.tools if item]
    if payload.certifications is not None:
        profile.certifications = [item for item in payload.certifications if item]
    if payload.resume_text is not None:
        profile.raw_text = payload.resume_text or None

    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile)

    return {
        "id": str(profile.id),
        "linkedin_url": profile.linkedin_url,
        "skills": profile.skills or [],
        "education": profile.education or [],
        "experience_years": profile.experience_years,
        "tools": profile.tools or [],
        "certifications": profile.certifications or [],
        "resume_text": profile.raw_text,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


@app.delete("/api/profile")
async def clear_profile(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Delete the current user's saved profile fields."""
    user_id = _require_user_id(auth)
    stmt = select(UserProfile).where(UserProfile.user_id == user_id).limit(1)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile:
        await db.delete(profile)
        await db.commit()
    return {"status": "ok"}


@app.get("/api/jobs/{job_id}/match")
async def get_job_match(job_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Get match score for a job against user profile."""
    import uuid as _uuid
    from backend.services.match_scorer import score_match

    user_id = _require_user_id(auth)
    jid = _uuid.UUID(job_id)
    stmt = select(Application).where(
        Application.id == jid,
        Application.user_id == user_id,
    )
    result = await db.execute(stmt)
    app_row = result.scalar_one_or_none()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get user profile
    profile_stmt = select(UserProfile).where(UserProfile.user_id == user_id).limit(1)
    profile_result = await db.execute(profile_stmt)
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="No resume profile found. Upload your resume first.")

    profile_dict = {
        "skills": profile.skills or [],
        "tools": profile.tools or [],
        "experience_years": profile.experience_years,
    }
    job_tech = app_row.tech_stack or []
    match = score_match(profile_dict, job_tech, app_row.description_text or "")

    # Cache the score on the application
    app_row.match_score = match["score"]
    await db.commit()

    return match


@app.post("/api/search/match-preview")
async def get_search_match_preview(
    payload: SearchMatchPreviewPayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    profile_stmt = select(UserProfile).where(UserProfile.user_id == user_id).limit(1)
    profile_result = await db.execute(profile_stmt)
    profile = profile_result.scalar_one_or_none()

    user_stmt = select(User).where(User.id == user_id).limit(1)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not profile:
        return {
            "profile_available": False,
            "jobs": [
                {
                    "id": job.id,
                    "url": job.url,
                    "score": None,
                    "fit_label": None,
                    "matched_skills": [],
                    "missing_skills": [],
                    "transferable_skills": [],
                    "preference_signals": [],
                }
                for job in payload.jobs
            ],
        }

    return {
        "profile_available": True,
        "jobs": [
            {
                "id": job.id,
                "url": job.url,
                **_score_search_preview(profile, user, job),
            }
            for job in payload.jobs
        ],
    }


# --- Sprint 6: Onboarding / Preferences ---

class PreferencesPayload(BaseModel):
    preferred_locations: Optional[list] = None
    preferred_remote_type: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    target_salary_min: Optional[int] = None
    target_salary_max: Optional[int] = None
    role_interest_ids: Optional[list] = None
    onboarding_complete: Optional[bool] = None


@app.post("/api/profile/preferences")
async def save_preferences(
    payload: PreferencesPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save user onboarding preferences."""
    import uuid as _uuid

    user = current_user
    fields = payload.model_fields_set

    if "preferred_locations" in fields:
        user.preferred_locations = payload.preferred_locations
    if "preferred_remote_type" in fields:
        user.preferred_remote_type = payload.preferred_remote_type
    if "target_salary_min" in fields:
        user.target_salary_min = payload.target_salary_min
    if "target_salary_max" in fields:
        user.target_salary_max = payload.target_salary_max
    if "onboarding_complete" in fields:
        user.onboarding_complete = payload.onboarding_complete

    # Handle role interests
    if "role_interest_ids" in fields:
        # Clear existing
        from sqlalchemy import delete
        await db.execute(delete(UserRoleInterest).where(UserRoleInterest.user_id == user.id))
        # Add new
        for uid in payload.role_interest_ids or []:
            db.add(UserRoleInterest(user_id=user.id, umbrella_id=_uuid.UUID(uid)))

    await db.commit()
    await db.refresh(user)

    return {
        "preferred_locations": user.preferred_locations,
        "preferred_remote_type": user.preferred_remote_type,
        "target_salary_min": user.target_salary_min,
        "target_salary_max": user.target_salary_max,
        "onboarding_complete": user.onboarding_complete,
    }


@app.get("/api/profile/preferences")
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user preferences."""
    from sqlalchemy.orm import selectinload

    stmt = select(User).options(selectinload(User.role_interests)).where(User.id == current_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "preferred_locations": user.preferred_locations,
        "preferred_remote_type": user.preferred_remote_type,
        "target_salary_min": user.target_salary_min,
        "target_salary_max": user.target_salary_max,
        "onboarding_complete": user.onboarding_complete,
        "role_interest_ids": [str(ri.umbrella_id) for ri in user.role_interests],
    }


# --- Sprint 8: ATS Intelligence ---

@app.get("/api/intelligence/ats/{platform}", dependencies=[Depends(verify_api_key)])
async def get_ats_intelligence(platform: str, db: AsyncSession = Depends(get_db)):
    """Get behavioral profile for an ATS platform."""
    from backend.services.ats_intelligence import get_platform_profile
    return await get_platform_profile(db, platform)


@app.post("/api/intelligence/ats/compute", dependencies=[Depends(verify_api_key)])
async def compute_ats_intelligence(db: AsyncSession = Depends(get_db)):
    """Trigger ATS metrics computation."""
    from backend.services.ats_intelligence import compute_ats_metrics
    metrics = await compute_ats_metrics(db)
    return {"status": "ok", "metrics": metrics}


# --- Sprint 9: Warm Paths ---

@app.get("/api/jobs/{job_id}/warm-paths")
async def get_warm_paths(job_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Get warm connections for a job's company."""
    import uuid as _uuid
    from backend.services.warm_path import discover_warm_paths

    user_id = _require_user_id(auth)
    jid = _uuid.UUID(job_id)
    stmt = select(Application).where(
        Application.id == jid,
        Application.user_id == user_id,
    )
    result = await db.execute(stmt)
    app_row = result.scalar_one_or_none()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")

    # Get company domain from job URL or company_ref
    domain = None
    if app_row.company_id:
        company_stmt = select(Company).where(Company.id == app_row.company_id)
        company_result = await db.execute(company_stmt)
        company = company_result.scalar_one_or_none()
        if company:
            domain = company.domain
    if not domain and app_row.job_url:
        from urllib.parse import urlparse
        parsed = urlparse(app_row.job_url)
        domain = parsed.netloc.lower().replace("www.", "")

    if not domain:
        return {"warm_connections": [], "company": app_row.company}

    connections = await discover_warm_paths(db, domain, user_id=user_id)
    return {
        "warm_connections": connections,
        "company": app_row.company,
        "domain": domain,
    }


# --- Sprint 10: Network ---

@app.get("/api/network")
async def list_network(
    q: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Unified network view: all contacts + unique email senders."""
    from sqlalchemy import or_, func
    from sqlalchemy.orm import selectinload
    from backend.services.email_classifier import should_create_network_contact
    from backend.services.contact_enrichment import build_inferred_contact_from_email_event

    user_id = _require_user_id(auth)
    contacts_list = []
    ignored_result = await db.execute(
        select(IgnoredNetworkContact.email).where(IgnoredNetworkContact.user_id == user_id)
    )
    ignored_emails = {row[0].lower() for row in ignored_result.all()}

    # Get contacts from Contact table
    contact_stmt = select(Contact).options(selectinload(Contact.application)).where(Contact.user_id == user_id)
    if q:
        search = _contains_like(q)
        contact_stmt = contact_stmt.where(
            or_(
                func.lower(Contact.name).like(search, escape="\\"),
                func.lower(Contact.email).like(search, escape="\\"),
            )
        )
    if source:
        contact_stmt = contact_stmt.where(Contact.source == source)
    contact_stmt = contact_stmt.order_by(Contact.id).offset(offset).limit(limit)
    contact_result = await db.execute(contact_stmt)
    contacts = contact_result.scalars().all()

    seen_emails: set[str] = set()
    for c in contacts:
        email = (c.email or "").lower()
        if email and email in ignored_emails:
            continue
        if email in seen_emails:
            continue
        seen_emails.add(email)
        contacts_list.append({
            "id": str(c.id),
            "name": c.name,
            "email": c.email,
            "title": c.title,
            "phone_number": c.phone_number,
            "company": c.company_name or (c.application.company if c.application else None),
            "company_id": str(c.company_id) if c.company_id else None,
            "source": c.source or "hunter",
            "reached_out": c.reached_out,
            "response_received": c.response_received,
            "linkedin_url": c.linkedin_url,
        })

    # Add unique email senders not already in contacts
    email_stmt = select(EmailEvent).where(
        EmailEvent.user_id == user_id,
        EmailEvent.sender_email.isnot(None),
        EmailEvent.is_from_user.is_(False),
        EmailEvent.hidden.is_(False),
        EmailEvent.is_human.is_(True),
        EmailEvent.email_type == "conversation",
    ).order_by(EmailEvent.received_at.desc())
    email_result = await db.execute(email_stmt)
    sender_aggregate: dict[str, dict] = {}
    for email_event in email_result.scalars():
        email_addr = (email_event.sender_email or "").lower()
        if not email_addr:
            continue
        aggregate = sender_aggregate.setdefault(
            email_addr,
            {
                "event": email_event,
                "email_count": 0,
                "last_interaction": email_event.received_at,
            },
        )
        aggregate["email_count"] += 1
        if aggregate["last_interaction"] is None or (
            email_event.received_at and email_event.received_at > aggregate["last_interaction"]
        ):
            aggregate["last_interaction"] = email_event.received_at
            aggregate["event"] = email_event

    derived_contacts = sorted(
        sender_aggregate.items(),
        key=lambda item: item[1]["last_interaction"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    for email_addr, aggregate in derived_contacts[offset : offset + limit]:
        if email_addr in ignored_emails:
            continue
        if email_addr in seen_emails:
            continue
        event = aggregate["event"]
        if not should_create_network_contact(event.sender or "", email_addr):
            continue
        seen_emails.add(email_addr)
        inferred = build_inferred_contact_from_email_event(event)
        display_name = inferred["name"] or event.sender
        haystack = " ".join(filter(None, [email_addr, display_name, inferred["title"], inferred["company"]])).lower()
        if q and q.lower() not in haystack:
            continue
        contacts_list.append({
            "id": f"email-{email_addr}",
            "name": display_name,
            "email": email_addr,
            "title": inferred["title"],
            "phone_number": None,
            "company": inferred["company"],
            "company_id": None,
            "source": "email",
            "reached_out": False,
            "response_received": False,
            "linkedin_url": inferred["linkedin_url"],
            "email_count": aggregate["email_count"],
            "last_interaction_at": aggregate["last_interaction"].isoformat() if aggregate["last_interaction"] else None,
        })

    return contacts_list[:limit]


@app.get("/api/network/{email}")
async def get_network_contact(email: EmailStr, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Full contact profile: emails, linked applications, company info."""
    from sqlalchemy.orm import selectinload
    from backend.services.contact_enrichment import build_inferred_contact

    user_id = _require_user_id(auth)
    email_value = str(email)
    # Get contact record
    contact_stmt = select(Contact).options(selectinload(Contact.application)).where(
        Contact.email == email_value,
        Contact.user_id == user_id,
    ).limit(1)
    contact_result = await db.execute(contact_stmt)
    contact = contact_result.scalar_one_or_none()

    # Get all emails from/to this person
    email_stmt = select(EmailEvent).options(
        selectinload(EmailEvent.application)
    ).where(
        EmailEvent.user_id == user_id,
        EmailEvent.sender_email == email_value,
    ).order_by(EmailEvent.received_at.desc()).limit(50)
    email_result = await db.execute(email_stmt)
    email_events = email_result.scalars().all()
    emails = [_serialize_email_event(e) for e in email_events]

    # Get linked applications
    linked_apps = []
    if contact:
        app_stmt = select(Application).where(
            Application.id == contact.application_id,
            Application.user_id == user_id,
        )
        app_result = await db.execute(app_stmt)
        app = app_result.scalar_one_or_none()
        if app:
            linked_apps.append(_serialize_app(app))

    inferred_contact = build_inferred_contact(
        sender_name=emails[0]["sender"] if emails else None,
        sender_email=email_value,
        explicit_company=(contact.company_name if contact else None)
        or (contact.application.company if contact and getattr(contact, "application", None) else None)
        or (emails[0].get("company_name") if emails else None),
        texts=[
            *(email.get("summary") for email in emails),
            *(email.get("key_sentence") for email in emails),
            *(email.get("body") for email in emails),
            *(email.get("snippet") for email in emails),
            *(email.get("subject") for email in emails),
        ],
    )

    contact_payload = _serialize_contact(contact) if contact else {"email": email_value}
    if inferred_contact["name"] and not contact_payload.get("name"):
        contact_payload["name"] = inferred_contact["name"]
    if inferred_contact["title"] and not contact_payload.get("title"):
        contact_payload["title"] = inferred_contact["title"]
    if inferred_contact["linkedin_url"] and not contact_payload.get("linkedin_url"):
        contact_payload["linkedin_url"] = inferred_contact["linkedin_url"]
    if inferred_contact["company"] and not contact_payload.get("company"):
        contact_payload["company"] = inferred_contact["company"]

    return {
        "contact": contact_payload,
        "emails": emails,
        "applications": linked_apps,
    }


@app.delete("/api/network/{email}")
async def delete_network_contact(email: EmailStr, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    email_value = str(email).lower()

    contacts_result = await db.execute(
        select(Contact).where(
            Contact.user_id == user_id,
            Contact.email == email_value,
        )
    )
    contacts = contacts_result.scalars().all()
    deleted_contacts = 0
    for contact in contacts:
        await db.delete(contact)
        deleted_contacts += 1

    ignored_result = await db.execute(
        select(IgnoredNetworkContact).where(
            IgnoredNetworkContact.user_id == user_id,
            IgnoredNetworkContact.email == email_value,
        )
    )
    ignored_contact = ignored_result.scalar_one_or_none()
    if not ignored_contact:
        db.add(IgnoredNetworkContact(user_id=user_id, email=email_value))

    await db.commit()
    return {"status": "ok", "deleted_contacts": deleted_contacts, "email": email_value}


# --- Sprint 11: Alerts ---

@app.get("/api/alerts")
async def list_alerts(
    unread: Optional[bool] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List alerts, optionally filtered to unread."""
    user_id = _require_user_id(auth)
    stmt = select(Alert).where(Alert.user_id == user_id).order_by(Alert.created_at.desc())
    if unread:
        stmt = stmt.where(Alert.read.is_(False))
    stmt = _paginate(stmt, limit, offset)
    result = await db.execute(stmt)
    alerts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "alert_type": a.alert_type,
            "title": a.title,
            "body": a.body,
            "action_url": a.action_url,
            "read": a.read,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@app.patch("/api/alerts/read-all")
async def mark_all_alerts_read(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Mark all alerts as read for the current user."""
    user_id = _require_user_id(auth)
    stmt = select(Alert).where(
        Alert.user_id == user_id,
        Alert.read.is_(False),
    )
    result = await db.execute(stmt)
    alerts = result.scalars().all()
    for alert in alerts:
        alert.read = True
    if alerts:
        await db.commit()
    return {"status": "ok", "updated": len(alerts)}


@app.patch("/api/alerts/{alert_id}")
async def update_alert(alert_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Mark an alert as read."""
    user_id = _require_user_id(auth)
    aid = _uuid.UUID(alert_id)
    stmt = select(Alert).where(
        Alert.id == aid,
        Alert.user_id == user_id,
    )
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.read = True
    await db.commit()
    return {"status": "ok"}


@app.get("/api/alerts/count")
async def alert_count(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Get unread alert count."""
    user_id = _require_user_id(auth)
    from sqlalchemy import func
    stmt = select(func.count(Alert.id)).where(
        Alert.read.is_(False),
        Alert.user_id == user_id,
    )
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return {"unread": count}


# --- Sprint 12: Send Email ---

class SendEmailPayload(BaseModel):
    to: EmailStr
    cc: list[EmailStr] = Field(default_factory=list)
    subject: str = Field(..., max_length=MAX_NAME_LEN)
    body: str = Field(..., max_length=MAX_LONG_TEXT_LEN)
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    reply_to_email_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    reply_to_message_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    thread_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)


def _is_gmail_scope_error(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return "insufficient authentication scopes" in lowered or "access token scope insufficient" in lowered


async def _build_gmail_service_for_user(
    db: AsyncSession,
    user_id: _uuid.UUID,
):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    stmt = select(GmailToken).where(GmailToken.user_id == user_id)
    result = await db.execute(stmt)
    gmail_token = result.scalar_one_or_none()
    if not gmail_token:
        raise HTTPException(status_code=400, detail="Gmail not connected.")

    access_token = decrypt_gmail_token(gmail_token.access_token)
    refresh_token = decrypt_gmail_token(gmail_token.refresh_token)
    if not is_gmail_token_encrypted(gmail_token.access_token) or not is_gmail_token_encrypted(gmail_token.refresh_token):
        gmail_token.access_token = encrypt_gmail_token(access_token)
        gmail_token.refresh_token = encrypt_gmail_token(refresh_token)
        gmail_token.updated_at = datetime.now(timezone.utc)
        await db.commit()

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GMAIL_CLIENT_ID", ""),
        client_secret=os.getenv("GMAIL_CLIENT_SECRET", ""),
    )
    return build("gmail", "v1", credentials=creds)


@app.get("/api/emails/{email_id}/reply-context")
async def get_email_reply_context(
    email_id: str,
    reply_all: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.services.email_sender import build_reply_context

    user_id = current_user.id
    stmt = select(EmailEvent).where(
        EmailEvent.id == _uuid.UUID(email_id),
        EmailEvent.user_id == user_id,
    )
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Email not found")

    gmail_service = await _build_gmail_service_for_user(db, user_id)
    try:
        reply_context = await build_reply_context(
            gmail_service=gmail_service,
            event=event,
            user_email=current_user.email,
            reply_all=reply_all,
        )
    except Exception as exc:
        if _is_gmail_scope_error(exc):
            raise HTTPException(
                status_code=400,
                detail="Gmail send access is missing. Reconnect your Gmail account to grant compose access.",
            ) from exc
        raise HTTPException(status_code=502, detail="Failed to prepare Gmail reply context.") from exc

    return reply_context


@app.post("/api/emails/send", status_code=201)
@limiter.limit(_send_email_rate_limit, error_message="Too many send email requests. Try again in a minute.")
async def send_email_endpoint(
    request: Request,
    payload: SendEmailPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send an email via Gmail API."""
    from backend.services.email_sender import send_email

    user_id = current_user.id
    if payload.application_id:
        app_stmt = select(Application).where(
            Application.id == _uuid.UUID(payload.application_id),
            Application.user_id == user_id,
        )
        app_result = await db.execute(app_stmt)
        if not app_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Application not found")

    gmail_service = await _build_gmail_service_for_user(db, user_id)

    try:
        result = await send_email(
            db=db,
            gmail_service=gmail_service,
            to=payload.to,
            cc=[str(addr) for addr in payload.cc],
            subject=payload.subject,
            body=payload.body,
            application_id=payload.application_id,
            reply_to_email_id=payload.reply_to_email_id,
            reply_to_message_id=payload.reply_to_message_id,
            thread_id=payload.thread_id,
            user_email=current_user.email,
            user_id=user_id,
        )
    except Exception as exc:
        if _is_gmail_scope_error(exc):
            raise HTTPException(
                status_code=400,
                detail="Gmail send access is missing. Reconnect your Gmail account to grant compose access.",
            ) from exc
        raise HTTPException(status_code=502, detail="Gmail send failed.") from exc
    return result


# --- Sprint 13: Interview Calendar ---

class InterviewCreate(BaseModel):
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    interview_type: str = Field("phone", max_length=MAX_SHORT_TEXT_LEN)
    scheduled_at: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    duration_minutes: Optional[int] = None
    interviewer_name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    interviewer_email: Optional[EmailStr] = None
    location_or_link: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    notes: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)


class InterviewUpdate(BaseModel):
    interview_type: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)
    scheduled_at: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    duration_minutes: Optional[int] = None
    interviewer_name: Optional[str] = Field(None, max_length=MAX_NAME_LEN)
    interviewer_email: Optional[EmailStr] = None
    location_or_link: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    notes: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    outcome: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)


def _serialize_interview(i: Interview) -> dict:
    return {
        "id": str(i.id),
        "application_id": str(i.application_id) if i.application_id else None,
        "interview_type": i.interview_type,
        "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
        "duration_minutes": i.duration_minutes,
        "interviewer_name": i.interviewer_name,
        "interviewer_email": i.interviewer_email,
        "location_or_link": i.location_or_link,
        "notes": i.notes,
        "outcome": i.outcome,
        "calendar_event_id": i.calendar_event_id,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


@app.post("/api/interviews", status_code=201)
async def create_interview(
    payload: InterviewCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create an interview record."""
    user_id = _require_user_id(auth)

    scheduled_at = None
    if payload.scheduled_at:
        from dateutil import parser as dateparser
        scheduled_at = dateparser.parse(payload.scheduled_at)

    application_id = None
    if payload.application_id:
        application_id = _uuid.UUID(payload.application_id)
        app_stmt = select(Application).where(
            Application.id == application_id,
            Application.user_id == user_id,
        )
        app_result = await db.execute(app_stmt)
        if not app_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Application not found")

    interview = Interview(
        application_id=application_id,
        interview_type=payload.interview_type,
        scheduled_at=scheduled_at,
        duration_minutes=payload.duration_minutes,
        interviewer_name=payload.interviewer_name,
        interviewer_email=payload.interviewer_email,
        location_or_link=payload.location_or_link,
        notes=payload.notes,
        user_id=user_id,
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)
    return _serialize_interview(interview)


@app.get("/api/interviews")
async def list_interviews(
    application_id: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List interviews, optionally filtered by application."""
    user_id = _require_user_id(auth)
    stmt = select(Interview).where(Interview.user_id == user_id).order_by(Interview.scheduled_at.desc().nullslast())
    if application_id:
        stmt = stmt.where(Interview.application_id == _uuid.UUID(application_id))
    stmt = _paginate(stmt, limit, offset)
    result = await db.execute(stmt)
    return [_serialize_interview(i) for i in result.scalars().all()]


@app.get("/api/interviews/upcoming")
async def upcoming_interviews(
    limit: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Get upcoming interviews (scheduled in the future)."""
    user_id = _require_user_id(auth)
    now = datetime.now(timezone.utc)
    stmt = select(Interview).where(
        Interview.user_id == user_id,
        Interview.scheduled_at > now,
        Interview.outcome == "pending",
    ).order_by(Interview.scheduled_at.asc())
    stmt = _paginate(stmt, limit, offset)
    result = await db.execute(stmt)
    return [_serialize_interview(i) for i in result.scalars().all()]


@app.patch("/api/interviews/{interview_id}")
async def update_interview(
    interview_id: str,
    payload: InterviewUpdate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Update an interview record."""
    user_id = _require_user_id(auth)
    iid = _uuid.UUID(interview_id)
    stmt = select(Interview).where(
        Interview.id == iid,
        Interview.user_id == user_id,
    )
    result = await db.execute(stmt)
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    if payload.interview_type is not None:
        interview.interview_type = payload.interview_type
    if payload.scheduled_at is not None:
        from dateutil import parser as dateparser
        interview.scheduled_at = dateparser.parse(payload.scheduled_at)
    if payload.duration_minutes is not None:
        interview.duration_minutes = payload.duration_minutes
    if payload.interviewer_name is not None:
        interview.interviewer_name = payload.interviewer_name
    if payload.interviewer_email is not None:
        interview.interviewer_email = payload.interviewer_email
    if payload.location_or_link is not None:
        interview.location_or_link = payload.location_or_link
    if payload.notes is not None:
        interview.notes = payload.notes
    if payload.outcome is not None:
        interview.outcome = payload.outcome

    await db.commit()
    await db.refresh(interview)
    return _serialize_interview(interview)


@app.delete("/api/interviews/{interview_id}")
async def delete_interview(interview_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Delete an interview."""
    user_id = _require_user_id(auth)
    iid = _uuid.UUID(interview_id)
    stmt = select(Interview).where(
        Interview.id == iid,
        Interview.user_id == user_id,
    )
    result = await db.execute(stmt)
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    await db.delete(interview)
    await db.commit()
    return {"status": "deleted"}


@app.post("/api/interviews/from-email/{email_id}", status_code=201)
async def create_interview_from_email(
    email_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create interview from a classified email with datetime extraction."""
    import uuid as _uuid
    from backend.services.calendar_sync import extract_interview_datetime

    user_id = _require_user_id(auth)
    eid = _uuid.UUID(email_id)
    stmt = select(EmailEvent).where(
        EmailEvent.id == eid,
        EmailEvent.user_id == user_id,
    )
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Email not found")

    # Extract datetime from email
    extracted = extract_interview_datetime(event.body or "", event.subject or "")

    scheduled_at = None
    duration_minutes = None
    location_or_link = None

    if extracted:
        from dateutil import parser as dateparser
        try:
            scheduled_at = dateparser.parse(extracted["scheduled_at"])
        except (ValueError, TypeError):
            pass
        duration_minutes = extracted.get("duration_minutes")
        location_or_link = extracted.get("location_or_link")

    interview = Interview(
        application_id=event.application_id,
        user_id=user_id,
        interview_type="phone",
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes,
        interviewer_name=event.sender,
        interviewer_email=event.sender_email,
        location_or_link=location_or_link,
        notes=f"Created from email: {event.subject}",
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)
    return _serialize_interview(interview)


# ── Sprint 18: Interview Notes / Second Brain ──────────────────────────


def _serialize_note(n: InterviewNote) -> dict:
    return {
        "id": str(n.id),
        "interview_id": str(n.interview_id) if n.interview_id else None,
        "application_id": str(n.application_id) if n.application_id else None,
        "questions_asked": n.questions_asked,
        "went_well": n.went_well,
        "to_improve": n.to_improve,
        "overall_feeling": n.overall_feeling,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


class NoteCreate(BaseModel):
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    questions_asked: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    went_well: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    to_improve: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    overall_feeling: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)  # great/good/okay/poor


class NotePatch(BaseModel):
    questions_asked: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    went_well: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    to_improve: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)
    overall_feeling: Optional[str] = Field(None, max_length=MAX_SHORT_TEXT_LEN)


@app.post("/api/interviews/{interview_id}/notes", status_code=201)
async def create_interview_note(
    interview_id: str,
    payload: NoteCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create a structured note for an interview."""
    import uuid as _uuid
    iid = _uuid.UUID(interview_id)

    # Verify interview exists
    user_id = _require_user_id(auth)
    stmt = select(Interview).where(
        Interview.id == iid,
        Interview.user_id == user_id,
    )
    result = await db.execute(stmt)
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    note = InterviewNote(
        interview_id=iid,
        application_id=_uuid.UUID(payload.application_id) if payload.application_id else interview.application_id,
        questions_asked=payload.questions_asked,
        went_well=payload.went_well,
        to_improve=payload.to_improve,
        overall_feeling=payload.overall_feeling,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)


@app.get("/api/interviews/{interview_id}/notes")
async def list_interview_notes(
    interview_id: str,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List all notes for an interview."""
    import uuid as _uuid
    user_id = _require_user_id(auth)
    iid = _uuid.UUID(interview_id)
    stmt = (
        select(InterviewNote)
        .join(Interview, InterviewNote.interview_id == Interview.id)
        .where(InterviewNote.interview_id == iid)
        .where(Interview.user_id == user_id)
        .order_by(InterviewNote.created_at.desc())
    )
    stmt = _paginate(stmt, limit, offset)
    result = await db.execute(stmt)
    return [_serialize_note(n) for n in result.scalars().all()]


@app.patch("/api/interviews/notes/{note_id}")
async def update_interview_note(note_id: str, payload: NotePatch, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Update an interview note."""
    import uuid as _uuid
    user_id = _require_user_id(auth)
    nid = _uuid.UUID(note_id)
    stmt = (
        select(InterviewNote)
        .join(Interview, InterviewNote.interview_id == Interview.id)
        .where(InterviewNote.id == nid, Interview.user_id == user_id)
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    for field in ("questions_asked", "went_well", "to_improve", "overall_feeling"):
        val = getattr(payload, field)
        if val is not None:
            setattr(note, field, val)

    await db.commit()
    await db.refresh(note)
    return _serialize_note(note)


@app.delete("/api/interviews/notes/{note_id}")
async def delete_interview_note(note_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Delete an interview note."""
    import uuid as _uuid
    user_id = _require_user_id(auth)
    nid = _uuid.UUID(note_id)
    stmt = (
        select(InterviewNote)
        .join(Interview, InterviewNote.interview_id == Interview.id)
        .where(InterviewNote.id == nid, Interview.user_id == user_id)
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
    await db.commit()
    return {"status": "deleted"}


@app.get("/api/interviews/{interview_id}/prep")
async def get_interview_prep(interview_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Pre-interview prep: surface past notes for same company.

    Returns notes from prior interviews at the same company, plus
    the company's knowledge graph context if available.
    """
    import uuid as _uuid
    user_id = _require_user_id(auth)
    iid = _uuid.UUID(interview_id)

    # Get the interview and its application
    stmt = select(Interview).where(
        Interview.id == iid,
        Interview.user_id == user_id,
    )
    result = await db.execute(stmt)
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    if not interview.application_id:
        return {"past_notes": [], "company_context": None}

    # Get the application to find the company
    app_stmt = select(Application).where(
        Application.id == interview.application_id,
        Application.user_id == user_id,
    )
    app_result = await db.execute(app_stmt)
    app = app_result.scalar_one_or_none()
    if not app:
        return {"past_notes": [], "company_context": None}

    # Find all past notes for the same company
    past_notes_stmt = (
        select(InterviewNote)
        .join(Interview, InterviewNote.interview_id == Interview.id)
        .join(Application, Interview.application_id == Application.id)
        .where(Application.company == app.company, Application.user_id == user_id, Interview.user_id == user_id)
        .where(InterviewNote.interview_id != iid)
        .order_by(InterviewNote.created_at.desc())
        .limit(20)
    )
    past_result = await db.execute(past_notes_stmt)
    past_notes = [_serialize_note(n) for n in past_result.scalars().all()]

    # Get company context if company_id is set
    company_context = None
    if app.company_id:
        company_stmt = select(Company).where(Company.id == app.company_id)
        company_result = await db.execute(company_stmt)
        company = company_result.scalar_one_or_none()
        if company and company.domain:
            from backend.services.knowledge_graph import get_company_context
            company_context = await get_company_context(db, company.domain, user_id=user_id)

    return {"past_notes": past_notes, "company_context": company_context}


@app.get("/api/interviews/past-due")
async def get_past_due_interviews(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Get interviews whose scheduled_at has passed but have no notes yet.

    Used for post-interview prompts: 'How did your interview at {company} go?'
    """
    from sqlalchemy.orm import selectinload

    user_id = _require_user_id(auth)
    now = datetime.now(timezone.utc)
    stmt = (
        select(Interview)
        .where(Interview.user_id == user_id)
        .where(Interview.scheduled_at < now)
        .where(Interview.outcome == "pending")
        .order_by(Interview.scheduled_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    interviews = result.scalars().all()

    # Filter to those without notes
    past_due = []
    for i in interviews:
        note_stmt = select(InterviewNote).where(InterviewNote.interview_id == i.id).limit(1)
        note_result = await db.execute(note_stmt)
        if not note_result.scalar_one_or_none():
            # Get company name from application
            company_name = None
            role_title = None
            if i.application_id:
                app_stmt = select(Application).where(
                    Application.id == i.application_id,
                    Application.user_id == user_id,
                )
                app_result = await db.execute(app_stmt)
                app = app_result.scalar_one_or_none()
                if app:
                    company_name = app.company
                    role_title = app.role_title

            past_due.append({
                **_serialize_interview(i),
                "company_name": company_name,
                "role_title": role_title,
            })

    return past_due


@app.get("/api/interviews/patterns")
async def get_interview_patterns(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Analyze interview note patterns across all applications.

    Returns aggregated insights like outcome rates by interview type,
    common areas of improvement, and performance by company/role category.
    """
    from sqlalchemy import func

    # Get all notes with their interviews
    user_id = _require_user_id(auth)
    stmt = (
        select(InterviewNote, Interview, Application)
        .join(Interview, InterviewNote.interview_id == Interview.id)
        .join(Application, Interview.application_id == Application.id, isouter=True)
        .where(Interview.user_id == user_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return {"total_notes": 0, "patterns": {}}

    # Aggregate feelings
    feeling_counts = {}
    type_outcomes = {}
    company_feelings = {}

    for note, interview, app in rows:
        # Feeling distribution
        feeling = note.overall_feeling or "unknown"
        feeling_counts[feeling] = feeling_counts.get(feeling, 0) + 1

        # Outcome by interview type
        itype = interview.interview_type or "unknown"
        if itype not in type_outcomes:
            type_outcomes[itype] = {"total": 0, "passed": 0, "failed": 0, "pending": 0}
        type_outcomes[itype]["total"] += 1
        type_outcomes[itype][interview.outcome or "pending"] = type_outcomes[itype].get(interview.outcome or "pending", 0) + 1

        # Feeling by company
        if app:
            company = app.company
            if company not in company_feelings:
                company_feelings[company] = []
            company_feelings[company].append(feeling)

    # Find best-performing areas
    best_companies = []
    for company, feelings in company_feelings.items():
        positive = sum(1 for f in feelings if f in ("great", "good"))
        total = len(feelings)
        if total > 0:
            best_companies.append({
                "company": company,
                "positive_rate": round(positive / total, 2),
                "total_interviews": total,
            })
    best_companies.sort(key=lambda x: x["positive_rate"], reverse=True)

    return {
        "total_notes": len(rows),
        "feeling_distribution": feeling_counts,
        "outcome_by_type": type_outcomes,
        "company_performance": best_companies[:10],
    }


# --- Sprint 14: AI-Drafted Communications ---

class DraftRequest(BaseModel):
    application_id: Optional[str] = Field(None, max_length=MAX_ID_LEN)
    contact_email: Optional[EmailStr] = None
    draft_type: str = Field("follow_up", max_length=MAX_SHORT_TEXT_LEN)  # follow_up/introduction/reply/thank_you
    additional_context: Optional[str] = Field(None, max_length=MAX_LONG_TEXT_LEN)


@app.post("/api/drafts/generate")
async def generate_draft_endpoint(
    payload: DraftRequest,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Generate an AI email draft."""
    import uuid as _uuid
    from backend.services.draft_writer import generate_draft
    from backend.dependencies import check_ai_consent

    company = ""
    role = ""
    contact_name = ""
    conversation_history = []
    days_since = 0

    user_id = _require_user_id(auth)
    ai_on = await check_ai_consent(user_id, db)

    # Get application context
    if payload.application_id:
        app_id = _uuid.UUID(payload.application_id)
        stmt = select(Application).where(
            Application.id == app_id,
            Application.user_id == user_id,
        )
        result = await db.execute(stmt)
        app_row = result.scalar_one_or_none()
        if app_row:
            company = app_row.company
            role = app_row.role_title
            if app_row.applied_at:
                days_since = (datetime.now(timezone.utc) - app_row.applied_at.replace(tzinfo=timezone.utc if app_row.applied_at.tzinfo is None else app_row.applied_at.tzinfo)).days

    # Get contact info
    if payload.contact_email:
        contact_stmt = select(Contact).where(
            Contact.email == payload.contact_email,
            Contact.user_id == user_id,
        ).limit(1)
        contact_result = await db.execute(contact_stmt)
        contact = contact_result.scalar_one_or_none()
        if contact:
            contact_name = contact.name or ""

        # Get conversation history
        from sqlalchemy.orm import selectinload
        email_stmt = select(EmailEvent).options(
            selectinload(EmailEvent.application)
        ).where(
            EmailEvent.user_id == user_id,
            EmailEvent.sender_email == payload.contact_email,
        ).order_by(EmailEvent.received_at.desc()).limit(5)
        email_result = await db.execute(email_stmt)
        for e in email_result.scalars().all():
            conversation_history.append({
                "sender": e.sender,
                "subject": e.subject,
                "snippet": e.snippet or e.key_sentence or "",
                "is_from_user": e.is_from_user,
            })

    draft = await generate_draft(
        draft_type=payload.draft_type,
        company=company,
        role=role,
        contact_name=contact_name,
        contact_email=payload.contact_email or "",
        conversation_history=conversation_history,
        days_since=days_since,
        additional_context=payload.additional_context or "",
        ai_enabled=ai_on,
    )
    return draft


# --- Sprint 15: Knowledge Graph ---

@app.get("/api/companies/{domain}/context")
async def get_company_context_endpoint(
    domain: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Get full assembled company context from knowledge graph."""
    from backend.services.knowledge_graph import get_company_context

    user_id = _require_user_id(auth)
    return await get_company_context(db, domain, user_id=user_id)


# --- Sprint 16: Salary Intelligence ---

@app.post("/api/jobs/{job_id}/extract-salary")
async def extract_salary_endpoint(job_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Extract salary from job description and store on application."""
    import uuid as _uuid
    from backend.services.salary_extractor import extract_salary

    user_id = _require_user_id(auth)
    jid = _uuid.UUID(job_id)
    stmt = select(Application).where(
        Application.id == jid,
        Application.user_id == user_id,
    )
    result = await db.execute(stmt)
    app_row = result.scalar_one_or_none()
    if not app_row:
        raise HTTPException(status_code=404, detail="Application not found")

    if not app_row.description_text:
        return {"extracted": False, "reason": "No description text"}

    salary = extract_salary(app_row.description_text)
    if not salary:
        return {"extracted": False, "reason": "No salary found in description"}

    app_row.salary_min = salary["salary_min"]
    app_row.salary_max = salary["salary_max"]
    app_row.salary_currency = salary["salary_currency"]
    app_row.salary_period = salary["salary_period"]
    await db.commit()

    return {"extracted": True, **salary}


@app.get("/api/intelligence/salary")
async def salary_intelligence(
    umbrella_id: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Aggregated salary intelligence by role category and/or location."""
    from backend.services.salary_extractor import aggregate_salaries
    from sqlalchemy import func

    user_id = _require_user_id(auth)
    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.salary_min.isnot(None),
        Application.salary_max.isnot(None),
    )

    if umbrella_id:
        import uuid as _uuid
        stmt = stmt.where(Application.umbrella_id == _uuid.UUID(umbrella_id))
    if location:
        stmt = stmt.where(func.lower(Application.location).like(_contains_like(location), escape="\\"))

    result = await db.execute(stmt)
    apps = result.scalars().all()

    salaries = [
        {
            "salary_min": a.salary_min,
            "salary_max": a.salary_max,
            "salary_currency": a.salary_currency,
            "salary_period": a.salary_period,
        }
        for a in apps
    ]

    aggregated = aggregate_salaries(salaries)

    return {
        "filter": {
            "umbrella_id": umbrella_id,
            "location": location,
        },
        "stats": aggregated,
        "raw_count": len(salaries),
    }


@app.get("/api/export/csv")
async def export_csv(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    import csv
    import io

    from fastapi.responses import StreamingResponse
    from sqlalchemy import func

    stmt = select(
        Application,
        func.count(Contact.id).label("contacts_count"),
    ).outerjoin(Contact).group_by(Application.id).order_by(Application.applied_at.desc())
    stmt = stmt.where(Application.user_id == user_id)

    result = await db.execute(stmt)
    rows = result.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "company", "role_title", "department", "job_url", "source",
        "applied_at", "status", "last_email_at", "notes",
        "contacts_count", "archived_at",
    ])

    for app_row, contacts_count in rows:
        writer.writerow([
            app_row.company,
            app_row.role_title,
            app_row.department or "",
            app_row.job_url or "",
            app_row.source or "",
            app_row.applied_at.isoformat() if app_row.applied_at else "",
            app_row.status or "",
            app_row.last_email_at.isoformat() if app_row.last_email_at else "",
            app_row.notes or "",
            contacts_count,
            app_row.archived_at.isoformat() if app_row.archived_at else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=apptrail_export.csv"},
    )


# ── Sprint 17: Company Visits ──────────────────────────────────────────


class CompanyVisitPayload(BaseModel):
    domain: str = Field(..., max_length=MAX_DOMAIN_LEN)
    url: Optional[str] = Field(None, max_length=MAX_URL_LEN)
    visit_count: int = 1


@app.post("/api/company-visits", status_code=201)
async def record_company_visit(payload: CompanyVisitPayload, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Record or update a career page visit from the extension."""
    user_id = _require_user_id(auth)
    stmt = select(CompanyVisit).where(
        CompanyVisit.domain == payload.domain,
        CompanyVisit.user_id == user_id,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.visit_count = payload.visit_count
        existing.last_visited_at = now
        await db.commit()
        await db.refresh(existing)
        return {
            "id": str(existing.id),
            "domain": existing.domain,
            "visit_count": existing.visit_count,
            "first_visited_at": existing.first_visited_at.isoformat() if existing.first_visited_at else None,
            "last_visited_at": existing.last_visited_at.isoformat() if existing.last_visited_at else None,
        }
    else:
        visit = CompanyVisit(
            domain=payload.domain,
            url=payload.url,
            visit_count=payload.visit_count,
            first_visited_at=now,
            last_visited_at=now,
            user_id=user_id,
        )
        db.add(visit)
        await db.commit()
        await db.refresh(visit)
        return {
            "id": str(visit.id),
            "domain": visit.domain,
            "visit_count": visit.visit_count,
            "first_visited_at": visit.first_visited_at.isoformat(),
            "last_visited_at": visit.last_visited_at.isoformat(),
        }


@app.get("/api/company-visits")
async def list_company_visits(
    min_visits: int = Query(default=1, ge=1),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List tracked company visits, optionally filtered by minimum visit count."""
    user_id = _require_user_id(auth)
    stmt = (
        select(CompanyVisit)
        .where(CompanyVisit.user_id == user_id)
        .where(CompanyVisit.visit_count >= min_visits)
        .order_by(CompanyVisit.last_visited_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    visits = result.scalars().all()
    return [
        {
            "id": str(v.id),
            "domain": v.domain,
            "url": v.url,
            "visit_count": v.visit_count,
            "first_visited_at": v.first_visited_at.isoformat() if v.first_visited_at else None,
            "last_visited_at": v.last_visited_at.isoformat() if v.last_visited_at else None,
        }
        for v in visits
    ]


class SubmissionPayload(BaseModel):
    platform: str = Field(..., max_length=MAX_PLATFORM_LEN)
    url: str = Field(..., max_length=MAX_URL_LEN)
    domain: str = Field(..., max_length=MAX_DOMAIN_LEN)
    enrichment: Optional[dict] = None


@app.post("/api/company-visits/submission", status_code=200)
async def record_submission_detection(payload: SubmissionPayload, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    """Handle auto-detected ATS application submission from the extension.

    Finds the most recent application matching the domain and updates its status to 'applied'.
    Also applies any enrichment data (salary, department) extracted from the confirmation page.
    """
    from sqlalchemy import func

    user_id = _require_user_id(auth)

    # Find matching application by company domain
    app_stmt = (
        select(Application)
        .join(Company, Application.company_id == Company.id, isouter=True)
        .where(Company.domain == payload.domain, Application.user_id == user_id)
        .order_by(Application.applied_at.desc())
        .limit(1)
    )
    result = await db.execute(app_stmt)
    app = result.scalar_one_or_none()

    updated = False
    if app:
        if app.status == "saved":
            app.status = "applied"
            app.applied_at = datetime.now(timezone.utc)
        # Apply enrichment
        if payload.enrichment:
            if payload.enrichment.get("department") and not app.department:
                app.department = payload.enrichment["department"]
            salary_str = payload.enrichment.get("salary")
            if salary_str and not app.salary_min:
                # Try to parse salary range from enrichment string like "$100,000 - $150,000"
                import re
                nums = re.findall(r'[\d,]+', salary_str)
                if len(nums) >= 2:
                    app.salary_min = int(nums[0].replace(',', ''))
                    app.salary_max = int(nums[1].replace(',', ''))
                    app.salary_currency = "USD"
                    app.salary_period = "year"
        await db.commit()
        updated = True

    return {"matched": app is not None, "updated": updated, "platform": payload.platform}


# ── Sprint 19: Notification Preferences & Alerts ──────────────────────


class NotificationPrefPayload(BaseModel):
    sms_enabled: bool | None = None
    sms_phone: str | None = Field(None, max_length=MAX_PHONE_LEN)
    weekly_digest_enabled: bool | None = None
    browser_notifications_enabled: bool | None = None
    radar_updates_enabled: bool | None = None
    inbox_updates_enabled: bool | None = None
    conversations_enabled: bool | None = None
    network_enabled: bool | None = None
    interviews_enabled: bool | None = None
    followups_enabled: bool | None = None
    listings_enabled: bool | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: int | None = Field(None, ge=0, le=23)
    quiet_hours_end: int | None = Field(None, ge=0, le=23)


@app.get("/api/notifications/preferences")
async def get_notification_preferences(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Get current user's notification preferences."""
    user_id = _require_user_id(auth)
    stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    result = await db.execute(stmt)
    pref = result.scalars().first()

    return serialize_notification_preferences(pref)


@app.put("/api/notifications/preferences")
async def update_notification_preferences(
    payload: NotificationPrefPayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create or update notification preferences."""
    user_id = _require_user_id(auth)
    fields = payload.model_fields_set
    stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    result = await db.execute(stmt)
    pref = result.scalars().first()

    if not pref:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)

    if "sms_enabled" in fields:
        pref.sms_enabled = payload.sms_enabled
    if "sms_phone" in fields:
        pref.sms_phone = payload.sms_phone
    if "weekly_digest_enabled" in fields:
        pref.weekly_digest_enabled = payload.weekly_digest_enabled
    if "browser_notifications_enabled" in fields:
        pref.browser_notifications_enabled = payload.browser_notifications_enabled
    if "radar_updates_enabled" in fields:
        pref.radar_updates_enabled = payload.radar_updates_enabled
    if "inbox_updates_enabled" in fields:
        pref.inbox_updates_enabled = payload.inbox_updates_enabled
    if "conversations_enabled" in fields:
        pref.conversations_enabled = payload.conversations_enabled
    if "network_enabled" in fields:
        pref.network_enabled = payload.network_enabled
    if "interviews_enabled" in fields:
        pref.interviews_enabled = payload.interviews_enabled
    if "followups_enabled" in fields:
        pref.followups_enabled = payload.followups_enabled
    if "listings_enabled" in fields:
        pref.listings_enabled = payload.listings_enabled
    if "quiet_hours_enabled" in fields:
        pref.quiet_hours_enabled = payload.quiet_hours_enabled
    if "quiet_hours_start" in fields:
        pref.quiet_hours_start = payload.quiet_hours_start
    if "quiet_hours_end" in fields:
        pref.quiet_hours_end = payload.quiet_hours_end

    from datetime import datetime, timezone
    pref.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(pref)
    return serialize_notification_preferences(pref)


class AlertCreatePayload(BaseModel):
    alert_type: str = Field(..., max_length=MAX_SHORT_TEXT_LEN)
    title: str = Field(..., max_length=MAX_NAME_LEN)
    body: str | None = Field(None, max_length=MAX_LONG_TEXT_LEN)
    action_url: str | None = Field(None, max_length=MAX_URL_LEN)


@app.post("/api/alerts", status_code=201)
async def create_alert(
    payload: AlertCreatePayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create an alert and optionally send SMS for urgent types."""
    user_id = _require_user_id(auth)
    alert = await create_user_alert(
        db,
        user_id=user_id,
        alert_type=payload.alert_type,
        title=payload.title,
        body=payload.body,
        action_url=payload.action_url,
        respect_preferences=False,
    )
    await db.commit()
    if alert is None:
        raise HTTPException(status_code=500, detail="Failed to create alert")
    await db.refresh(alert)

    # Try to send SMS for urgent alerts
    sms_result = None
    try:
        from backend.services.sms_sender import maybe_send_sms_for_alert
        sms_result = await maybe_send_sms_for_alert(
            db, payload.alert_type, payload.title, payload.body, user_id=user_id
        )
    except Exception:
        pass  # SMS is best-effort

    return {
        "id": str(alert.id),
        "alert_type": alert.alert_type,
        "title": alert.title,
        "body": alert.body,
        "action_url": alert.action_url,
        "read": alert.read,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "sms_sent": sms_result is not None,
    }


@app.get("/api/digest/preview")
async def preview_digest(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Preview the weekly digest stats without sending."""
    from backend.tasks.send_weekly_digest import build_digest, render_digest_text

    user_id = _require_user_id(auth)
    stats = await build_digest(db, user_id=user_id)
    return {
        "stats": stats,
        "preview": render_digest_text(stats),
    }


# ── Sprint 20: Resume Tailoring ──────────────────────────────────────


class TailorPayload(BaseModel):
    resume_text: str | None = Field(None, max_length=MAX_RESUME_TEXT_LEN)  # Override resume text; defaults to user profile


@app.post("/api/resume/tailor/{application_id}", status_code=201)
async def tailor_resume_endpoint(
    application_id: str,
    payload: TailorPayload,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Generate a tailored resume for a specific job application."""
    user_id = _require_user_id(auth)
    try:
        app_uuid = _uuid.UUID(application_id)
    except ValueError:
        raise HTTPException(404, "Application not found")

    # Get application
    stmt = select(Application).where(Application.id == app_uuid)
    if user_id:
        stmt = stmt.where(Application.user_id == user_id)
    result = await db.execute(stmt)
    app = result.scalars().first()
    if not app:
        raise HTTPException(404, "Application not found")

    # Get resume text from payload or user profile
    original_text = payload.resume_text
    skills = None
    if not original_text:
        profile_stmt = select(UserProfile)
        if user_id:
            profile_stmt = profile_stmt.where(UserProfile.user_id == user_id)
        profile_result = await db.execute(profile_stmt)
        profile = profile_result.scalars().first()
        if profile and profile.raw_text:
            original_text = profile.raw_text
            skills = profile.skills
        else:
            raise HTTPException(400, "No resume text provided and no user profile found. Upload a resume first.")

    # Get job description
    job_description = app.description_text or ""
    if not job_description:
        raise HTTPException(400, "Application has no job description. Add one before tailoring.")

    # Generate tailored version
    from backend.services.resume_tailor import tailor_resume
    from backend.dependencies import check_ai_consent
    ai_on = await check_ai_consent(user_id, db)
    result = await tailor_resume(
        original_text=original_text,
        job_description=job_description,
        company=app.company or "",
        role=app.role_title or "",
        skills=skills,
        ai_enabled=ai_on,
    )

    # Save draft
    draft = ResumeDraft(
        application_id=app.id,
        original_text=original_text,
        tailored_text=result["tailored_text"],
        changes_summary=result["changes_summary"],
        user_id=user_id,
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)

    return {
        "id": str(draft.id),
        "application_id": str(draft.application_id),
        "original_text": draft.original_text,
        "tailored_text": draft.tailored_text,
        "changes_summary": draft.changes_summary,
        "match_improvements": result.get("match_improvements", ""),
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


@app.get("/api/resume/drafts/{application_id}")
async def list_resume_drafts(
    application_id: str,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List all tailored resume drafts for an application."""
    user_id = _require_user_id(auth)
    try:
        app_uuid = _uuid.UUID(application_id)
    except ValueError:
        return []

    stmt = (
        select(ResumeDraft)
        .where(ResumeDraft.application_id == app_uuid)
        .order_by(ResumeDraft.created_at.desc())
    )
    if user_id:
        stmt = stmt.where(ResumeDraft.user_id == user_id)
    stmt = _paginate(stmt, limit, offset)
    result = await db.execute(stmt)
    drafts = result.scalars().all()

    return [
        {
            "id": str(d.id),
            "application_id": str(d.application_id) if d.application_id else None,
            "tailored_text": d.tailored_text,
            "changes_summary": d.changes_summary,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in drafts
    ]


@app.get("/api/resume/drafts/{application_id}/{draft_id}")
async def get_resume_draft(
    application_id: str,
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Get a specific resume draft with full text for diff view."""
    user_id = _require_user_id(auth)
    try:
        app_uuid = _uuid.UUID(application_id)
        d_uuid = _uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(404, "Draft not found")

    stmt = select(ResumeDraft).where(
        ResumeDraft.id == d_uuid,
        ResumeDraft.application_id == app_uuid,
    )
    if user_id:
        stmt = stmt.where(ResumeDraft.user_id == user_id)
    result = await db.execute(stmt)
    draft = result.scalars().first()
    if not draft:
        raise HTTPException(404, "Draft not found")

    return {
        "id": str(draft.id),
        "application_id": str(draft.application_id) if draft.application_id else None,
        "original_text": draft.original_text,
        "tailored_text": draft.tailored_text,
        "changes_summary": draft.changes_summary,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }


@app.delete("/api/resume/drafts/{application_id}/{draft_id}")
async def delete_resume_draft(
    application_id: str,
    draft_id: str,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Delete a resume draft."""
    user_id = _require_user_id(auth)
    try:
        app_uuid = _uuid.UUID(application_id)
        d_uuid = _uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(404, "Draft not found")

    stmt = select(ResumeDraft).where(
        ResumeDraft.id == d_uuid,
        ResumeDraft.application_id == app_uuid,
    )
    if user_id:
        stmt = stmt.where(ResumeDraft.user_id == user_id)
    result = await db.execute(stmt)
    draft = result.scalars().first()
    if not draft:
        raise HTTPException(404, "Draft not found")

    await db.delete(draft)
    await db.commit()
    return {"status": "deleted"}


def _serialize_research_profile(profile: ResearchProfile) -> dict:
    return {
        "id": str(profile.id),
        "name": profile.name,
        "objective": profile.objective,
        "selected_domains": profile.selected_domains or [],
        "selected_roles": profile.selected_roles or [],
        "selected_companies": profile.selected_companies or [],
        "keywords": profile.keywords or [],
        "excluded_keywords": profile.excluded_keywords or [],
        "source_types": profile.source_types or [],
        "mode": profile.mode,
        "frequency": profile.frequency,
        "depth": profile.depth,
        "notification_mode": profile.notification_mode,
        "minimum_score": profile.minimum_score,
        "target_locations": profile.target_locations or [],
        "remote_types": profile.remote_types or [],
        "seniority_levels": profile.seniority_levels or [],
        "research_source_scopes": profile.research_source_scopes or [],
        "use_profile_context": profile.use_profile_context,
        "include_public_web_research": profile.include_public_web_research,
        "report_prompt_notes": profile.report_prompt_notes,
        "max_search_queries": profile.max_search_queries,
        "max_sources_per_run": profile.max_sources_per_run,
        "active": profile.active,
        "last_run_at": profile.last_run_at.isoformat() if profile.last_run_at else None,
        "next_run_at": profile.next_run_at.isoformat() if profile.next_run_at else None,
        "last_successful_run_at": profile.last_successful_run_at.isoformat() if profile.last_successful_run_at else None,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _serialize_run(run: ResearchRun) -> dict:
    return {
        "id": str(run.id),
        "profile_id": str(run.profile_id),
        "run_type": run.run_type,
        "mode": run.mode,
        "trigger_reason": run.trigger_reason,
        "status": run.status,
        "orchestrator_version": run.orchestrator_version,
        "graph_thread_id": run.graph_thread_id,
        "current_step": run.current_step,
        "report_id": str(run.report_id) if run.report_id else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "source_counts": run.source_counts or {},
        "signal_counts": run.signal_counts or {},
        "error_message": run.error_message,
        "status_detail": run.status_detail or {},
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "llm_call_count": run.llm_call_count,
        "cost_estimate_cents": run.cost_estimate_cents,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _serialize_signal(signal: OpportunitySignal, score: OpportunityScore | None = None) -> dict:
    payload = {
        "id": str(signal.id),
        "profile_id": str(signal.profile_id) if signal.profile_id else None,
        "company_id": str(signal.company_id) if signal.company_id else None,
        "application_id": str(signal.application_id) if signal.application_id else None,
        "event_type": signal.event_type,
        "title": signal.title,
        "summary": signal.summary,
        "evidence": signal.evidence or [],
        "domains": signal.domains or [],
        "roles": signal.roles or [],
        "tech_stack": signal.tech_stack or [],
        "confidence": signal.confidence,
        "occurred_at": signal.occurred_at.isoformat() if signal.occurred_at else None,
        "created_at": signal.created_at.isoformat() if signal.created_at else None,
    }
    if score:
        payload["score"] = {
            "total_score": score.total_score,
            "role_fit": score.role_fit,
            "domain_fit": score.domain_fit,
            "company_interest": score.company_interest,
            "recency": score.recency,
            "public_data_buildability": score.public_data_buildability,
            "outreach_path_strength": score.outreach_path_strength,
            "portfolio_gap_relevance": score.portfolio_gap_relevance,
            "source_confidence": score.source_confidence,
            "explanation": score.explanation,
        }
    return payload


def _serialize_brief(brief: OpportunityBrief) -> dict:
    return {
        "id": str(brief.id),
        "profile_id": str(brief.profile_id) if brief.profile_id else None,
        "run_id": str(brief.run_id) if brief.run_id else None,
        "signal_id": str(brief.signal_id) if brief.signal_id else None,
        "title": brief.title,
        "brief_type": brief.brief_type,
        "markdown": brief.markdown,
        "structured_json": brief.structured_json,
        "confidence": brief.confidence,
        "created_at": brief.created_at.isoformat() if brief.created_at else None,
    }


def _serialize_action(action: RecommendedAction) -> dict:
    return {
        "id": str(action.id),
        "profile_id": str(action.profile_id) if action.profile_id else None,
        "signal_id": str(action.signal_id) if action.signal_id else None,
        "brief_id": str(action.brief_id) if action.brief_id else None,
        "company_id": str(action.company_id) if action.company_id else None,
        "action_type": action.action_type,
        "title": action.title,
        "body": action.body,
        "payload": action.payload,
        "priority": action.priority,
        "status": action.status,
        "due_at": action.due_at.isoformat() if action.due_at else None,
        "created_at": action.created_at.isoformat() if action.created_at else None,
        "completed_at": action.completed_at.isoformat() if action.completed_at else None,
    }


@app.post("/api/research/profiles", status_code=201)
async def create_research_profile(
    payload: ResearchProfileCreate,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    profile = ResearchProfile(user_id=user_id, **payload.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return _serialize_research_profile(profile)


@app.get("/api/research/profiles")
async def list_research_profiles(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    stmt = (
        select(ResearchProfile)
        .where(ResearchProfile.user_id == user_id)
        .order_by(ResearchProfile.created_at.desc())
    )
    rows = (await db.execute(_paginate(stmt, limit, offset))).scalars().all()
    return [_serialize_research_profile(row) for row in rows]


@app.get("/api/research/profiles/{profile_id}")
async def get_research_profile(profile_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    try:
        p_uuid = _uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(404, "Profile not found")
    stmt = select(ResearchProfile).where(ResearchProfile.id == p_uuid, ResearchProfile.user_id == user_id)
    profile = (await db.execute(stmt)).scalars().first()
    if not profile:
        raise HTTPException(404, "Profile not found")
    return _serialize_research_profile(profile)


@app.patch("/api/research/profiles/{profile_id}")
async def update_research_profile(profile_id: str, payload: ResearchProfileUpdate, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    try:
        p_uuid = _uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(404, "Profile not found")
    stmt = select(ResearchProfile).where(ResearchProfile.id == p_uuid, ResearchProfile.user_id == user_id)
    profile = (await db.execute(stmt)).scalars().first()
    if not profile:
        raise HTTPException(404, "Profile not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile)
    return _serialize_research_profile(profile)


@app.delete("/api/research/profiles/{profile_id}")
async def delete_research_profile(profile_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    try:
        p_uuid = _uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(404, "Profile not found")
    stmt = select(ResearchProfile).where(ResearchProfile.id == p_uuid, ResearchProfile.user_id == user_id)
    profile = (await db.execute(stmt)).scalars().first()
    if not profile:
        raise HTTPException(404, "Profile not found")
    await db.delete(profile)
    await db.commit()
    return {"status": "deleted"}


@app.post("/api/research/profiles/{profile_id}/run", status_code=201)
async def run_research_profile(profile_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    try:
        p_uuid = _uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(404, "Profile not found")
    profile = (
        await db.execute(
            select(ResearchProfile).where(ResearchProfile.id == p_uuid, ResearchProfile.user_id == user_id)
        )
    ).scalars().first()
    if not profile:
        raise HTTPException(404, "Profile not found")

    run = ResearchRun(
        user_id=user_id,
        profile_id=profile.id,
        run_type="manual",
        mode=profile.mode,
        trigger_reason="manual_run",
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    try:
        candidates = await collect_internal_sources(db, profile, user_id)
        source_items: list[ResearchSourceItem] = []
        for candidate in candidates:
            company_id = None
            if candidate.company_domain:
                company = (
                    await db.execute(select(Company).where(Company.domain == candidate.company_domain))
                ).scalars().first()
                if company:
                    company_id = company.id

            existing_stmt = select(ResearchSourceItem).where(
                ResearchSourceItem.user_id == user_id,
                ResearchSourceItem.source_url == candidate.source_url,
                ResearchSourceItem.content_hash == candidate.content_hash,
            )
            existing = (await db.execute(existing_stmt)).scalars().first()
            if existing:
                source_items.append(existing)
                continue

            item = ResearchSourceItem(
                run_id=run.id,
                user_id=user_id,
                profile_id=profile.id,
                company_id=company_id,
                source_type=candidate.source_type,
                source_name=candidate.source_name,
                source_url=candidate.source_url,
                external_id=candidate.external_id,
                title=candidate.title,
                raw_text=candidate.raw_text,
                raw_json=candidate.raw_json,
                published_at=candidate.published_at,
                content_hash=candidate.content_hash,
            )
            db.add(item)
            source_items.append(item)

        await db.flush()

        signal_counter: dict[str, int] = {}
        for item in source_items:
            generated = extract_signals(item, user_id=user_id, profile_id=profile.id, run_id=run.id, company_id=item.company_id)
            for signal in generated:
                duplicate_stmt = select(OpportunitySignal).where(
                    OpportunitySignal.user_id == user_id,
                    OpportunitySignal.source_item_id == item.id,
                    OpportunitySignal.event_type == signal.event_type,
                )
                existing_signal = (await db.execute(duplicate_stmt)).scalars().first()
                if existing_signal:
                    continue

                db.add(signal)
                await db.flush()

                scoring = score_signal(signal, profile=profile)
                score_row = OpportunityScore(
                    signal_id=signal.id,
                    user_id=user_id,
                    profile_id=profile.id,
                    **scoring,
                )
                db.add(score_row)

                brief_payload = generate_briefs(signal, scoring)
                brief = OpportunityBrief(
                    user_id=user_id,
                    profile_id=profile.id,
                    run_id=run.id,
                    signal_id=signal.id,
                    **brief_payload,
                )
                db.add(brief)
                await db.flush()

                for action_payload in generate_actions(signal, scoring):
                    db.add(
                        RecommendedAction(
                            user_id=user_id,
                            profile_id=profile.id,
                            signal_id=signal.id,
                            brief_id=brief.id,
                            company_id=signal.company_id,
                            action_type=action_payload["action_type"],
                            title=action_payload["title"],
                            body=action_payload.get("body"),
                            payload=action_payload.get("payload"),
                            priority=action_payload.get("priority", 50),
                        )
                    )

                if scoring["total_score"] >= max(profile.minimum_score, 85):
                    db.add(
                        Alert(
                            user_id=user_id,
                            alert_type="opportunity_signal",
                            title=f"Radar signal: {signal.title}",
                            body=signal.summary,
                            action_url=_alert_action_url("/radar", profile_id=str(profile.id), signal_id=str(signal.id)),
                        )
                    )

                signal_counter[signal.event_type] = signal_counter.get(signal.event_type, 0) + 1

        run.source_counts = {"total": len(source_items)}
        run.signal_counts = signal_counter
        run.status = "succeeded"
        run.completed_at = datetime.now(timezone.utc)
        profile.last_run_at = run.completed_at
        profile.last_successful_run_at = run.completed_at
        await db.commit()
        await db.refresh(run)
        return _serialize_run(run)
    except Exception as exc:
        await db.rollback()
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.add(run)
        await db.commit()
        raise


@app.get("/api/research/runs")
async def list_research_runs(
    profile_id: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    stmt = select(ResearchRun).where(ResearchRun.user_id == user_id).order_by(ResearchRun.created_at.desc())
    if profile_id:
        try:
            stmt = stmt.where(ResearchRun.profile_id == _uuid.UUID(profile_id))
        except ValueError:
            return []
    runs = (await db.execute(_paginate(stmt, limit, offset))).scalars().all()
    return [_serialize_run(r) for r in runs]


@app.get("/api/research/signals")
async def list_opportunity_signals(
    profile_id: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    stmt = select(OpportunitySignal).where(OpportunitySignal.user_id == user_id).order_by(OpportunitySignal.created_at.desc())
    if profile_id:
        try:
            stmt = stmt.where(OpportunitySignal.profile_id == _uuid.UUID(profile_id))
        except ValueError:
            return []
    signals = (await db.execute(_paginate(stmt, limit, offset))).scalars().all()

    signal_ids = [signal.id for signal in signals]
    scores: dict[_uuid.UUID, OpportunityScore] = {}
    if signal_ids:
        score_rows = (
            await db.execute(select(OpportunityScore).where(OpportunityScore.signal_id.in_(signal_ids)))
        ).scalars().all()
        scores = {row.signal_id: row for row in score_rows}

    return [_serialize_signal(signal, scores.get(signal.id)) for signal in signals]


@app.get("/api/research/briefs")
async def list_opportunity_briefs(
    profile_id: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    stmt = select(OpportunityBrief).where(OpportunityBrief.user_id == user_id).order_by(OpportunityBrief.created_at.desc())
    if profile_id:
        try:
            stmt = stmt.where(OpportunityBrief.profile_id == _uuid.UUID(profile_id))
        except ValueError:
            return []
    briefs = (await db.execute(_paginate(stmt, limit, offset))).scalars().all()
    return [_serialize_brief(brief) for brief in briefs]


@app.get("/api/research/actions")
async def list_recommended_actions(
    profile_id: Optional[str] = Query(None),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    user_id = _require_user_id(auth)
    stmt = (
        select(RecommendedAction)
        .where(RecommendedAction.user_id == user_id)
        .order_by(RecommendedAction.priority.desc(), RecommendedAction.created_at.desc())
    )
    if profile_id:
        try:
            stmt = stmt.where(RecommendedAction.profile_id == _uuid.UUID(profile_id))
        except ValueError:
            return []
    actions = (await db.execute(_paginate(stmt, limit, offset))).scalars().all()
    return [_serialize_action(action) for action in actions]


@app.patch("/api/research/actions/{action_id}")
async def update_recommended_action(action_id: str, payload: RecommendedActionUpdate, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    try:
        a_uuid = _uuid.UUID(action_id)
    except ValueError:
        raise HTTPException(404, "Action not found")
    action = (
        await db.execute(select(RecommendedAction).where(RecommendedAction.id == a_uuid, RecommendedAction.user_id == user_id))
    ).scalars().first()
    if not action:
        raise HTTPException(404, "Action not found")
    current_status = action.status
    next_status = payload.status
    if next_status != current_status and next_status not in _ACTION_STATUS_TRANSITIONS.get(current_status, set()):
        raise HTTPException(400, f"Invalid action transition: {current_status} -> {next_status}")

    action.status = next_status
    if next_status == "completed":
        action.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(action)
    return _serialize_action(action)


@app.post("/api/research/actions/{action_id}/accept")
async def accept_recommended_action(action_id: str, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    return await update_recommended_action(action_id, RecommendedActionUpdate(status="accepted"), db, auth)


@app.post("/api/research/feedback", status_code=201)
async def create_research_feedback(payload: ResearchFeedbackCreate, db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)

    def _to_uuid(value: str | None):
        if not value:
            return None
        try:
            return _uuid.UUID(value)
        except ValueError:
            raise HTTPException(400, f"Invalid uuid: {value}")

    feedback = ResearchFeedback(
        user_id=user_id,
        signal_id=_to_uuid(payload.signal_id),
        brief_id=_to_uuid(payload.brief_id),
        action_id=_to_uuid(payload.action_id),
        report_id=_to_uuid(payload.report_id),
        run_step_id=_to_uuid(payload.run_step_id),
        feedback_scope=payload.feedback_scope,
        rating=payload.rating,
        notes=payload.notes,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return {
        "id": str(feedback.id),
        "signal_id": str(feedback.signal_id) if feedback.signal_id else None,
        "brief_id": str(feedback.brief_id) if feedback.brief_id else None,
        "action_id": str(feedback.action_id) if feedback.action_id else None,
        "report_id": str(feedback.report_id) if feedback.report_id else None,
        "run_step_id": str(feedback.run_step_id) if feedback.run_step_id else None,
        "feedback_scope": feedback.feedback_scope,
        "rating": feedback.rating,
        "notes": feedback.notes,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }


@app.get("/api/research/feedback/stats")
async def research_feedback_stats(db: AsyncSession = Depends(get_db), auth: dict = Depends(verify_api_key)):
    user_id = _require_user_id(auth)
    stmt = (
        select(ResearchFeedback)
        .where(ResearchFeedback.user_id == user_id)
        .order_by(ResearchFeedback.created_at.desc())
    )
    feedback_rows = (await db.execute(stmt)).scalars().all()

    total = len(feedback_rows)
    useful = sum(1 for row in feedback_rows if row.rating == "useful")
    not_useful = sum(1 for row in feedback_rows if row.rating == "not_useful")
    usefulness_rate = round((useful / total) * 100, 1) if total else 0.0

    return {
        "total_feedback": total,
        "useful": useful,
        "not_useful": not_useful,
        "usefulness_rate": usefulness_rate,
        "notes_count": sum(1 for row in feedback_rows if row.notes),
        "recent_feedback": [
            {
                "id": str(row.id),
                "signal_id": str(row.signal_id) if row.signal_id else None,
                "brief_id": str(row.brief_id) if row.brief_id else None,
                "action_id": str(row.action_id) if row.action_id else None,
                "report_id": str(row.report_id) if row.report_id else None,
                "run_step_id": str(row.run_step_id) if row.run_step_id else None,
                "feedback_scope": row.feedback_scope,
                "rating": row.rating,
                "notes": row.notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in feedback_rows[:5]
        ],
    }


# ── Classifier Audit Dashboard ───────────────────────────────────────

AUDIT_RUNS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "audit", "runs")


def _ensure_audit_dir():
    os.makedirs(AUDIT_RUNS_DIR, exist_ok=True)


@app.get("/api/audit/runs")
async def list_audit_runs(auth: dict = Depends(verify_api_key)):
    """List all audit runs with summary metrics."""
    _ensure_audit_dir()
    runs = []
    for fname in sorted(os.listdir(AUDIT_RUNS_DIR), reverse=True):
        if fname.endswith("_meta.json"):
            path = os.path.join(AUDIT_RUNS_DIR, fname)
            with open(path) as f:
                runs.append(json.load(f))
    return runs


@app.get("/api/audit/runs/{run_id}")
async def get_audit_run(run_id: str, auth: dict = Depends(verify_api_key)):
    """Get run details including all email rows."""
    meta_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_meta.json")
    data_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_data.csv")

    if not os.path.exists(meta_path):
        raise HTTPException(404, "Run not found")

    with open(meta_path) as f:
        meta = json.load(f)

    emails = []
    if os.path.exists(data_path):
        with open(data_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                emails.append(row)

    return {"meta": meta, "emails": emails}


@app.post("/api/audit/runs", status_code=201)
async def create_audit_run(
    file: UploadFile = File(...),
    name: str = Form(...),
    classifier_engine: str = Form("unknown"),
    model: str = Form("unknown"),
    prompt_version: str = Form("v1"),
    notes: str = Form(""),
    auth: dict = Depends(verify_api_key),
):
    """Upload a reviewed CSV and create a new audit run."""
    from backend.services.audit_metrics import compute_run_metrics, parse_audit_csv

    _ensure_audit_dir()

    file_bytes = await file.read()
    rows = parse_audit_csv(file_bytes)

    if not rows:
        raise HTTPException(400, "CSV is empty or has no valid rows")

    # Generate run ID from timestamp
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)
    run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"

    # Compute metrics
    metrics = compute_run_metrics(rows)
    reviewed_count = sum(1 for r in rows if (r.get("review_correct") or "").strip())

    meta = {
        "id": run_id,
        "name": name,
        "created_at": now.isoformat(),
        "classifier_engine": classifier_engine,
        "model": model,
        "prompt_version": prompt_version,
        "notes": notes,
        "total_emails": len(rows),
        "reviewed_emails": reviewed_count,
        "metrics": metrics,
    }

    # Write files
    meta_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_meta.json")
    data_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_data.csv")

    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    with open(data_path, "wb") as f:
        f.write(file_bytes)

    return meta


@app.get("/api/audit/compare")
async def compare_audit_runs(
    run_ids: Optional[str] = Query(None),
    auth: dict = Depends(verify_api_key),
):
    """Compare metrics across runs. Pass comma-separated run_ids or omit for all."""
    from backend.services.audit_metrics import compare_runs

    _ensure_audit_dir()

    metas = []
    for fname in os.listdir(AUDIT_RUNS_DIR):
        if fname.endswith("_meta.json"):
            rid = fname.replace("_meta.json", "")
            if run_ids and rid not in run_ids.split(","):
                continue
            with open(os.path.join(AUDIT_RUNS_DIR, fname)) as f:
                metas.append(json.load(f))

    return compare_runs(metas)


@app.delete("/api/audit/runs/{run_id}")
async def delete_audit_run(run_id: str, auth: dict = Depends(verify_api_key)):
    """Delete a run and its data."""
    meta_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_meta.json")
    data_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_data.csv")

    if not os.path.exists(meta_path):
        raise HTTPException(404, "Run not found")

    os.remove(meta_path)
    if os.path.exists(data_path):
        os.remove(data_path)

    return {"status": "deleted"}


@app.patch("/api/audit/runs/{run_id}/emails/{email_idx}")
async def update_audit_email_review(
    run_id: str,
    email_idx: int,
    body: dict,
    auth: dict = Depends(verify_api_key),
):
    """Update review columns for a single email row, recompute metrics."""
    from backend.services.audit_metrics import compute_run_metrics

    data_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_data.csv")
    meta_path = os.path.join(AUDIT_RUNS_DIR, f"{run_id}_meta.json")

    if not os.path.exists(data_path) or not os.path.exists(meta_path):
        raise HTTPException(404, "Run not found")

    # Read CSV
    with open(data_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if email_idx < 0 or email_idx >= len(rows):
        raise HTTPException(400, f"Invalid email index {email_idx}")

    # Update review columns
    review_fields = {
        "review_correct", "review_expected_decision",
        "review_expected_classification", "review_expected_network_contact",
        "review_expected_status_change", "review_reason",
    }
    for key, value in body.items():
        if key in review_fields:
            rows[email_idx][key] = value

    # Rewrite CSV
    import io as _io
    output = _io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    with open(data_path, "w", encoding="utf-8") as f:
        f.write(output.getvalue())

    # Recompute metrics
    metrics = compute_run_metrics(rows)
    reviewed_count = sum(1 for r in rows if (r.get("review_correct") or "").strip())

    with open(meta_path) as f:
        meta = json.load(f)
    meta["metrics"] = metrics
    meta["reviewed_emails"] = reviewed_count
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return {"status": "updated", "metrics": metrics}


# ── Extraction Reports ────────────────────────────────────────────────

class ExtractionReportCreate(BaseModel):
    report_type: str  # missing_data | undetected_site | false_positive | wrong_data
    url: str
    domain: str | None = None
    platform_detected: str | None = None
    extraction_method: str | None = None
    extracted_data: dict | None = None
    corrected_data: dict | None = None
    fields_flagged: list[str] | None = None
    user_agent: str | None = None
    extension_version: str | None = None
    extractor_version: str | None = None
    notes: str | None = None


@app.post("/api/extraction-reports", status_code=201)
async def create_extraction_report(
    body: ExtractionReportCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """Submit an extraction report from the extension."""
    valid_types = {"missing_data", "undetected_site", "false_positive", "wrong_data"}
    if body.report_type not in valid_types:
        raise HTTPException(400, f"report_type must be one of {valid_types}")

    user_id = None
    if hasattr(_user, "id"):
        user_id = _user.id

    report = ExtractionReport(
        user_id=user_id,
        report_type=body.report_type,
        url=body.url,
        domain=body.domain,
        platform_detected=body.platform_detected,
        extraction_method=body.extraction_method,
        extracted_data=body.extracted_data,
        corrected_data=body.corrected_data,
        fields_flagged=body.fields_flagged,
        user_agent=body.user_agent,
        extension_version=body.extension_version,
        extractor_version=body.extractor_version,
        notes=body.notes,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return {
        "id": str(report.id),
        "report_type": report.report_type,
        "url": report.url,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@app.get("/api/extraction-reports")
async def list_extraction_reports(
    report_type: str | None = None,
    platform: str | None = None,
    domain: str | None = None,
    resolved: bool | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """List extraction reports with filters (admin view)."""
    q = select(ExtractionReport).order_by(ExtractionReport.created_at.desc())
    if report_type:
        q = q.where(ExtractionReport.report_type == report_type)
    if platform:
        q = q.where(ExtractionReport.platform_detected == platform)
    if domain:
        q = q.where(ExtractionReport.domain == domain)
    if resolved is not None:
        q = q.where(ExtractionReport.resolved == resolved)
    q = q.offset(offset).limit(limit)

    result = await db.execute(q)
    reports = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "report_type": r.report_type,
            "url": r.url,
            "domain": r.domain,
            "platform_detected": r.platform_detected,
            "extraction_method": r.extraction_method,
            "extracted_data": r.extracted_data,
            "corrected_data": r.corrected_data,
            "fields_flagged": r.fields_flagged,
            "extension_version": r.extension_version,
            "extractor_version": r.extractor_version,
            "notes": r.notes,
            "resolved": r.resolved,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@app.get("/api/extraction-reports/stats")
async def extraction_report_stats(
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """Aggregate stats for the admin dashboard."""
    from sqlalchemy import func

    # Total counts by type
    type_q = await db.execute(
        select(ExtractionReport.report_type, func.count())
        .group_by(ExtractionReport.report_type)
    )
    by_type = {row[0]: row[1] for row in type_q.all()}

    # Counts by platform
    platform_q = await db.execute(
        select(ExtractionReport.platform_detected, func.count())
        .where(ExtractionReport.platform_detected.is_not(None))
        .group_by(ExtractionReport.platform_detected)
    )
    by_platform = {row[0]: row[1] for row in platform_q.all()}

    # Most-reported fields (flatten fields_flagged arrays)
    fields_q = await db.execute(
        select(ExtractionReport.fields_flagged)
        .where(ExtractionReport.fields_flagged.is_not(None))
    )
    field_counts: dict[str, int] = {}
    for (fields,) in fields_q.all():
        if isinstance(fields, list):
            for f in fields:
                field_counts[f] = field_counts.get(f, 0) + 1

    # Unresolved count
    unresolved_q = await db.execute(
        select(func.count()).where(ExtractionReport.resolved == False)  # noqa: E712
    )
    unresolved = unresolved_q.scalar() or 0

    # Total
    total_q = await db.execute(select(func.count()).select_from(ExtractionReport))
    total = total_q.scalar() or 0

    return {
        "total": total,
        "unresolved": unresolved,
        "by_type": by_type,
        "by_platform": by_platform,
        "by_field": field_counts,
    }


@app.patch("/api/extraction-reports/{report_id}")
async def update_extraction_report(
    report_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """Mark a report as resolved or add admin notes."""
    import uuid as _uuid
    report_uuid = _uuid.UUID(report_id)
    result = await db.execute(
        select(ExtractionReport).where(ExtractionReport.id == report_uuid)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    if "resolved" in body:
        report.resolved = body["resolved"]
        if body["resolved"]:
            report.resolved_at = datetime.now(timezone.utc)
        else:
            report.resolved_at = None
    if "notes" in body:
        report.notes = body["notes"]

    await db.commit()
    return {"status": "updated", "id": str(report.id), "resolved": report.resolved}


# ── Extraction Changelog CRUD ─────────────────────────────────────────


@app.post("/api/extraction-changelog")
async def create_changelog_entry(
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """Create a new extraction/classifier changelog entry."""
    version = body.get("version")
    description = body.get("description")
    if not version or not description:
        raise HTTPException(400, "version and description are required")

    change_type = body.get("change_type", "extraction")
    if change_type not in ("extraction", "classifier", "both"):
        raise HTTPException(400, "change_type must be extraction, classifier, or both")

    entry = ExtractionChangelog(
        version=version,
        description=description,
        platforms_affected=body.get("platforms_affected"),
        fields_affected=body.get("fields_affected"),
        change_type=change_type,
    )
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, f"Changelog version '{version}' already exists")
    await db.refresh(entry)
    return {
        "id": str(entry.id),
        "version": entry.version,
        "description": entry.description,
        "platforms_affected": entry.platforms_affected,
        "fields_affected": entry.fields_affected,
        "change_type": entry.change_type,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


@app.get("/api/extraction-changelog")
async def list_changelog_entries(
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """List all changelog entries ordered by creation date desc."""
    result = await db.execute(
        select(ExtractionChangelog).order_by(ExtractionChangelog.created_at.desc())
    )
    entries = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "version": e.version,
            "description": e.description,
            "platforms_affected": e.platforms_affected,
            "fields_affected": e.fields_affected,
            "change_type": e.change_type,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


@app.patch("/api/extraction-changelog/{entry_id}")
async def update_changelog_entry(
    entry_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """Update a changelog entry."""
    import uuid as _uuid
    entry_uuid = _uuid.UUID(entry_id)
    result = await db.execute(
        select(ExtractionChangelog).where(ExtractionChangelog.id == entry_uuid)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Changelog entry not found")

    for field in ("description", "platforms_affected", "fields_affected", "change_type"):
        if field in body:
            setattr(entry, field, body[field])

    await db.commit()
    return {
        "id": str(entry.id),
        "version": entry.version,
        "description": entry.description,
        "platforms_affected": entry.platforms_affected,
        "fields_affected": entry.fields_affected,
        "change_type": entry.change_type,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


# ── Version Accuracy Stats ────────────────────────────────────────────


@app.get("/api/extraction-reports/version-stats")
async def extraction_version_stats(
    db: AsyncSession = Depends(get_db),
    _user=Depends(verify_api_key),
):
    """Group extraction reports by extractor_version and compute per-field accuracy.

    For each version, counts total reports, reports with corrections (wrong_data),
    and per-field accuracy rates based on fields_flagged.
    """
    from sqlalchemy import func

    # Get all reports with an extractor_version
    result = await db.execute(
        select(ExtractionReport).where(
            ExtractionReport.extractor_version.is_not(None)
        ).order_by(ExtractionReport.created_at)
    )
    reports = result.scalars().all()

    versions: dict = {}
    for r in reports:
        v = r.extractor_version
        if v not in versions:
            versions[v] = {
                "version": v,
                "total_reports": 0,
                "wrong_data_reports": 0,
                "false_positive_reports": 0,
                "undetected_site_reports": 0,
                "fields_flagged_counts": {},
                "fields_total": 0,
                "first_report": r.created_at.isoformat() if r.created_at else None,
                "last_report": None,
            }

        versions[v]["total_reports"] += 1
        versions[v]["last_report"] = r.created_at.isoformat() if r.created_at else None

        if r.report_type == "wrong_data":
            versions[v]["wrong_data_reports"] += 1
            if isinstance(r.fields_flagged, list):
                for f in r.fields_flagged:
                    versions[v]["fields_flagged_counts"][f] = (
                        versions[v]["fields_flagged_counts"].get(f, 0) + 1
                    )
                    versions[v]["fields_total"] += 1
        elif r.report_type == "false_positive":
            versions[v]["false_positive_reports"] += 1
        elif r.report_type == "undetected_site":
            versions[v]["undetected_site_reports"] += 1

    # Compute per-field accuracy for each version
    version_list = []
    for v, data in versions.items():
        total = data["total_reports"]
        wrong = data["wrong_data_reports"]
        field_accuracy = {}
        for field, flagged_count in data["fields_flagged_counts"].items():
            # Accuracy = 1 - (flagged / total reports for this version)
            field_accuracy[field] = round(1 - (flagged_count / total), 3) if total > 0 else None

        version_list.append({
            "version": data["version"],
            "total_reports": total,
            "wrong_data_reports": wrong,
            "false_positive_reports": data["false_positive_reports"],
            "undetected_site_reports": data["undetected_site_reports"],
            "accuracy_rate": round(1 - (wrong / total), 3) if total > 0 else None,
            "field_accuracy": field_accuracy,
            "first_report": data["first_report"],
            "last_report": data["last_report"],
        })

    # Also pull changelog entries to correlate versions with changes
    changelog_result = await db.execute(
        select(ExtractionChangelog).order_by(ExtractionChangelog.created_at)
    )
    changelog = [
        {
            "version": e.version,
            "description": e.description,
            "platforms_affected": e.platforms_affected,
            "fields_affected": e.fields_affected,
            "change_type": e.change_type,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in changelog_result.scalars().all()
    ]

    return {
        "versions": version_list,
        "changelog": changelog,
    }


# ---------------------------------------------------------------------------
# Data Consent & Account Management
# ---------------------------------------------------------------------------

CONSENT_TYPES = ("core", "ai_processing", "third_party_enrichment", "web_research")


class ConsentBody(BaseModel):
    core: bool
    ai_processing: bool
    third_party_enrichment: bool
    web_research: bool | None = None


@app.get("/api/consent")
async def get_consent(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DataConsent).where(DataConsent.user_id == current_user.id)
    )
    rows = {r.consent_type: r.granted for r in result.scalars().all()}
    return {
        "consents": {ct: rows.get(ct, False) for ct in CONSENT_TYPES},
        "accepted_at": current_user.data_consent_accepted_at.isoformat() if current_user.data_consent_accepted_at else None,
    }


@app.put("/api/consent")
async def update_consent(
    body: ConsentBody,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.core:
        raise HTTPException(status_code=400, detail="Core data consent is required to use AppTrail.")

    now = datetime.now(timezone.utc)
    ip = request.client.host if request.client else None
    requested_consents = {
        "core": body.core,
        "ai_processing": body.ai_processing,
        "third_party_enrichment": body.third_party_enrichment,
        "web_research": body.web_research,
    }
    mapping: dict[str, bool] = {}

    for consent_type, requested_value in requested_consents.items():
        result = await db.execute(
            select(DataConsent).where(
                DataConsent.user_id == current_user.id,
                DataConsent.consent_type == consent_type,
            )
        )
        existing = result.scalar_one_or_none()
        granted = existing.granted if requested_value is None and existing else bool(requested_value)
        mapping[consent_type] = granted
        if existing:
            was_granted = existing.granted
            existing.granted = granted
            existing.updated_at = now
            existing.ip_address = ip
            if granted and not was_granted:
                existing.granted_at = now
                existing.revoked_at = None
            elif not granted and was_granted:
                existing.revoked_at = now
        else:
            consent = DataConsent(
                user_id=current_user.id,
                consent_type=consent_type,
                granted=granted,
                granted_at=now if granted else None,
                ip_address=ip,
                updated_at=now,
            )
            db.add(consent)

    current_user.data_consent_accepted_at = now
    current_user.updated_at = now
    await db.commit()

    return {
        "consents": mapping,
        "accepted_at": now.isoformat(),
    }


class DeleteAccountBody(BaseModel):
    confirm: str


@app.delete("/api/account", status_code=204)
async def delete_account(
    body: DeleteAccountBody,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.confirm != "DELETE":
        raise HTTPException(status_code=400, detail='You must send {"confirm": "DELETE"} to delete your account.')

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_jwt(token)
            blacklist_token(payload.get("jti", ""))
        except Exception:
            pass

    await db.delete(current_user)
    await db.commit()

    response = Response(status_code=204)
    clear_refresh_cookie(response)
    return response


@app.get("/api/account/export")
async def export_account_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = current_user.id

    def _serialize(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid4.__class__):
            return str(obj)
        return str(obj)

    def _row_dict(row):
        mapper = sa_inspect(type(row))
        d = {}
        for col in mapper.columns:
            val = getattr(row, col.key, None)
            if isinstance(val, datetime):
                val = val.isoformat()
            elif hasattr(val, 'hex'):
                val = str(val)
            d[col.key] = val
        return d

    export: dict = {
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "name": current_user.name,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
    }

    tables = [
        ("applications", Application, Application.user_id == uid),
        ("contacts", Contact, Contact.user_id == uid),
        ("emails", EmailEvent, EmailEvent.user_id == uid),
        ("interviews", Interview, Interview.user_id == uid),
        ("company_visits", CompanyVisit, CompanyVisit.user_id == uid),
        ("alerts", Alert, Alert.user_id == uid),
        ("warm_connections", WarmConnection, WarmConnection.user_id == uid),
        ("research_profiles", ResearchProfile, ResearchProfile.user_id == uid),
        ("research_runs", ResearchRun, ResearchRun.user_id == uid),
        ("research_source_items", ResearchSourceItem, ResearchSourceItem.user_id == uid),
        ("opportunity_signals", OpportunitySignal, OpportunitySignal.user_id == uid),
        ("opportunity_scores", OpportunityScore, OpportunityScore.user_id == uid),
        ("opportunity_briefs", OpportunityBrief, OpportunityBrief.user_id == uid),
        ("recommended_actions", RecommendedAction, RecommendedAction.user_id == uid),
        ("research_feedback", ResearchFeedback, ResearchFeedback.user_id == uid),
        ("consents", DataConsent, DataConsent.user_id == uid),
    ]

    for key, model, condition in tables:
        result = await db.execute(select(model).where(condition))
        export[key] = [_row_dict(r) for r in result.scalars().all()]

    import uuid as _uuid
    content = json.dumps(export, default=str, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=apptrail-export-{current_user.email}.json"},
    )
