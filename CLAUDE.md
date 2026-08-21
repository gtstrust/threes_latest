# CLAUDE.md — Threes Golf Platform

## Project Overview

Threes is a short-form competitive golf platform where players compete over 3-hole loops instead of traditional 18-hole rounds. The platform manages tournaments (knockout and round-robin formats), casual "fun rounds," real-time leaderboards, and player profiles.

**MVP Target:** Corporate Golf Days — structured events where an organiser controls the entire course.

**MVP is a lean validation build** — web-only, no native apps, no AI features, no offline-first sync, no Fun Rounds. See [`THREES_STRATEGY.md`](../THREES_STRATEGY.md) for the rationale and [`ROADMAP.md`](./ROADMAP.md) for what's Phase 1 vs Phase 2. The goal is to run one real corporate golf day, paid for via the per-event organiser fee, before investing in the full-featured build.

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
- **Points**: 1 pt for winning a hole (lowest strokes), 0.5 pts for a halved hole, 0 pts for losing.
- **Countback**: Tie-breaker using performance on the hardest-ranked hole.
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
7. Phase 2 features (deferred): native iOS/Android apps, AI invitation/summary generation, offline-first sync, Fun Rounds, longest drive, closest to pin, social friends, gamification.
8. Phase 3 features (deferred): Stripe payment processing, golf club/corporate accounts, sponsors.
