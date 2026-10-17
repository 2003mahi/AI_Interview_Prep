import os
from fastapi import Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from .config import Settings
from .models.document import Document

settings = Settings()

# Async DB engine using asyncpg
engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

@asynccontextmanager
async def get_db() -> AsyncSession:
    """Provide a transactional async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_user_id(x_api_key: str = Header(...)) -> str:
    """Validate API key and return associated user_id."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT user_id FROM users WHERE api_key = :key"),
            {"key": x_api_key}
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return row[0]
