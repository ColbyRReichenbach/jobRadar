import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=os.getenv("SQLALCHEMY_ECHO", "false").lower() == "true")

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
async_session_factory = async_session


async def get_db():
    async with async_session() as session:
        yield session
