"""The DATABASE_URL driver coercion — pure, so checkable without a session.

Only asyncpg is installed, so a URL naming no driver at all can only mean that
one. SQLAlchemy's default for a bare `postgresql://` is psycopg2, and the
`ModuleNotFoundError` it raises names a package this project has never depended
on — which is why a real deploy spent four releases on it.
"""

import logging

from app.core.config import Settings

# What the Supabase dashboard hands out, with a password whose characters would
# be mangled if the URL were parsed and rebuilt. The rewrite must be a prefix
# swap and nothing more.
SUPABASE_STYLE = (
    "postgres.asrijzarthrqgyuujigw:p%40ss%3Aword"
    "@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"
)


def test_a_bare_postgresql_url_gets_the_asyncpg_driver():
    settings = Settings(database_url=f"postgresql://{SUPABASE_STYLE}")
    assert settings.database_url == f"postgresql+asyncpg://{SUPABASE_STYLE}"


def test_the_postgres_alias_is_treated_the_same():
    settings = Settings(database_url=f"postgres://{SUPABASE_STYLE}")
    assert settings.database_url == f"postgresql+asyncpg://{SUPABASE_STYLE}"


def test_a_url_that_already_names_asyncpg_is_untouched():
    url = f"postgresql+asyncpg://{SUPABASE_STYLE}"
    assert Settings(database_url=url).database_url == url


def test_a_driver_asked_for_by_name_is_left_alone():
    """Rewriting this would be guessing at intent; it fails clearly on its own."""
    url = f"postgresql+psycopg://{SUPABASE_STYLE}"
    assert Settings(database_url=url).database_url == url


def test_the_rewrite_warns_without_leaking_the_password(caplog):
    """The trace in the deploy log is half the decision — and must not carry the URL."""
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        Settings(database_url=f"postgresql://{SUPABASE_STYLE}")

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "asyncpg" in message
    assert "p%40ss%3Aword" not in message
    assert "pooler.supabase.com" not in message


def test_a_correct_url_says_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        Settings(database_url=f"postgresql+asyncpg://{SUPABASE_STYLE}")

    assert caplog.records == []
