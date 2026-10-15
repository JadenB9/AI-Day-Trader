"""
Async SQLAlchemy database setup.
"""
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from contextlib import asynccontextmanager

from config.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all models"""


# Engine singleton
_engine = None
_session_factory = None


def get_engine():
    """Get or create async engine"""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database.url,
            echo=settings.database.echo,
            pool_pre_ping=True
        )
    return _engine


def get_session_factory():
    """Get or create session factory"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False
        )
    return _session_factory


async def init_db() -> None:
    """Initialize database, create tables"""
    engine = get_engine()
    async with engine.begin() as conn:
        # Import models so they're registered with Base
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections"""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async session context manager"""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
