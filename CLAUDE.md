# CLAUDE.md — Threes Golf Platform

## Project Overview

Threes is a short-form competitive golf platform where players compete over 3-hole loops instead of traditional 18-hole rounds. The platform manages tournaments (knockout and round-robin formats), casual "fun rounds," real-time leaderboards, and player profiles.

**MVP Target:** Corporate Golf Days — structured events where an organiser controls the entire course.

**MVP is a lean validation build** — web-only, no native apps, no AI features, no offline-first sync, no Fun Rounds. See [`THREES_STRATEGY.md`](./THREES_STRATEGY.md) for the rationale and [`ROADMAP.md`](./ROADMAP.md) for what's Phase 1 vs Phase 2. The goal is to run one real corporate golf day, paid for via the per-event organiser fee, before investing in the full-featured build.

## Current Implementation Status

Only `backend/` exists so far — `frontend/` and `docs/` in the structure below are the target layout, not yet created. Within the backend, only `auth` and `players` are implemented end-to-end; `tournaments`, `rounds`, `groups`, and `scores` are stub routers returning `501`, and their business-logic modules (`services/grouping.py`, `services/scoring.py`, `services/tournament.py`) are empty placeholders. See [`backend/CLAUDE.md`](./backend/CLAUDE.md) for backend-specific commands, the auth/JWT model, and implementation gotchas (e.g. new models must be registered in `app/models/__init__.py` or Alembic autogenerate silently no-ops).

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
│   │   │   └── players.py
│   │   ├── core/             # Config, security, dependencies
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── deps.py
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic layer
│   │   │   ├── scoring.py    # Points calculation engine
│   │   │   ├── tournament.py # Tournament state machine
│   │   │   ├── grouping.py   # Group generation algorithm
│   │   │   └── ai.py         # Claude API integration
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

### ADR-004: Groups of exactly 3
MVP enforces groups of exactly 3 players. If player count is not divisible by 3, the last group may have 2 players (a bye is not needed; 2-player groups use the same scoring rules). This simplifies the UI and scoring logic.

### ADR-005: Offline-resilient score entry — Phase 2
Deferred from MVP (see `THREES_STRATEGY.md` §2). MVP score submission is online-only with retry-on-failure and a connectivity warning; no local persistence. Phase 2 revisits this only if pilot feedback shows on-course connectivity is actually a problem: Flutter would store pending score submissions in local storage (Hive), sync when connectivity returns, show a "pending" indicator, and the server would resolve conflicts (last-write-wins with timestamp).

### ADR-006: Web-first for MVP
The Flutter app targets web only for MVP — no iOS/Android builds, no app store submission. This removes Fastlane, TestFlight, and Play Store review latency from the pilot's critical path. Native builds are Phase 2, pursued once the pilot validates the format and the fee.

### ADR-007: Holes are never halved — three-level tie-break
A hole has exactly one winner (1 pt) or no winner at all (everyone 0 pts). **There are no half-points**, so points are always integers.

The winner of a hole is decided by working down three levels, stopping at the first that separates the tied players:

1. **Fewest strokes.**
2. **Closest to the pin** — the group flags one player per hole.
3. **Longest drive on the fairway** — the group flags one player per hole. A drive that finished in the rough is not eligible, however long.

If all three levels fail to separate them, **nobody wins the hole** and every player in the group scores 0 for it.

A level can only break a tie if the flagged player is one of the tied players. If A and B are tied on strokes but C was flagged closest to the pin, level 2 cannot separate A from B and the cascade falls through to level 3. This means "no winner" is a genuinely common outcome, not an edge case, and both the scoring engine and the UI must treat it as normal.

The overall leaderboard breaks level players on **fewest total strokes across the loop**. This deliberately replaces countback on the hardest-ranked hole, which would have required the organiser to enter a difficulty ranking for every hole at setup.

**Forward compatibility with handicaps (Phase 2):** because the client submits only raw strokes (ADR-002) and points are always derived server-side, net scoring can be layered on later without changing the score-entry path or re-migrating stored scores.

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

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
ANTHROPIC_API_KEY=sk-ant-...
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
EMAIL_FROM=noreply@threes.golf
```

### Frontend (.env)

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
API_BASE_URL=http://localhost:8000
```

## Key Domain Concepts

- **Tournament**: A structured competition with rounds, groups, and a bracket.
- **Round**: One stage of a tournament. Each round has multiple groups playing simultaneously.
- **Group**: 2–3 players playing the same 3 holes together. One group = one match.
- **Hole Score**: The number of strokes a player took on a single hole.
- **Points**: 1 pt for winning a hole, 0 pts otherwise. **Holes are never halved** — see ADR-007 for
  the tie-break cascade. Points are always integers; there are no half-points.
- **Closest to the Pin (CTP)**: Per hole, the group flags which single player finished closest to the
  pin. Captured for every hole as a tie-break input (ADR-007), not as a standalone competition.
- **Longest Drive on Fairway**: Per hole, the group flags which single player hit the longest drive
  that *finished on the fairway*. A longer drive into the rough is not eligible. Tie-break input only.
- **Leaderboard Tie-break**: Level players are separated by fewest total strokes across the loop.
  (This replaces the earlier "countback on the hardest hole" rule, which needed a per-hole difficulty
  ranking the organiser would have had to enter.)
- **Fun Round**: A casual, non-tournament round between friends. **Phase 2** — not in MVP.
- **Virtual Player**: A player without a device, whose scores are entered by another group member.
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
