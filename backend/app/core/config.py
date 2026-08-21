from pydantic_settings import BaseSettings, SettingsConfigDict


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
