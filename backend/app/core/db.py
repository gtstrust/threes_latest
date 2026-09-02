import logging
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# Supabase's transaction-mode pooler. Session mode (5432) hands a client one
# backend for the life of the connection; transaction mode hands out a different
# one per transaction, which is what breaks prepared statements below.
TRANSACTION_POOLER_PORT = 6543


def asyncpg_connect_args(url: str) -> dict[str, Any]:
    """The asyncpg settings this URL needs, which is usually none at all.

    Behind a transaction-mode pooler, a statement prepared on one backend is
    executed on another that has never heard of it — `InvalidSQLStatementNameError`,
    intermittently, under exactly the load an event produces. Turning both
    statement caches off and naming each statement uniquely is what survives it.

    `docs/DEPLOYMENT.md` §1 asks for the session pooler on 5432 precisely so none
    of this is needed, and that is still the right string to deploy: prepared
    statements are a real saving. But that is one hand-typed secret standing
    between a wrong port and an outage mid-round, so a wrong port costs speed here
    rather than the day.

    Returns:
        Keyword arguments for `create_async_engine`'s `connect_args` — empty for
        any connection that keeps its backend.
    """
    try:
        port = make_url(url).port
    except ArgumentError:
        # Not a URL SQLAlchemy can parse. It is about to fail on its own terms,
        # with a better message than anything guessed here.
        return {}

    if port != TRANSACTION_POOLER_PORT:
        return {}

    logger.warning(
        "DATABASE_URL is on port %d, the transaction-mode pooler. Prepared "
        "statements are disabled to survive it; prefer the session pooler on "
        "5432 (docs/DEPLOYMENT.md section 1).",
        TRANSACTION_POOLER_PORT,
    )
    return {
        # asyncpg's own cache of prepared statements.
        "statement_cache_size": 0,
        # The SQLAlchemy adapter's cache in front of it.
        "prepared_statement_cache_size": 0,
        # asyncpg numbers statements sequentially, so two backends behind one
        # pooler both reach for `__asyncpg_stmt_1__`. Unique names mean a
        # collision cannot happen even for a single-use statement.
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Build the process-wide engine on first use.

    Deliberately lazy: creating this at import time makes the whole app — and the
    test suite, which only wants `get_db` to override it — fail to import whenever
    DATABASE_URL names a driver that isn't installed.
    """
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=False,
        connect_args=asyncpg_connect_args(settings.database_url),
    )


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
