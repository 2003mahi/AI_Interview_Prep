import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from ..config import settings

# Async engine using asyncpg driver
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

# Session factory
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# Dependency to get a DB session
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
