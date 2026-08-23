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

The suite uses its own database, `threes_test`, created automatically on first run — deliberately
not the `threes_dev` database Alembic manages, since tests drop every table and would otherwise
leave your migrated schema empty while `alembic_version` still claimed to be up to date. Point it
elsewhere with `TEST_DATABASE_URL`; it refuses to run against a non-local host.

## End-to-end script

`pytest` drives the app in-process with the schema dropped and rebuilt around every test.
`scripts/demo_tournament.py` does the opposite: it plays a complete corporate golf day over real
HTTP against a running server — six authenticated players, two courses, one tournament, two rounds
of three holes with the groups redrawn in between, every hole scored, and a winner declared.

```bash
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --port 8000        # in another shell

python scripts/demo_tournament.py
```

It checks its own results — every hole's `decided_by` against the strokes it scripted, and the
leaderboards against the score responses it received — printing a checklist and exiting non-zero if
the API disagrees, so it doubles as a smoke test. The twelve hole-cards are scripted to exercise all
three levels of the ADR-007 cascade, including the re-submit that carries a tie-break answer and one
hole nobody wins.

The script signs its own Supabase-shaped JWTs, so it needs `SUPABASE_JWT_SECRET` to hold the same
value the server is using — it reads `--jwt-secret`, then the environment, then `.env`. Everything
else has a working default; see `--help` for `--base-url`, `--seed` and `--quiet`.

It writes to whatever database the server is pointed at, normally `threes_dev`, and **leaves its
data behind** — the API has no DELETE for a tournament or a course. Each run creates its own players
and courses, so runs accumulate rather than collide.

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

Routes → services → repositories → database. Every router is implemented,
there are no stub endpoints left, and every piece of the scoring engine is now
wired to a route. What remains in Phase 1 is the Flutter frontend, plus
Supabase Realtime (M9 in [`../ROADMAP.md`](../ROADMAP.md)) — which only pushes
clients to refetch the leaderboard endpoints below, since ADR-001 keeps the
ranking itself server-side.

## API surface

`GET /health` is open; everything else needs a bearer token. Full
request/response schemas are at http://localhost:8000/docs.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness check (no auth) |
| `GET` | `/auth/me` | Verify a token and echo its claims |
| `POST` | `/players` | Idempotently provision the caller's profile |
| `GET` `PATCH` | `/players/me` | Read or update your own profile |
| `GET` | `/players/{id}` | Read a profile |
| `POST` `GET` | `/courses` | Create or search courses (shared reference data) |
| `GET` `PATCH` | `/courses/{id}` | Read a course with its holes, or rename it |
| `PUT` | `/courses/{id}/holes` | Upsert the holes being played |
| `POST` `GET` | `/tournaments` | Create a tournament, or list your own |
| `GET` `PATCH` | `/tournaments/{id}` | Read or edit tournament details |
| `POST` | `/tournaments/{id}/status` | Registration transitions (ADR-003) |
| `POST` `GET` | `/tournaments/{id}/participants` | Self-register, or read the field |
| `POST` | `/tournaments/{id}/participants/virtual` | Add a Virtual Player (organiser) |
| `DELETE` | `/tournaments/{id}/participants/{pid}` | Remove someone from the field (organiser) |
| `POST` `GET` | `/tournaments/{id}/rounds` | Draw the next round and start play, or list rounds |
| `GET` | `/rounds/{id}` | The draw: every group with its members and loop |
| `POST` | `/rounds/{id}/complete` | Finish the round in progress (organiser) |
| `GET` | `/groups/{id}` | One group, its members and its loop |
| `POST` | `/groups/{id}/holes/{hole_id}/scores` | Enter the group's strokes for a hole |
| `GET` | `/groups/{id}/scores` | The group's card so far |
| `GET` | `/tournaments/{id}/leaderboard` | Cumulative standings across every round |
| `GET` | `/rounds/{id}/leaderboard` | Standings for one round |

Two of these are worth knowing before you call them:

- **`POST /tournaments/{id}/status` will not set `ROUND_IN_PROGRESS` or
  `ROUND_COMPLETE`.** Drawing a round starts play and completing a round ends
  it, so those statuses belong to the round endpoints (ADR-008).
- **Score submission is an idempotent upsert of one hole for the whole
  group.** Re-posting a hole corrects it. If the strokes tie, the response
  names the tied players in `tied_participants` — ask *those* players who was
  closest to the pin, then who hit the longest drive on the fairway, and post
  the hole again with the answer (ADR-007).
