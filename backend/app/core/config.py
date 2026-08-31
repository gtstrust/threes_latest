import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# The literal values shipped in `.env.example`. They describe the shape of a
# setting rather than name a place, so a config still carrying them is a config
# with no Supabase project behind it. Without this, a fresh `cp .env.example .env`
# would have the app fetching keys from — and broadcasting at — a domain that
# isn't ours. Same idea as `_LOCAL_DB_HOSTS` in tests/conftest.py: name the known
# literals rather than guess at a pattern.
PLACEHOLDER_SETTINGS = frozenset(
    {
        "https://your-project.supabase.co",
        "your-service-role-key",
        "your-jwt-secret",
        "re_your_resend_key",
        "Threes <noreply@your-domain.com>",
        "your-cron-secret",
    }
)


# The URL schemes that name Postgres without naming a driver. SQLAlchemy resolves
# these to psycopg2, which this project has never depended on — see the validator
# on `database_url` below.
BARE_POSTGRES_SCHEMES = ("postgresql://", "postgres://")


def is_configured(value: str | None) -> bool:
    """True when a setting holds a real value rather than nothing or a placeholder."""
    return bool(value) and value not in PLACEHOLDER_SETTINGS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_jwt_secret: str | None = None

    # Outbound email. Both are needed before anything sends; either missing or
    # still holding its placeholder means the app runs with a NullMailer, which
    # is what keeps a fresh checkout from mailing anybody.
    resend_api_key: str | None = None
    email_from: str | None = None

    # Shared secret for the reminder sweep, which is called by a scheduler rather
    # than a person. Unset means the endpoint refuses everything — an unguarded
    # route that mails an entire field is not a safe default, so "not configured"
    # has to mean closed rather than open.
    cron_secret: str | None = None

    # Where the app lives, for links inside emails. Defaults to the dev server
    # because that is where it lives while nobody has deployed it; production
    # sets it to the real origin. A wrong value here produces mail whose links go
    # somewhere nobody can reach, which is worse than mail that doesn't send.
    app_url: str = "http://localhost:5173"

    # Port 5433, not 5432 — docker-compose publishes Postgres there to avoid clashing
    # with a locally-installed Postgres. Matches .env.example.
    database_url: str = "postgresql+asyncpg://threes:threes@localhost:5433/threes_dev"

    # 5173 is Vite's dev server, which is where `frontend/` runs (ADR-006). The
    # browser blocks the app's very first request without it, and the failure
    # reads as a network error rather than as a CORS one, so it is worth having
    # in the default rather than in everyone's .env.
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg(cls, value: str) -> str:
        """Name the asyncpg driver when the URL does not name one at all.

        asyncpg is the only driver this project installs, so a bare
        `postgresql://` can only mean that one. SQLAlchemy resolves it to psycopg2
        instead, and the resulting `ModuleNotFoundError: No module named
        'psycopg2'` names a package that appears nowhere here — raised from inside
        the dialect registry, several frames from anything the reader wrote.
        Supabase hands out bare URLs, so pasting one is the expected path rather
        than a slip, and worth repairing rather than rejecting.

        It still warns. A config that is not the shape this file documents should
        leave a trace in the deploy log instead of being silently corrected. The
        URL itself never goes in the message: it carries the database password.

        Any other explicit driver is left alone. Rewriting `postgresql+psycopg://`
        would be guessing at intent, and a driver asked for by name fails clearly
        enough on its own.
        """
        for scheme in BARE_POSTGRES_SCHEMES:
            if value.startswith(scheme):
                logger.warning(
                    "DATABASE_URL names no driver; using asyncpg. "
                    "Prefer postgresql+asyncpg:// explicitly."
                )
                return f"postgresql+asyncpg://{value[len(scheme) :]}"
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def supabase_jwks_url(self) -> str | None:
        """Where the project publishes its JWT signing keys, or None if there is none.

        Derived rather than configured separately: it is always this path under
        the project URL, and a second env var would only be a way for the two to
        disagree.
        """
        if not is_configured(self.supabase_url):
            return None
        assert self.supabase_url is not None  # narrowed by is_configured
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


settings = Settings()
