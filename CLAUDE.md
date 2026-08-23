# CLAUDE.md — Threes Golf Platform

## Project Overview

Threes is a short-form competitive golf platform where players compete over 3-hole loops instead of traditional 18-hole rounds. The platform manages tournaments (round-robin; knockout is a long-term goal and the API rejects it today), casual "fun rounds," real-time leaderboards, and player profiles.

**MVP Target:** Corporate Golf Days — structured events where an organiser controls the entire course.

**MVP is a lean validation build** — web-only, no native apps, no AI features, no offline-first sync, no Fun Rounds. See [`THREES_STRATEGY.md`](./THREES_STRATEGY.md) for the rationale and [`ROADMAP.md`](./ROADMAP.md) for what's Phase 1 vs Phase 2. The goal is to run one real corporate golf day, paid for via the per-event organiser fee, before investing in the full-featured build.

## Current Implementation Status

Only `backend/` exists so far — `frontend/` and `docs/` in the structure below are the target
layout, not yet created.

Implemented end-to-end in the backend: **auth, players, courses/holes, tournaments (with the
ADR-003 state machine), participants, rounds/groups (the shotgun-start draw), score entry
(the ADR-007 cascade, persisted), and the leaderboard**. **No stub routers remain** — every route
is real, and every part of the scoring engine now has a caller.

Score entry landed as `hole_scores` (raw strokes + the points each earned) and `hole_results`
(what the cascade decided, and which level decided it). The leaderboard reads the former as
`SUM(points) GROUP BY participant_id`, exactly as ADR-009 intended, and ranks it with
`rank_leaderboard`. Two endpoints: `GET /tournaments/{id}/leaderboard` (cumulative) and
`GET /rounds/{id}/leaderboard` (one round).

Not built: **Supabase Realtime** (`ROADMAP.md` M9) and the whole of `frontend/`. Realtime is only
a signal to refetch the endpoints above — ADR-001 keeps the ranking server-side — so it is purely
additive and waits on there being a client to subscribe with.

See [`backend/CLAUDE.md`](./backend/CLAUDE.md) for backend-specific commands, the auth/JWT model,
and implementation gotchas (e.g. new models must be registered in `app/models/__init__.py` or
Alembic autogenerate silently no-ops).

## Repository Structure

```
threes/
├── backend/                  # FastAPI Python backend
│   ├── app/
│   │   ├── api/              # Route handlers (routers)
│   │   │   ├── auth.py
│   │   │   ├── tournaments.py
│   │   │   ├── rounds.py
│   │   │   ├── groups.py
│   │   │   ├── scores.py
│   │   │   ├── leaderboard.py
│   │   │   ├── courses.py
│   │   │   ├── participants.py
│   │   │   └── players.py
│   │   ├── core/             # Config, security, dependencies
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── deps.py
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic layer
│   │   │   ├── scoring.py    # Points engine + leaderboard ranking (pure)
│   │   │   ├── score_entry.py # Score entry — persists what scoring.py decides
│   │   │   ├── leaderboard.py # Standings — zero-fills the field, then ranks it
│   │   │   ├── tournament.py # Tournament state machine
│   │   │   ├── grouping.py   # Draw: group sizes + shotgun-start loops (pure)
│   │   │   ├── round.py      # Round lifecycle — where draw + field + course meet
│   │   │   ├── course.py
│   │   │   └── participant.py
│   │   ├── repositories/     # Database access layer
│   │   └── main.py           # FastAPI app entry point
│   ├── migrations/           # Alembic migrations
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/                 # Flutter mobile/web app
│   ├── lib/
│   │   ├── features/         # Feature-based folder structure
│   │   │   ├── auth/
│   │   │   ├── tournaments/
│   │   │   ├── scoring/
│   │   │   ├── leaderboard/
│   │   │   ├── fun_rounds/
│   │   │   └── profile/
│   │   ├── core/             # Shared utilities, theme, routing
│   │   ├── models/           # Data models / DTOs
│   │   ├── providers/        # Riverpod providers
│   │   └── main.dart
│   ├── test/
│   ├── pubspec.yaml
│   └── analysis_options.yaml
├── docs/                     # Project documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DEPLOYMENT.md
│   └── SECURITY.md
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       └── frontend-ci.yml
├── CLAUDE.md                 # This file
├── README.md
├── ROADMAP.md
├── CONTRIBUTING.md
└── docker-compose.yml
```

## Development Commands

### Backend (FastAPI)

See [`backend/CLAUDE.md`](./backend/CLAUDE.md) for the full picture — notably that tests require a
real Postgres (no mocked-DB path) and the local Postgres container publishes on host port 5433, not 5432.

```bash
# Setup
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run development server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest
pytest --cov=app tests/

# Linting & formatting
ruff check .
ruff format .
mypy app/

# Database migrations
alembic upgrade head          # Apply all migrations
alembic revision --autogenerate -m "description"  # Create migration
alembic downgrade -1          # Rollback last migration
```

### Frontend (Flutter)

```bash
# Setup
cd frontend
flutter pub get

# Run (development)
flutter run                   # Connected device
flutter run -d chrome         # Web
flutter run -d ios             # iOS simulator
flutter run -d android         # Android emulator

# Tests
flutter test
flutter test --coverage

# Code quality
dart analyze
dart format .

# Build
flutter build apk             # Android
flutter build ios              # iOS
flutter build web              # Web
```

### Docker (Full Stack)

```bash
docker-compose up -d           # Start all services
docker-compose down            # Stop all services
docker-compose logs -f backend # Follow backend logs
```

## Architecture Decisions

### ADR-001: All data flows through FastAPI
The Flutter client does NOT query Supabase directly for data (except Auth and Realtime subscriptions). All CRUD operations go through FastAPI endpoints. This ensures consistent business logic, validation, and audit logging.

### ADR-002: Scoring engine is server-side only
All points calculation and tie-breaking happens on the backend. The client submits raw strokes; the server returns calculated results. This prevents score manipulation and ensures consistency.

### ADR-003: Tournament state machine
Tournaments follow a strict state machine: `CREATED → REGISTRATION_OPEN → REGISTRATION_CLOSED → ROUND_IN_PROGRESS → ROUND_COMPLETE → TOURNAMENT_COMPLETE`. Invalid transitions are rejected by the API.

### ADR-004: Groups of 3, with a pair or a fourball to absorb the remainder
Three is the format, so the draw makes groups of 3 wherever it can. The other two sizes exist only to place players a clean split would leave over: a remainder of two becomes a **pair** (5 is 3+2), and a remainder of one is folded into a **fourball** (7 is 3+4). A group of one is never produced — a lone player has nobody to play against, which is the whole reason the other sizes exist.

**Amended: four used to be 2+2.** Four is the standard social grouping, and four mates playing a loop together are one match. Splitting them into two pairs meant each hole was decided *within* a pair, so nobody actually played against the other two — a materially different competition from the one they thought they were in. Four players is now a single group of four, which falls straight out of the remainder-of-one rule rather than needing a special case.

Nothing in the scoring engine changed with it: `score_hole` takes a mapping of any size, and ADR-007's cascade is defined over "the players tied on strokes" without reference to how many there are. The cost is that a fourball has a slightly lower chance of an outright stroke winner than a three, so tie-breaks are asked marginally more often.

### ADR-005: Offline-resilient score entry — Phase 2
Deferred from MVP (see `THREES_STRATEGY.md` §2). MVP score submission is online-only with retry-on-failure and a connectivity warning; no local persistence. Phase 2 revisits this only if pilot feedback shows on-course connectivity is actually a problem: Flutter would store pending score submissions in local storage (Hive), sync when connectivity returns, show a "pending" indicator, and the server would resolve conflicts (last-write-wins with timestamp).

### ADR-006: Web-first for MVP
The Flutter app targets web only for MVP — no iOS/Android builds, no app store submission. This removes Fastlane, TestFlight, and Play Store review latency from the pilot's critical path. Native builds are Phase 2, pursued once the pilot validates the format and the fee.

### ADR-008: Play statuses are owned by the round endpoints
`ROUND_IN_PROGRESS` and `ROUND_COMPLETE` cannot be set through `POST /tournaments/{id}/status`. Drawing a round and starting play are one action (`POST /tournaments/{id}/rounds`), as are finishing a round and ending it (`POST /rounds/{round_id}/complete`).

Allowing the status to move on its own would let a tournament sit in `ROUND_IN_PROGRESS` with no round drawn, or in `ROUND_COMPLETE` with a round still marked in progress — two sources of truth quietly disagreeing. The status endpoint still owns the registration transitions and `ROUND_COMPLETE → TOURNAMENT_COMPLETE`.

The readiness check for "no course set" moved into the draw for the same reason: it's now the only route to `ROUND_IN_PROGRESS`, so a copy left on the status endpoint would have been unreachable.

### ADR-007: Holes are never halved — three-level tie-break
A hole has exactly one winner (1 pt) or no winner at all (everyone 0 pts). **There are no half-points**, so points are always integers.

The winner of a hole is decided by working down three levels, stopping at the first that separates the tied players:

1. **Fewest strokes.**
2. **Closest to the pin.**
3. **Longest drive on the fairway.** A drive that finished in the rough is not eligible, however long.

If all three levels fail to separate them, **nobody wins the hole** and every player in the group scores 0 for it.

**Levels 2 and 3 are contested only among the players tied on strokes.** If A and B are tied, the question is which *of A and B* was closer to the pin — C's ball is irrelevant however near the hole it finished. Naming a player who isn't tied is a data error rather than a silent fall-through: quietly returning "no winner" there would hide a real bug behind a plausible-looking result. The tie-break arguments are only consulted when a tie actually exists; an outright stroke winner takes the hole regardless.

Because the tie-breaks are scoped to the players they concern, "no winner" is uncommon. It means the tied players genuinely could not be separated — typically none of them found the fairway.

**Score entry follows from this.** There is no point flagging a hole-wide closest-to-pin or longest-drive winner, since only the tied subset counts. The tie-breaks are captured on demand: the client submits strokes, and *if* those tie, the app asks the tied players — "which of you was closest to the pin?", then if still level, "which of you hit the longest drive on the fairway?". Nothing is recorded unless it actually decided a hole.

The overall leaderboard breaks level players on **fewest total strokes across the loop**. This deliberately replaces countback on the hardest-ranked hole, which would have required the organiser to enter a difficulty ranking for every hole at setup.

**Forward compatibility with handicaps (Phase 2):** because the client submits only raw strokes (ADR-002) and points are always derived server-side, net scoring can be layered on later without changing the score-entry path or re-migrating stored scores.

### ADR-009: Scores are stored in two tables — reported and derived
A scored hole is written to **two** tables. `hole_scores` is what the players reported: one row per participant, holding their strokes and the points those strokes earned them. `hole_results` is what the ADR-007 cascade made of it: one row per group per hole, holding the winner, which of the three levels decided it, and the tie-break answer if one was used.

The split is along the line between **fact and judgement**. Strokes are reported by the group and are the only thing the client sends (ADR-002); everything in `hole_results` is the server's conclusion about them. Keeping them in one table would mean a row that is partly evidence and partly verdict, with no way to say which columns a correction is allowed to touch.

**Points live on the score row, not in the result row.** They are per-participant, so they belong beside each participant's strokes — and it makes the leaderboard `SUM(points) GROUP BY participant_id` rather than a walk over per-hole verdicts. Points are stored rather than recomputed on read because ADR-007's `decided_by` exists so a disputed hole can be audited, and an audit trail that is recalculated on demand records nothing: it would only ever show what today's code thinks, not what the group was told on the day.

**The database enforces ADR-007, not just the service.** Three check constraints on `hole_results`: a tie-break participant may be stored only when `decided_by` names that level ("nothing is recorded unless it actually decided a hole"), and `winner_participant_id IS NULL` exactly when `decided_by = 'no_winner'` — holes are never halved, so the alternative to one winner is none, never a shared one. These are invariants of the format rather than of one code path, and a wrong row is worse than a rejected write: it is a player told they won a hole they did not.

**The cost, accepted:** the two tables can disagree if anything writes one without the other, so both are always written together by `ScoreEntryService`, and re-submitting a hole rewrites both. That single upsert path is also how a correction and a late tie-break answer arrive, which is why there is no separate endpoint for either.

**Rejected:** storing only strokes and calling `score_hole` on every read. It is simpler and cannot drift, but it discards `decided_by` — the record of *why* a hole was awarded — and makes the leaderboard recompute the entire field on every poll, which is exactly the read path M8 needs to be cheap.

## Coding Conventions

### Python (Backend)

- **Python 3.12+** required
- Use `async def` for all route handlers and database calls
- Type hints on all function signatures
- Pydantic models for all request/response schemas
- Repository pattern: routes → services → repositories → database
- Naming: `snake_case` for everything (files, functions, variables)
- Docstrings on all public functions (Google style)
- No raw SQL in route handlers — use SQLAlchemy ORM or repository methods

### Dart (Frontend)

- **Dart 3.x** / **Flutter 3.x**
- Riverpod for state management (no setState in feature code)
- Feature-first folder structure
- `const` constructors wherever possible
- Naming: `snake_case` for files, `camelCase` for variables/functions, `PascalCase` for classes
- Use `freezed` for immutable data models
- No business logic in widgets — delegate to providers/services

### General

- Commit messages follow Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Branch naming: `feat/tournament-creation`, `fix/score-validation`, `docs/api-spec`
- All environment variables in `.env` files (never committed)
- Secrets in environment variables, never in code

## Environment Variables

### Backend (.env)

Only these are read (`app/core/config.py`; `extra="ignore"`, so anything else in `.env` is
silently dropped rather than rejected). No `ANTHROPIC_API_KEY` or `EMAIL_FROM` — AI generation
and email are Phase 2/3.

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/threes_dev
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

### Frontend (.env)

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
API_BASE_URL=http://localhost:8000
```

## Key Domain Concepts

- **Tournament**: A structured competition with rounds and groups, played at one **Course**.
  `course_id` is nullable so an event can be set up before the venue is booked, but a tournament
  cannot enter `ROUND_IN_PROGRESS` without one — there'd be no holes to play.
- **Course**: A golf course. **Shared reference data**, not owned by a tournament: two organisers
  running events at the same club point at one record. Names are unique *ignoring case*, so
  "Royal Melbourne" and "royal melbourne" can't both exist. Readable by anyone authenticated,
  editable only by whoever created it.
- **Hole**: One hole of a course — `hole_number`, plus optional `par` and `stroke_index`. Both are
  optional because scoring never uses par (ADR-007 is strokes alone), so an organiser can enter
  three hole numbers and start. `stroke_index` is present ready for Phase 2 handicaps. A course only
  needs the holes actually being played — a 3-hole loop needs 3, not 18.
- **Round**: One stage of a tournament — a draw of groups all playing simultaneously. Carries its own
  status (`PENDING` / `IN_PROGRESS` / `COMPLETE`), distinct from the tournament's, because a
  tournament runs several rounds and its single status can only describe the current one.
- **Group**: 2–4 players playing one 3-hole **loop** together. One group = one match. Three is the
  format; a pair or a fourball absorbs whatever a clean split leaves over (ADR-004).
- **Loop**: The 3 holes a group plays, taken as consecutive triples of the holes in play.
  **Each group gets its own loop** — a shotgun start, so the whole field tees off at once instead of
  queueing. A course caps this: 18 holes make only 6 loops, so above 18 players groups share loops
  round-robin and tee off staggered. That's expected, not an error.
- **Playing part of a course**: the draw takes an optional `hole_numbers` — `[7, 8, 9]` for a match
  played inside a normal round. The tournament stays attached to the real course record; which holes
  were played is recorded per group in `group_holes`, so a club never needs a duplicate "holes 7-9"
  course. Omitted means the whole course. A selection must be a multiple of 3, unlike the course-wide
  default, which simply leaves a remainder unused: a course is a record of what exists, a selection
  is a statement of intent, and silently dropping part of one would be the worse answer.
- **The draw**: Round 1 groups players in **registration order**, so people play with the mates they
  signed up alongside. Round 2 onwards shuffles. Both fall out of `build_groups` being deterministic
  and order-preserving — the ordering decision lives in `RoundService`, not the pure function.
- **Hole Score**: The number of strokes a player took on a single hole. Foreign-keys to a `Hole`
  rather than storing a bare hole number, so score → hole → course holds together.
- **Points**: 1 pt for winning a hole, 0 pts otherwise. **Holes are never halved** — see ADR-007 for
  the tie-break cascade. Points are always integers; there are no half-points.
- **Closest to the Pin (CTP)**: Tie-break level 2. Asked only when players tie on strokes, and only
  *of those tied players* — a non-tied player's ball is irrelevant however close it finished (ADR-007).
  Not a standalone competition in MVP.
- **Longest Drive on Fairway**: Tie-break level 3, asked on the same terms as CTP: only of the players
  tied on strokes. A drive that finished in the rough is not eligible, however long. Not a standalone
  competition in MVP.
- **Leaderboard Tie-break**: Level players are separated by fewest total strokes across the loop.
  (This replaces the earlier "countback on the hardest hole" rule, which needed a per-hole difficulty
  ranking the organiser would have had to enter.)
- **Fun Round**: A casual, non-tournament round between friends. **Phase 2** — not in MVP.
- **Participant**: Someone playing in a tournament — the identity groups and scores foreign-key to,
  never a Player directly. That indirection is what lets a Virtual Player be grouped and scored like
  anyone else. `display_name` is a snapshot taken at registration, so a leaderboard doesn't rename
  people mid-event if they edit their profile.
- **Virtual Player**: A participant with no account, whose scores are entered by another group
  member — `player_id IS NULL`. `UNIQUE(tournament_id, player_id)` prevents double registration
  while still allowing any number of virtual players, because Postgres treats NULLs as distinct.
  Names are not unique: two people really can both be John Smith.
- **The field**: A tournament's participants. Players self-register only while `REGISTRATION_OPEN`;
  the organiser can add or remove right up until `ROUND_IN_PROGRESS`. That override exists because
  ADR-003 has no route back to `REGISTRATION_OPEN`, so without it a no-show would be stuck in the
  draw. Once play starts the field is fixed.
- **Organiser Fee**: The MVP monetisation model — a flat fee, tiered by player count (small/medium/large), billed to the tournament organiser and invoiced manually. See `THREES_STRATEGY.md` §1. Not collected in-app; Stripe-based per-player entry fees are Phase 3.
- **Sponsor**: A company or brand attached to a tournament (Phase 3). Sponsor name and logo are displayed on leaderboards and invitation emails.

## Important Context

1. The MVP launches in Australia targeting corporate golf days.
2. "Threes" refers to the 3-hole competition format, not a card game.
3. The scoring engine is the most critical business logic — it must be exhaustively tested.
4. Real-time leaderboards use Supabase Realtime (Postgres LISTEN/NOTIFY), not custom WebSockets.
5. Magic link auth means no passwords are stored. Supabase Auth handles the entire flow.
6. MVP is a **lean validation build**: web-only, no AI, no offline sync, no Fun Rounds — see `THREES_STRATEGY.md`. The MVP milestone is running one real corporate golf day, with the organiser paying the per-event fee.
7. Phase 2 features (deferred): native iOS/Android apps, AI invitation/summary generation, offline-first sync, Fun Rounds, **handicaps / net scoring**, standalone longest-drive and closest-to-pin competitions (with their own prizes and leaderboards), social friends, gamification. Note that longest drive and closest to pin are *captured* in MVP because ADR-007 needs them to break tied holes — what's deferred is treating them as competitions in their own right.
8. Phase 3 features (deferred): Stripe payment processing, golf club/corporate accounts, sponsors.
