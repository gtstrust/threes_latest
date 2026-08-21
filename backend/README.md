# Threes Backend

FastAPI API for the Threes golf platform. Auth and the database both run through
Supabase: Supabase Auth issues JWTs (magic link, verified here on every request),
and Supabase Postgres is accessed via SQLAlchemy/asyncpg — not the `supabase-py`
client. See [`CLAUDE.md`](../CLAUDE.md) for the full project spec.

## Prerequisites

- Python 3.12+
- Docker + Docker Compose

## Quick Start (Docker)

No Supabase project needed to try this out — it runs against a local Postgres
container with placeholder auth config.

```bash
cd backend
cp .env.example .env
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Stop everything:

```bash
docker compose down        # keep data
docker compose down -v     # also wipe the Postgres volume
```

> **Port note:** the local Postgres container publishes on host port **5433**,
> not 5432, to avoid clashing with any Postgres already running on your
> machine. Inside the Docker network it's still reachable as `postgres:5432`.

## Local Development (without Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # if you haven't already

# Postgres needs to be reachable — either start just the DB via Docker:
docker compose up -d postgres
alembic upgrade head

uvicorn app.main:app --reload --port 8000
```

## Configuration

Copy `.env.example` to `.env` and fill in values. All fields have safe
defaults/placeholders, so the app boots without a real Supabase project —
protected endpoints (anything using `get_current_user`) return `500` until
`SUPABASE_JWT_SECRET` is set to a real value.

| Variable               | Purpose                                                                 |
|-------------------------|--------------------------------------------------------------------------|
| `SUPABASE_URL`          | Your Supabase project URL                                                |
| `SUPABASE_KEY`          | Supabase service-role key                                                |
| `SUPABASE_JWT_SECRET`   | Used to verify Supabase-issued JWTs (HS256) on incoming requests          |
| `DATABASE_URL`          | Async SQLAlchemy connection string (`postgresql+asyncpg://...`)          |
| `ENVIRONMENT`           | `development` / `production`                                             |
| `CORS_ORIGINS`          | Comma-separated list of allowed origins                                  |

**Connecting to a real Supabase project**: once one exists, fill in
`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_JWT_SECRET`, and point
`DATABASE_URL` at Supabase's Postgres connection string. No code changes
required — everything reads from environment variables.

## Database Migrations (Alembic)

Run inside the container (or locally against a reachable Postgres):

```bash
docker compose exec backend alembic upgrade head                       # apply all migrations
docker compose exec backend alembic revision --autogenerate -m "..."   # create a migration
docker compose exec backend alembic downgrade -1                       # rollback last migration
```

New SQLAlchemy models must be imported in `app/models/__init__.py` or
`alembic revision --autogenerate` will silently produce an empty migration.

## Testing

```bash
source .venv/bin/activate
docker compose up -d postgres    # tests need a real Postgres to run against
pytest
pytest --cov=app tests/
```

## Linting & Type Checking

```bash
ruff check .
ruff format .
mypy app/
```

## Authentication

Login itself is **not** proxied through this API — clients authenticate
directly against Supabase Auth (magic link) and receive a JWT. Send it as a
bearer token on every request:

```bash
curl http://localhost:8000/auth/me -H "Authorization: Bearer <supabase-jwt>"
```

`GET /auth/me` verifies the token and returns the claims it carries (no DB
lookup). `POST /players` is the idempotent "ensure my profile exists" call —
invoke it once right after login before calling any other `/players`
endpoint.

## Project Structure

```
app/
├── api/            # Route handlers (routers)
├── core/           # Config, JWT verification, DB engine, shared dependencies
├── models/         # SQLAlchemy ORM models
├── schemas/        # Pydantic request/response schemas
├── services/       # Business logic layer
├── repositories/   # Database access layer
└── main.py         # FastAPI app entry point
migrations/         # Alembic migrations
tests/
```

Routes → services → repositories → database. Only `auth` + `players` are
fully implemented; `tournaments`, `rounds`, `groups`, and `scores` are stub
routers (each returns `501` until built out).
