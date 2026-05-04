import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Set test env vars before importing app.
# DATABASE_URL must be force-set (not setdefault) because it may already exist
# as a shell env var pointing to the real Supabase database. If that leaks
# through, asyncpg tries to connect at import time and hangs the test suite.
os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ.setdefault("APPTRAIL_API_KEY", "test-api-key-for-testing")
os.environ.setdefault("APPTRAIL_GMAIL_TOKEN_ENCRYPTION_KEY", "9gesi-IgHlO6wRffB63j5cbQhIXnGGCKuxr0IFnAcaM=")
os.environ.setdefault("SOURCE_LINK_ENCRYPTION_KEY", "9gesi-IgHlO6wRffB63j5cbQhIXnGGCKuxr0IFnAcaM=")
os.environ.setdefault("SOURCE_LINK_ENCRYPTION_KEY_VERSION", "test-v1")
os.environ.setdefault("SOURCE_LINK_HASH_KEY", "test-source-link-hash-key")
os.environ.setdefault("SOURCE_LINK_HASH_KEY_VERSION", "test-v1")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("APPTRAIL_ADMIN_EMAILS", "test-user@apptrail.test")

from backend.database import get_db
from backend.dependencies import create_jwt
from backend.main import app, limiter
from backend.models import Base, User

TEST_API_KEY = os.environ["APPTRAIL_API_KEY"]
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_EMAIL = "test-user@apptrail.test"
AUTH_HEADER = {"Authorization": f"Bearer {create_jwt(str(TEST_USER_ID), TEST_USER_EMAIL, 'Test User')}"}
API_KEY_HEADER = {"Authorization": f"Bearer {TEST_API_KEY}"}


def make_auth_header(user_id: uuid.UUID, email: str = "user@apptrail.test", name: str = "Test User") -> dict[str, str]:
    token = create_jwt(str(user_id), email, name)
    return {"Authorization": f"Bearer {token}"}


_USER_SCOPED_MODELS = {
    "Application",
    "Contact",
    "EmailEvent",
    "UserProfile",
    "WarmConnection",
    "Interview",
    "CompanyVisit",
    "NotificationPreference",
    "ResumeDraft",
    "Alert",
    "ResearchProfile",
    "ResearchRun",
    "ResearchRunStep",
    "ResearchReport",
    "ResearchEvidenceItem",
    "ResearchSourceItem",
    "OpportunitySignal",
    "OpportunityScore",
    "OpportunityBrief",
    "RecommendedAction",
    "ResearchFeedback",
    "SearchDocument",
    "CopilotConversation",
    "CopilotMessage",
    "CopilotFeedback",
    "AiExperimentAssignment",
    "AiFeedbackRewardEvent",
    "AiShadowRun",
    "AiModelCall",
    "AiSafetyDecision",
    "AiArtifact",
    "EmailSyncAudit",
    "ApplicationSuggestionDecision",
    "InterviewSuggestionDecision",
    "UserApplicationLink",
    "SourceDiscoveryEvent",
    "ApplicationSourceLink",
    "JobSearchProviderUsage",
}


@event.listens_for(AsyncSession.sync_session_class, "before_flush")
def _assign_default_test_user_id(session, flush_context, instances):
    for obj in session.new:
        if obj.__class__.__name__ in _USER_SCOPED_MODELS and getattr(obj, "user_id", None) is None:
            obj.user_id = TEST_USER_ID


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            User(
                id=TEST_USER_ID,
                google_id="test-google-id",
                email=TEST_USER_EMAIL,
                name="Test User",
                is_admin=True,
            )
        )
        await session.commit()
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    storage = limiter._storage
    if hasattr(storage, "reset"):
        storage.reset()
    from backend.services.ai_safety import reset_ai_rate_limits_for_tests

    reset_ai_rate_limits_for_tests()
