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
pytest tests/test_scoring.py                            # one file
pytest tests/test_scoring.py::test_only_the_winner_scores   # one test
pytest -k "loop"                                        # by name
```

Note that **even the pure unit tests need Postgres up**: `conftest.py` connects at import time
(module level) to create `threes_test` if it's missing, so `pytest tests/test_scoring.py` fails
without a database despite `scoring.py` never touching one.

### Lint / type-check

```bash
ruff check .
ruff format .
mypy app/     # strict mode is on (pyproject.toml: [tool.mypy] strict = true)
```

CI additionally runs `ruff format --check .` and `alembic upgrade head`, so an unformatted file
or a migration that won't apply fails the build even though `pytest` passes locally.

The local `.venv` here is **Python 3.14**, but `requires-python` is `>=3.12`, mypy targets 3.12,
and CI pins 3.12. `mypy app/` is what catches 3.13+-only syntax before CI does — running it is
not optional.

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
`repositories/player.py` → `models/player.py` → `schemas/player.py`) as the minimal template for
a new resource; `rounds` is the fuller one, showing domain errors, authorization guards, and a
service that coordinates several repositories.

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

`auth`, `players`, `courses`, `tournaments`, `participants`, `rounds` and `groups` are all
implemented end-to-end. **`app/api/scores.py` is the only remaining stub** — it returns 501, and
there is no `HoleScore` model or score persistence behind it.

`services/scoring.py` is fully written and exhaustively unit-tested but **has no caller yet**:
nothing invokes `score_hole` or `rank_leaderboard` outside `tests/test_scoring.py`. Wiring it up
(a `HoleScore` model, a migration, a scores service, and a leaderboard endpoint) is the next
slice — M7/M8 in `../ROADMAP.md`. Follow the `rounds` slice as the template; it's the most recent
and the most complete example of the layering.

### The pure core

Two modules are deliberately pure — synchronous, no session, no I/O, plain data in and out — so
the platform's most critical logic is testable without fixtures:

- `services/scoring.py` — the ADR-007 cascade (`score_hole`) and `rank_leaderboard`.
- `services/grouping.py` — `group_sizes` / `build_groups` / `build_loops` / `allocate_loops`.

Keep them that way. Anything needing a database belongs in the calling service.

Two consequences worth knowing before changing them:

- **`build_groups` is deterministic and order-preserving.** That's what makes exact-grouping
  assertions possible in tests. The randomness lives in `RoundService.draw_round`, which shuffles
  the participant list before calling it for round 2 onwards (round 1 stays in registration order
  so people play with whoever they signed up alongside).
- **`group_sizes` never returns a group of 1.** A remainder of one trades a three for two pairs,
  so 4 players is 2+2 and 7 is 3+2+2 — not 3+1 or 3+3+1.

### Domain errors and how routes map them

Each service defines its own exception hierarchy rooted at a `*Error` base
(`TournamentError`, `CourseError`, `ParticipantError`, `RoundError`) and **raises rather than
returning status codes**; the router catches each and maps it to an `HTTPException`. Services
never import `fastapi`. When adding a rule, add an exception type next to its siblings and map it
in the route — don't reach for `HTTPException` from inside a service.

A recurring one: every service that writes a row foreign-keyed to `players` first checks the
caller's profile exists (`OrganiserProfileMissing`, `CreatorProfileMissing`,
`PlayerProfileMissing`). The row is created lazily by `POST /players`, so without the check this
surfaces as a raw integrity error.

### Authorization

Beyond "holds a valid JWT", three guards in `app/core/deps.py` carry all of it:

- `require_course_owner` — courses are shared reference data, readable by anyone authenticated,
  editable only by whoever created them.
- `require_organiser` — anything that changes a tournament, its field, or its rounds.
- `require_can_view` — reading a tournament: the organiser, or anyone in the field. Async, unlike
  the other two, because it has to look the caller up in the participant list.

These are plain functions, not FastAPI dependencies — the route fetches the tournament/course
first (via its local `_get_or_404` helper) and then calls the guard.

### Where the tournament lifecycle actually lives

Splitting ADR-003 across two files is intentional and easy to get wrong:

- `services/tournament.py` owns `ALLOWED_TRANSITIONS` and the registration transitions plus
  `ROUND_COMPLETE → TOURNAMENT_COMPLETE`, via `POST /tournaments/{id}/status`.
- `services/round.py` owns the two *play* statuses. `ROUND_IN_PROGRESS` and `ROUND_COMPLETE`
  cannot be set through the status endpoint at all — `_reject_round_driven` refuses them with a
  pointer to the right endpoint (ADR-008). Drawing a round starts play; completing a round ends
  it.

Because of that, **preconditions for starting play belong in `RoundService.draw_round`, not in
`TournamentService.transition`** — a check placed on the status endpoint can never fire, since
the target is rejected before it's reached. The "no course set" check moved for exactly this
reason.

### Testing pattern

`tests/conftest.py` overrides the `get_db` FastAPI dependency with a per-test session factory
against the real configured database (tables created/dropped per test via `Base.metadata`), and
monkeypatches `settings.supabase_jwt_secret` to a fixed test value. Use the `make_token` fixture
to mint valid Supabase-shaped JWTs for authenticated requests rather than hand-rolling PyJWT
calls in new tests.
