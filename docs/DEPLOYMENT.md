# Deploying Threes

Backend on **Fly.io** (Sydney), frontend on **Cloudflare Pages**, database and auth on the existing
**Supabase** project. Everything the repository can hold is committed; what remains is credentials
and dashboards.

**Nothing has been deployed yet.** This document is the procedure, not a record.

## What is already in the repo

| File | Purpose |
|---|---|
| `backend/fly.toml` | The Fly app: Sydney, always-warm, `alembic upgrade head` as the release command |
| `backend/Dockerfile` | Already production-shaped — non-root user, binds `0.0.0.0:8000`, ships `migrations/` |
| `frontend/public/_redirects` | SPA fallback, without which every join link 404s |
| `frontend/public/_headers` | Stops an edge cache pinning a stale service worker |
| `.github/workflows/deploy-backend.yml` | Manual (`workflow_dispatch`) deploy; inert until run |

## What only you can do

`fly auth login`, `fly secrets set`, and the Cloudflare and Supabase dashboards. Those hold
credentials that must not pass through a transcript or a commit.

---

## Order matters

There is a genuine circular dependency: the backend needs to allow the frontend's origin, and the
frontend needs to know the backend's URL, and neither exists until the other is deployed. Doing
these out of order produces a magic-link email that redirects to `localhost` — which looks like a
broken login rather than a misconfiguration.

1. Deploy the backend. Note its URL.
2. Create the Pages project, pointing `VITE_API_BASE_URL` at that URL. Note the Pages URL.
3. Set the backend's `CORS_ORIGINS` to the Pages URL and redeploy.
4. Set Supabase's Site URL and redirect allow-list to the Pages URL.

---

## 1. Backend — Fly.io

```bash
cd backend
fly auth login
fly launch --no-deploy      # accept the existing fly.toml; app threes-api, region syd
```

`threes-api` is a globally unique name on Fly. If it is taken, `fly launch` will say so — pick
another and change `app` in `fly.toml` to match.

### Secrets

```bash
fly secrets set \
  SUPABASE_URL="https://<ref>.supabase.co" \
  SUPABASE_KEY="sb_secret_..." \
  SUPABASE_JWT_SECRET="$(openssl rand -base64 32)" \
  DATABASE_URL="postgresql+asyncpg://postgres.<ref>:<url-encoded-password>@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres" \
  CORS_ORIGINS="https://<your-project>.pages.dev"
```

Three of those have a trap in them.

**`SUPABASE_KEY` must be the secret key (`sb_secret_…`), not the publishable one.** The Realtime
broadcast endpoint rejects a publishable key, so the leaderboard would simply stop updating live —
with no error anywhere a player can see, because a failed broadcast is deliberately swallowed
(ADR-010). Scoring would keep working and the board would keep being wrong until someone refreshed.

**`SUPABASE_JWT_SECRET` is not a Supabase value.** This project signs real tokens with ES256,
verified through JWKS; the shared secret is only used by the test suite and `scripts/dev_token.py`.
Generating a random string here means that even if it leaks it cannot mint a token this server
accepts. Putting a genuine Supabase JWT secret in it would hand that power away for nothing. See
`backend/CLAUDE.md`.

**`DATABASE_URL` must use the session-mode pooler, port 5432.** Not the transaction pooler on 6543,
and not the direct host:

- `app/core/db.py` builds the engine without `statement_cache_size=0`, so asyncpg uses prepared
  statements. Transaction-mode pgbouncer hands out a different backend connection per statement and
  those prepared statements vanish underneath it — the failure is intermittent `InvalidSQLStatementName`
  errors under load, which is to say, during an event.
- `db.<ref>.supabase.co` publishes no A record. It is IPv6-only, and Fly machines are not
  guaranteed to have IPv6 egress to it.

URL-encode the password: `@`, `/`, `#` and `?` in a password will otherwise be read as part of the
connection string's structure.

### Deploy

```bash
fly deploy
```

Or, once `FLY_API_TOKEN` is set as a repository secret under the `production` environment, run the
**Deploy Backend** workflow from the Actions tab. Generate the token with
`fly tokens create deploy -x 999999h`.

---

## 2. Frontend — Cloudflare Pages

Create a Pages project connected to this repository:

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Output directory | `dist` |
| Node version | 22 |

Environment variables (all three are required — `src/lib/env.ts` refuses to start without them):

```
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
VITE_API_BASE_URL=https://threes-api.fly.dev
```

**The publishable key, never the secret one.** Vite inlines `VITE_*` at build time, so whatever goes
here ships inside a static asset that anyone can read. `src/lib/env.ts` throws on startup if it
finds an `sb_secret_` prefix, but do not rely on that to catch a mistake — the secret key bypasses
row level security entirely.

---

## 3. Supabase Auth

In **Authentication → URL Configuration**:

- **Site URL**: the Pages URL. This is where magic links land; while it says `localhost:5173` every
  link emailed to a real player opens a page that does not exist for them.
- **Redirect URLs**: the Pages URL. Add `https://*.<your-project>.pages.dev/**` too if you want to
  be able to log in to preview deployments — every branch build gets its own subdomain, and without
  a wildcard none of them can complete a login.

---

## 4. Rotate the database password

Do this once, at the end of the first deploy. The password has been handled during development and
should not be the one a production database keeps.

**Settings → Database → Reset database password**, then:

```bash
fly secrets set DATABASE_URL="postgresql+asyncpg://postgres.<ref>:<new-url-encoded-password>@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
```

Setting a secret triggers a redeploy on its own. Update your local `backend/.env` too if it points
at Supabase rather than the local Postgres.

---

## Verifying

```bash
curl https://threes-api.fly.dev/health          # {"status":"ok"}
fly logs                                        # the release command's alembic output
```

Then, in a browser, in this order — each step depends on the one before it:

1. Load the Pages URL. It should render the sign-in screen, not a blank page. A blank page with a
   console error naming a `VITE_` variable means step 2's environment variables are incomplete.
2. Request a magic link and follow it from a real inbox. It must land on the Pages URL, not
   `localhost`. The app then calls `POST /players`; a CORS error here means `CORS_ORIGINS` does not
   match the Pages origin exactly (scheme and host, no trailing slash).
3. Create a tournament, open the invite card, and **scan the QR from a phone**. It should resolve
   `/join/THR-…` from a cold load — this is the check that `_redirects` is working, and it cannot be
   done from the desktop tab that already has the app loaded.
4. Join from that phone, draw a round, score a hole, and watch the leaderboard move on the other
   device without a refresh. That exercises the Realtime broadcast, which is the part that fails
   silently if `SUPABASE_KEY` is the wrong key.

---

## Rolling back

```bash
fly releases                        # find the previous version
fly deploy --image <image-ref>      # redeploy that image
```

**A rollback does not undo a migration.** The release command has already run by the time a bad
version is serving traffic, and rolling the image back leaves the schema where the newer code put
it. If a migration is the problem, `alembic downgrade` is a separate and deliberate act — and it
must be one the migration actually supports, which is why every migration in this repo has a real
`downgrade()`.

## Hardening, once the URLs are settled

Add a Content-Security-Policy to `frontend/public/_headers`. It is not committed today because the
correct value names both the Supabase project and the API, and a wrong `connect-src` breaks
magic-link login outright rather than degrading:

```
/*
  Content-Security-Policy: default-src 'self'; connect-src 'self' https://<ref>.supabase.co wss://<ref>.supabase.co https://threes-api.fly.dev; img-src 'self' data:; style-src 'self' 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'
```

`wss:` is required — the Realtime subscription is a WebSocket. `style-src 'unsafe-inline'` is needed
while any inline style attribute remains in the bundle; check the console for violations before
deciding it can be dropped.

## Cost

One always-warm `shared-cpu-1x` machine with 512MB, plus Supabase and Cloudflare Pages, which are
both free at this scale. The always-warm part is a deliberate choice rather than a default: see the
comment in `fly.toml` about cold starts between holes.
