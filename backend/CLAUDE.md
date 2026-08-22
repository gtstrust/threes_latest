# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is the `backend/` package of the Threes monorepo. See [`../CLAUDE.md`](../CLAUDE.md) for
the full project spec, domain concepts, and ADRs — this file covers backend-specific commands
and implementation details that require reading multiple files to piece together.

## Commands

### Setup & running

```bash
cp .env.example .env                        # safe defaults; app boots without a real Supabase project
docker compose up -d --build                 # full stack: Postgres (host port 5433) + API on :8000
docker compose exec backend alembic upgrade head

# or, without Docker for the app itself:
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres                # still need Postgres reachable
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Tests

Tests require a real Postgres — start it first (`docker compose up -d postgres`). There is no
mocked-DB test path; `tests/conftest.py` creates and drops every table per test.

**The suite runs against its own database, `threes_test`, not the `threes_dev` one Alembic
manages.** This matters: `drop_all` doesn't touch `alembic_version`, so sharing a database would
leave migrations believing they were applied against an empty schema. `conftest.py` creates
`threes_test` on first connect, so there's no setup step. Override with `TEST_DATABASE_URL`; the
suite refuses to start against any non-local host, because it drops everything.

```bash
pytest
pytest --cov=app tests/
pytest tests/test_players.py::test_players_full_slice   # single test
```

### Lint / type-check

```bash
ruff check .
ruff format .
mypy app/     # strict mode is on (pyproject.toml: [tool.mypy] strict = true)
```

### Migrations

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

**New models must be imported in `app/models/__init__.py`** — `autogenerate` diffs against
`Base.metadata`, and a model that isn't imported there never registers, so autogenerate silently
produces an empty migration.

## Architecture

Strict layering, one direction only: **routes (`app/api/`) → services (`app/services/`) →
repositories (`app/repositories/`) → SQLAlchemy models (`app/models/`)**. Routes hold no DB
queries or business logic; repositories hold no business logic, only persistence. Pydantic
schemas (`app/schemas/`) are the request/response contract and are distinct from the SQLAlchemy
models — services convert between them (e.g. `PlayerRead.model_validate(player)`).

Follow the `players` vertical slice (`api/players.py` → `services/player.py` →
`repositories/player.py` → `models/player.py` → `schemas/player.py`) as the template for
implementing any new resource.

### Auth model — read this before touching anything auth-related

Supabase Auth issues JWTs (magic link) directly to the client; **this API never sees a password
and does not proxy login**. Every protected route depends on `CurrentUserDep`
(`app/core/deps.py`), which verifies the bearer token itself via `decode_supabase_jwt`
(`app/core/security.py`) — HS256, shared-secret (`SUPABASE_JWT_SECRET`), no DB lookup. Data
access uses SQLAlchemy/asyncpg against Supabase's Postgres directly, **not** the `supabase-py`
client — the JWT secret is the only piece of Supabase's SDK surface this backend depends on.

`CurrentUser` (id + email) is derived purely from JWT claims. A verified token does **not**
imply a `players` row exists — `id` mirrors `auth.users.id` but the row is created lazily.
`POST /players` is the idempotent "ensure my profile exists" call; the frontend must call it once
right after login before any other `/players` endpoint, or `GET /players/me` / `PATCH
/players/me` will 404. `decode_supabase_jwt` returns 500 (not 401) when `SUPABASE_JWT_SECRET` is
unset — that's a config error, not an auth failure — see `test_security.py` for the distinction.

### Config

`app/core/config.py` (pydantic-settings, reads `.env`) has safe defaults for everything, so the
app boots with no real Supabase project — but any route through `get_current_user` 500s until
`SUPABASE_JWT_SECRET` is a real value. `DATABASE_URL` inside the Docker network points at hostname
`postgres`, not `localhost` (see `docker-compose.yml`) — the compose file overrides the `.env`
value for the `backend` service for this reason.

### Implementation status

Only `auth` and `players` are implemented end-to-end. `tournaments`, `rounds`, `groups`, and
`scores` (`app/api/*.py`) are stub routers that unconditionally return 501. The corresponding
business-logic modules — `services/grouping.py` (ADR-004 group-of-3 algorithm),
`services/scoring.py` (points + countback engine), `services/tournament.py` (ADR-003 state
machine) — are empty files containing only a docstring pointing back to the relevant ADR in the
root `CLAUDE.md`. When implementing one of these, follow the `players` slice's layering rather
than inventing a new pattern.

### Testing pattern

`tests/conftest.py` overrides the `get_db` FastAPI dependency with a per-test session factory
against the real configured database (tables created/dropped per test via `Base.metadata`), and
monkeypatches `settings.supabase_jwt_secret` to a fixed test value. Use the `make_token` fixture
to mint valid Supabase-shaped JWTs for authenticated requests rather than hand-rolling PyJWT
calls in new tests.
