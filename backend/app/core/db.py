from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Build the process-wide engine on first use.

    Deliberately lazy: creating this at import time makes the whole app — and the
    test suite, which only wants `get_db` to override it — fail to import whenever
    DATABASE_URL names a driver that isn't installed.
    """
    return create_async_engine(settings.database_url, pool_pre_ping=True, echo=False)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
