import asyncio
import os
import uuid
from collections.abc import AsyncGenerator

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.models.base import Base

TEST_JWT_SECRET = "dev-local-only-secret-change-me!"

# A database of its own — NOT settings.database_url, and NOT the threes_dev
# database Alembic manages. Two reasons:
#   1. .env normally points at a real Supabase project, and the `engine` fixture
#      below runs drop_all.
#   2. Sharing threes_dev with Alembic means running the suite wipes every table
#      while leaving alembic_version behind, so migrations then believe they're
#      applied against an empty database.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://threes:threes@localhost:5433/threes_test",
)

# Hostnames we accept as "a database it is safe to drop every table in".
_LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres"})


def _assert_safe_to_drop(url: str) -> None:
    """Abort the run if the test database isn't local.

    The `engine` fixture calls Base.metadata.drop_all. Pointed at a hosted database
    that silently destroys real data, so this refuses to run anywhere but localhost
    or the docker-compose `postgres` service.
    """
    host = make_url(url).host
    if host not in _LOCAL_DB_HOSTS:
        pytest.exit(
            f"Refusing to run tests against non-local database host {host!r}. "
            "The suite drops every table. Set TEST_DATABASE_URL to a local database.",
            returncode=1,
        )


async def _create_test_database_if_missing(url: str) -> None:
    """Create the test database on first run.

    The docker-compose postgres container only creates threes_dev, and its volume
    persists, so an init script would only fire for people who wipe it. Creating
    the database here means the suite works from a clean checkout with no extra
    setup step.
    """
    target = make_url(url)
    async_engine = create_async_engine(
        target.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with async_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                # Identifier can't be bound as a parameter; it comes from our own
                # config rather than user input.
                await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        await async_engine.dispose()


_assert_safe_to_drop(TEST_DATABASE_URL)
asyncio.run(_create_test_database_if_missing(TEST_DATABASE_URL))


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(engine, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_JWT_SECRET)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def make_token():
    def _make_token(subject: str | None = None, email: str = "test@example.com") -> str:
        return jwt.encode(
            {"sub": subject or str(uuid.uuid4()), "email": email, "aud": "authenticated"},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )

    return _make_token
