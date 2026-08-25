# Threes Frontend

React + Vite (TypeScript), web only, shipped as an installable PWA. See
[`../CLAUDE.md`](../CLAUDE.md) for the project spec and ADR-006 for why this is
not Flutter.

## Quick start

The backend has to be running — see [`../backend/README.md`](../backend/README.md).

```bash
cd frontend
npm install
cp .env.example .env    # then fill in the publishable key
npm run dev             # http://localhost:5173
```

## Configuration

| Variable | Purpose |
|----------|---------|
| `VITE_SUPABASE_URL` | Your Supabase project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | The `sb_publishable_…` key, from Project Settings → API keys |
| `VITE_API_BASE_URL` | Where FastAPI is listening |

**Vite inlines `VITE_*` at build time**, so every value here ends up in a static
asset any visitor can read. That is fine for these three. It is also why the
**secret** key (`sb_secret_…`) must never appear in this directory — it bypasses
row level security and belongs only in `backend/.env`. `src/lib/env.ts` refuses
to start if it finds one, and `.env` is gitignored while `.env.example` is not.

The dev server's origin must be in the backend's `CORS_ORIGINS`; `localhost:5173`
is in the default.

## Commands

```bash
npm run dev          # dev server with HMR
npm run build        # static bundle in dist/
npm run preview      # serve the built bundle
npm test             # vitest, once
npm run test:watch
npm run typecheck    # tsc -b
npm run lint         # oxlint
```

## How it fits together

**ADR-001 holds literally: `supabase-js` is used for exactly two things** —
magic-link auth and the realtime subscription. Every byte of data comes from
FastAPI with a bearer token. There is no `.from(...)` anywhere in `src/`, and
there should never be: the tables carry deny-all row level security, so such a
call returns nothing rather than failing in a way you would notice.

```
src/
  lib/
    env.ts        config, validated at startup; rejects a secret key
    supabase.ts   auth + realtime channel, nothing else
    api.ts        typed fetch, injects the bearer, flattens FastAPI's two error shapes
    realtime.ts   subscribe(tournamentId) -> refetch
    types.ts      mirrors backend/app/schemas/
  features/
    auth/         login, session, the profile-provisioning gate
```

Three things about this API that are easy to get wrong, all of them learned the
hard way:

- **`POST /players` must be called once after login**, before any other
  `/players` route, or they 404. A verified token does not imply a profile row.
  `features/auth/session.tsx` does it; `RequireAuth` holds the app back until it
  succeeds.
- **Tournament status values are UPPERCASE** — `REGISTRATION_OPEN`, not
  `registration_open`. Lowercase is a 422.
- **Score entry is a conversation, not a form.** POST the strokes; if the
  response carries `tied_participants`, ask *only those players* who was closest
  to the pin and POST the same hole again with the answer. Naming a player who is
  not tied is a 422, deliberately (ADR-007).

## Status

Slice 1 of 5 — shell, magic-link auth, profile provisioning, PWA install.
Tournaments, the draw, score entry and the leaderboard follow; see the Frontend
table in [`../ROADMAP.md`](../ROADMAP.md).
