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
(`app/core/security.py`) — no DB lookup. Data
access uses SQLAlchemy/asyncpg against Supabase's Postgres directly, **not** the `supabase-py`
client — the JWT secret is the only piece of Supabase's SDK surface this backend depends on.

`CurrentUser` (id + email) is derived purely from JWT claims. A verified token does **not**
imply a `players` row exists — `id` mirrors `auth.users.id` but the row is created lazily.
`POST /players` is the idempotent "ensure my profile exists" call; the frontend must call it once
right after login before any other `/players` endpoint, or `GET /players/me` / `PATCH
/players/me` will 404.

**Two verification paths, chosen by the token itself.** A real project signs with **ES256** and
publishes the public key at its JWKS endpoint, so a browser's magic-link token is verified against
that. But `tests/conftest.py` and `scripts/demo_tournament.py` sign their own **HS256** tokens
against `SUPABASE_JWT_SECRET`, because Supabase issues tokens straight to clients and there is no
login endpoint here to call. An asymmetric token carries a `kid` naming its signing key and a
shared-secret one does not, which is what `decode_supabase_jwt` branches on. Neither path is
legacy — deleting the HS256 one takes the test suite and the demo script with it.

**This project is ES256-only.** Verified by minting a real token through the Auth admin API: the
header is `{"alg": "ES256", "kid": "505bee7a-…"}`, and the legacy HS256 secret cannot verify it
(`InvalidAlgorithmError` — it is not an HS256 token at all). So `SUPABASE_JWT_SECRET` here is **not**
a Supabase value and must not be set to one: it is a locally-generated random string, used only by
the tests and the demo script. Keeping a production credential out of the HS256 branch means that
even if it leaks, it cannot mint a token this server accepts — confirmed by feeding the leaked
legacy secret's forgery to `GET /auth/me` and getting a 401.

The JWKS is cached by `kid` for `JWKS_CACHE_TTL_SECONDS`, behind an `asyncio.Lock` so a cold cache
under load fetches once. An unknown `kid` forces a refetch, which is how a key rotation recovers
without waiting out the TTL. **Not `jwt.PyJWKClient`** — it fetches with blocking `urllib`, which
inside an async request stalls the entire event loop rather than just that caller.

Three status codes worth keeping straight, all in `test_security.py`: **401** for a bad, expired or
unknown-key token; **500** when `SUPABASE_JWT_SECRET` is unset and there is no project either — a
config error, not an auth failure; and **503** when the JWKS endpoint is unreachable, because the
caller's token may be perfectly good and answering 401 would send them off to log in again over an
outage that has nothing to do with them.

### Config

`app/core/config.py` (pydantic-settings, reads `.env`) has safe defaults for everything, so the
app boots with no real Supabase project — but any route through `get_current_user` 500s until
`SUPABASE_JWT_SECRET` is a real value. `DATABASE_URL` inside the Docker network points at hostname
`postgres`, not `localhost` (see `docker-compose.yml`) — the compose file overrides the `.env`
value for the `backend` service for this reason.

### Implementation status

Every router is implemented — **no 501 stubs remain** — and every part of the scoring engine has a
caller. M9 (Supabase Realtime) is done and verified against the real project. Phase 1 and Phase 2
are both code-complete.

`../ROADMAP.md` is the source of truth for what is built; this file does not restate it, because the
two copies drifted apart once already.

Follow the `rounds` or `scores` slice as the template — both show the layering in full.

### The leaderboard

`services/leaderboard.py` is thin on purpose: `rank_leaderboard` orders, `ScoreRepository`
sums, and the service supplies the one thing neither can know — **who belongs on the board**.

- **The field is established first, then the aggregate is merged onto it.** A bare
  `SUM(points) GROUP BY participant_id` returns only players who have already scored, which
  early in a day is almost nobody. Everyone drawn is listed, on nothing until they score.
- **Registration order is load-bearing.** `rank_leaderboard`'s sort is stable, so players level
  on both points and strokes come out in input order. `list_for_tournament` orders by
  `created_at`; feeding the aggregate's mapping order instead would leave tied players
  shuffling between polls.
- **A round's field comes from its draw**, not from the tournament's participants. Identical
  today, but knockout progression would make a later round a subset — and the board would then
  quietly list eliminated players.

`totals_for_tournament` / `totals_for_round` on `ScoreRepository` are the only aggregate queries
in the codebase. `hole_scores` has no `tournament_id`, so both reach one via
`groups → rounds`. Don't copy `ParticipantRepository.count_for_tournament`, which fetches rows
and calls `len()`; ADR-009 stores points precisely so this read path stays a real SQL aggregate.

### The pure core

Two modules are deliberately pure — synchronous, no session, no I/O, plain data in and out — so
the platform's most critical logic is testable without fixtures:

- `services/scoring.py` — the ADR-007 cascade (`score_hole`) and `rank_leaderboard`.
- `services/grouping.py` — `group_sizes` / `build_groups` / `build_loops` / `allocate_loops`.

Keep them that way. Anything needing a database belongs in the calling service — for scoring
that's `services/score_entry.py`, named to sit a clear distance from `scoring.py` rather than one
letter away. `score_entry` decides *which* strokes may reach the engine and what happens to the
answer; `scoring` decides who won.

Two consequences worth knowing before changing them:

- **`build_groups` is deterministic and order-preserving.** That's what makes exact-grouping
  assertions possible in tests. The randomness lives in `RoundService.draw_round`, which shuffles
  the participant list before calling it for round 2 onwards (round 1 stays in registration order
  so people play with whoever they signed up alongside).
- **`group_sizes` never returns a group of 1.** A remainder of one is folded into a **four**, so 4
  players is one fourball and 7 is 3+4 — not 3+1, and no longer 2+2 or 3+2+2. A remainder of two is
  still a pair. Three constants now, and the distinction matters: `TARGET_GROUP_SIZE` (3) is what
  the arithmetic divides by, while `MAX_GROUP_SIZE` (4) only ever appears as the remainder case.
  Dividing by `MAX_GROUP_SIZE` would turn the whole field into fourballs and quietly stop the
  platform being about threes.
- **`build_loops` chunks whatever holes it is given**, which since the draw learned `hole_numbers`
  is not always the whole course. `RoundService._select_holes` narrows and sorts them first; the
  pure function is unchanged and still assumes playing order.

### Scoring: the two tables, and one deliberate import

**`hole_scores` (reported) and `hole_results` (derived) are split for the reasons in ADR-009** —
read that before changing either. What matters when working in this code: both are always written
together by `ScoreEntryService`, and re-submitting a hole rewrites both. That single upsert path is
how a mis-key is corrected *and* how a tie-break answer arrives, since ADR-007 only asks the
question once a tie appears; a submission that ties reports `tied_participants` so the client knows
which players to ask. Never write one table without the other.

The three check constraints on `hole_results` are not belt-and-braces — they are the enforcement
point for ADR-007's "nothing is recorded unless it decided a hole" and "holes are never halved".
Service-level validation is the convenience; the constraints are the guarantee.

`app/models/score.py` imports `DecidedBy` from `app/services/scoring.py` — the one place a model
reaches into the service layer. It is deliberate: `DecidedBy` is part of `score_hole`'s return
contract, and a second copy in the model layer is how the database labels quietly drift from what
the engine returns. `scoring.py` imports nothing from `app.*`, which is what keeps this from being
a cycle — **don't add a models import there**.

`DecidedBy` is also the first enum whose values differ from its member names (`STROKES` vs
`"strokes"`). SQLAlchemy persists the *name* by default, so the column passes `values_callable` to
store the lowercase value instead, keeping the database label, the API response and ADR-007's
vocabulary identical.

### The Supabase database, and why every table has RLS on

`DATABASE_URL` can point at either the local Docker Postgres or the Supabase project; the app does
not care, but two things about Supabase do not apply locally:

- **`public` is served to the internet.** Supabase exposes it through PostgREST, and the key that
  reaches it is the *publishable* one the frontend ships to every browser. A table created by
  Alembic has RLS **off** and inherits grants for `anon`/`authenticated`, so without intervention
  all twelve tables are readable and writable by anyone who reads the site's JavaScript. Migration
  `20260824_0006` enables RLS on every table and defines **no policies**: PostgREST matches nothing
  and sees nothing, while the app connects as the tables' owner and bypasses RLS untouched.
  This is not the RLS ADR-010 rejected — that was a *policy* restating `require_can_view` in SQL.
  A blanket deny encodes no rule, so there is nothing to drift.
  **A table added after `0006` has to enable RLS itself** — `0006` is a snapshot, not a rule. The
  twelfth table, `tournament_reminders`, does so in its own migration (`20260829_0013`). Any new
  table must do the same, or it ships readable to the internet.
- **Alembic's own table was the gap.** `alembic_version` is created by Alembic, not by our models,
  so `0006` missed it — and `anon` could not merely read it but **UPDATE** it, which corrupts every
  future migration while touching no tournament data. `20260824_0007` revokes the grants outright
  (RLS restricts rows; here the wanted answer is no access at all) and enables RLS as a backstop.
  Both statements are guarded by a `pg_roles` check so the migration still runs on a plain Postgres
  that has no `anon` role.

**The direct connection host is IPv6-only.** `db.<ref>.supabase.co` publishes no A record, so any
network without IPv6 must use the pooler string from the dashboard instead. CI is the obvious place
this bites.

**Which pooler matters.** Session mode (5432) gives a client one backend for the life of the
connection, so asyncpg's prepared statements are still there next time. Transaction mode (6543)
hands out a different backend per transaction and they are not — `InvalidSQLStatementNameError`,
intermittently, on whichever routes happen to have cached a statement. `asyncpg_connect_args`
(`app/core/db.py`) recognises 6543 and disables both statement caches with uniquely-named
statements, warning as it does. `docs/DEPLOYMENT.md` §1 still asks for session mode; this is the net
under it, and it is there because the ask was already written down and still got missed.

**Do not point `scripts/demo_tournament.py` at a server wired to Supabase.** It writes a full
tournament and there is no DELETE for a tournament or a course, so the data stays. The test suite is
safe by construction: `conftest.py` refuses any non-local `TEST_DATABASE_URL`.

### Realtime — the one outbound call

`services/realtime.py` is the only place this backend talks *out* to a third party. It sends a
contentless "the leaderboard moved" broadcast; ADR-010 in `../CLAUDE.md` has the reasoning, and
three things about it are easy to break:

- **It is scheduled, not awaited.** `app/api/scores.py` uses FastAPI `BackgroundTasks`, because
  `get_db` commits in its dependency exit code and FastAPI runs that *before* background tasks.
  Awaiting the broadcast in the route or the service would send it mid-transaction, and a client
  fast enough to act would refetch a board missing the hole that triggered it.
  `test_the_signal_fires_only_after_the_score_is_visible` pins the ordering by counting rows on a
  separate connection — it fails with `0 == 3` if the call is moved inline.
- **It is off unless Supabase is really configured.** `build_notifier()` returns `NullNotifier`
  when `SUPABASE_URL`/`SUPABASE_KEY` are unset *or still hold the `.env.example` placeholders*.
  The placeholder check is not cosmetic: without it, `cp .env.example .env` has the app POSTing to
  `your-project.supabase.co` after every hole.
- **The test suite must never emit.** `conftest.py`'s `client` fixture installs `NullNotifier` for
  every test; the `notifier` fixture swaps in a recorder for the ones that assert on signals.
  Without that default the notifier is built from your real `.env`, and the shared `httpx` client —
  created in one test's event loop, reused in the next — dies with "Event loop is closed".

The payload is `{"tournament_id", "round_id"}` and must stay that way. Adding scores to it would
route data around FastAPI and re-open the authorization question ADR-010 exists to close.

### Why an unhandled 500 looks like a CORS error

Starlette's stack is `ServerErrorMiddleware` → user middleware → `ExceptionMiddleware` → routes. An
exception nothing catches travels up *past* `CORSMiddleware`, and the 500 that
`ServerErrorMiddleware` writes never passes back down through the `send` wrapper that adds
`Access-Control-Allow-Origin`. The browser then reports a CORS failure for a request whose CORS
configuration is fine, and sends the reader to audit the wrong thing.

`app/core/errors.py` answers inside CORS instead, and `app/main.py` adds it **before**
`CORSMiddleware` — `add_middleware` inserts at the front, so the last one added is the outermost.
Two things about it are easy to undo:

- **`@app.exception_handler(Exception)` is not the same fix.** Starlette special-cases the
  `Exception` and `500` keys and installs them on `ServerErrorMiddleware`, i.e. back outside CORS.
- **It is a pure ASGI middleware, not a `BaseHTTPMiddleware`.** ADR-010 depends on `BackgroundTasks`
  running after `get_db` commits, and there is no reason to put a streaming wrapper in that path.

Because the exception is caught, uvicorn never sees it and never logs it — `logger.exception` in the
middleware is the only record, and `logging.basicConfig` in `main.py` is what gets it to stdout at
all (uvicorn adds no root handler). `tests/test_errors.py` pins the order and the log.

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

Beyond "holds a valid JWT", five guards in `app/core/deps.py` carry all of it:

- `require_course_owner` — courses are shared reference data, readable by anyone authenticated,
  editable only by whoever created them.
- `require_organiser` — anything that changes a tournament, its field, or its rounds.
- `require_can_view` — reading a tournament: the organiser, or anyone in the field. Async, unlike
  the first two, because it has to look the caller up in the participant list.
- `require_group_member` — entering a score: someone in that group, or the organiser. Async, for the
  same reason.
- `reject_fun_round` — not authorization so much as visibility. A fun round is a `tournaments` row
  with `kind = FUN_ROUND`, so the tournament-management routes would otherwise happily operate on
  one. It raises **404**, not 403: to a caller on `/tournaments/{id}`, a fun round does not exist.

These are plain functions, not FastAPI dependencies — the route fetches the tournament/course
first (via its local `_get_or_404` helper) and then calls the guard.

### The Phase 2 surface

Five slices landed after the sections above were written. They follow the same layering, so the
notes here are only what is surprising about each.

- **Fun rounds** — `api/fun_rounds.py`, `services/fun_round.py`. A fun round *is* a tournament row
  (`kind = FUN_ROUND`), which is why it inherits the draw, the cascade and the leaderboard without a
  second implementation. The separation is `reject_fun_round` on the tournament routes; see
  "Authorization" above.
- **Join and referral codes** — `api/join.py`, `services/join_code.py`. `join_code.py` is pure and
  synchronous, alongside `scoring.py` and `grouping.py`, and is tested exhaustively for that reason.
  Uniqueness is the database's job: `generate_code` draws from `secrets` and the caller retries
  against the unique constraint, because guaranteeing it in the function would mean a read before
  every write and still race.
- **Reminders and mail** — `services/reminders.py`, `services/mail.py`, `repositories/reminder.py`.
  `build_mailer()` mirrors `build_notifier()`: it returns a `NullMailer` unless both
  `RESEND_API_KEY` and `EMAIL_FROM` are really configured, so local runs and the suite send nothing.
  A failed send is survivable by design — `tests/conftest.py` ships a `FailingMailer` to prove it.
- **`/internal`** — `api/internal.py`, the cron entry point for the reminder sweep. Auth is an
  `X-Cron-Key` header compared with `secrets.compare_digest`, not a JWT. **An unconfigured
  `CRON_SECRET` gives 404, not 503** — an internal route should not advertise that it exists — and a
  wrong key gives 403. Driven by the manual `reminder-sweep.yml` workflow; its hourly cron is
  commented out.
- **Player caps and stats** — `max_players` is nullable on `tournaments` (absent means uncapped, not
  zero). Stats live in `services/stats.py` behind `/players/me/stats` and
  `/players/me/stats/courses`.

### Scripts

`scripts/` is not part of the app and is not imported by it:

- `dev_token.py --email you@example.com` mints an HS256 token for Swagger. The `HTTPBearer`
  description points at it, so this is the documented way in.
- `check_db_url.py --connect` is the deploy pre-flight: it checks a `DATABASE_URL` before Fly does.
  Worth running against the pooler string, which is the part that usually goes wrong.
- `demo_tournament.py` writes a full tournament through the API. **Do not point it at a server wired
  to Supabase** — there is no DELETE for a tournament or a course, so the data stays.

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
