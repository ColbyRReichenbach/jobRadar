import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_URL_LOWER = (DATABASE_URL or "").lower()

engine_kwargs: dict[str, object] = {
    "echo": os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true",
}

if DATABASE_URL_LOWER and not DATABASE_URL_LOWER.startswith("sqlite"):
    engine_kwargs.update(
        pool_pre_ping=True,
        pool_use_lifo=True,
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30")),
    )

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
async_session_factory = async_session


async def get_db():
    async with async_session() as session:
        yield session
