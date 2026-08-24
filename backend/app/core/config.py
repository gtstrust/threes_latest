from pydantic_settings import BaseSettings, SettingsConfigDict

# The literal values shipped in `.env.example`. They describe the shape of a
# setting rather than name a place, so a config still carrying them is a config
# with no Supabase project behind it. Without this, a fresh `cp .env.example .env`
# would have the app fetching keys from — and broadcasting at — a domain that
# isn't ours. Same idea as `_LOCAL_DB_HOSTS` in tests/conftest.py: name the known
# literals rather than guess at a pattern.
PLACEHOLDER_SETTINGS = frozenset(
    {"https://your-project.supabase.co", "your-service-role-key", "your-jwt-secret"}
)


def is_configured(value: str | None) -> bool:
    """True when a setting holds a real value rather than nothing or a placeholder."""
    return bool(value) and value not in PLACEHOLDER_SETTINGS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_jwt_secret: str | None = None

    # Port 5433, not 5432 — docker-compose publishes Postgres there to avoid clashing
    # with a locally-installed Postgres. Matches .env.example.
    database_url: str = "postgresql+asyncpg://threes:threes@localhost:5433/threes_dev"

    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
