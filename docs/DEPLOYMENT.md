# Deploying Threes

Backend on **Fly.io** (Sydney), frontend on **Cloudflare Workers** (static assets), database and
auth on the existing
**Supabase** project. Everything the repository can hold is committed; what remains is credentials
and dashboards.

**Both ends are deployed.** The backend is `threes-api.fly.dev` — one always-warm machine in Sydney,
schema at head, health check passing — and the frontend Worker serves `app.threes.golf`, with the
SPA fallback resolving cold `/join/THR-…` loads. This document is both the procedure and a record of
what was done.

## What is already in the repo

| File | Purpose |
|---|---|
| `backend/fly.toml` | The Fly app: Sydney, always-warm, `alembic upgrade head` as the release command |
| `backend/Dockerfile` | Already production-shaped — non-root user, binds `0.0.0.0:8000`, ships `migrations/` |
| `frontend/wrangler.jsonc` | The Worker: assets directory, and the SPA fallback without which every join link 404s |
| `frontend/public/_headers` | Stops an edge cache pinning a stale service worker |
| `.github/workflows/deploy-backend.yml` | Manual (`workflow_dispatch`) deploy; inert until run |

## What only you can do

`fly auth login`, `fly secrets set`, and the Cloudflare and Supabase dashboards. Those hold
credentials that must not pass through a transcript or a commit.

---

## Order matters

There is a genuine circular dependency: the backend needs to allow the frontend's origin, and the
frontend needs to know the backend's URL, and neither exists until the other is deployed. Doing
these out of order produces a magic-link email that redirects to `localhost:3000` — which looks
like a broken login rather than a misconfiguration. §3 covers how to spot it before clicking.

1. Deploy the backend. Note its URL.
2. Create the Worker, pointing `VITE_API_BASE_URL` at that URL. Note the origin it serves on.
3. Set the backend's `CORS_ORIGINS` to that origin and redeploy.
4. Set Supabase's Site URL and redirect allow-list to that origin.

Both ends are now settled: the backend is `https://threes-api.fly.dev` and the frontend is
`https://app.threes.golf`, so the loop above only has to be walked again if either moves.

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
  DATABASE_URL="postgresql+asyncpg://postgres.<ref>:<url-encoded-password>@<pooler-host>:5432/postgres" \
  CORS_ORIGINS="https://app.threes.golf" \
  APP_URL="https://app.threes.golf" \
  RESEND_API_KEY="re_..." \
  EMAIL_FROM="Threes <noreply@your-domain.com>" \
  CRON_SECRET="$(openssl rand -base64 32)"
```

`APP_URL`, `RESEND_API_KEY`, `EMAIL_FROM` and `CRON_SECRET` are for reminders. Leave the mail two
unset and the app runs with a `NullMailer` — everything works, nothing sends, which is a reasonable
way to deploy first and switch mail on later.

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

- Transaction-mode pgbouncer hands out a different backend connection per transaction, and a
  prepared statement made on one is gone on the next — intermittent `InvalidSQLStatementName`
  errors under load, which is to say, during an event.
- `db.<ref>.supabase.co` publishes no A record. It is IPv6-only, and Fly machines are not
  guaranteed to have IPv6 egress to it.

**This warning was already here and was not followed, so the app no longer depends on it.**
`asyncpg_connect_args` in `app/core/db.py` recognises port 6543 and turns both statement caches off,
naming each statement uniquely, then logs a warning saying so. A wrong port now costs prepared-statement
reuse rather than the day. Session mode is still the string to deploy — that saving is real — but it
is a performance choice again instead of the only thing between a typo and an outage mid-round.

**Copy `<pooler-host>` from the dashboard — Connect → Session pooler — rather than composing it.**
The fleet is per *project*, not per region: `aws-0-ap-southeast-2` and `aws-1-ap-southeast-2` both
exist and are different load balancers, so a project on one is simply absent from the other. Guessing
gives `Tenant or user not found`, which reads like a credentials problem and is not one.

**Keep the `postgresql+asyncpg://` scheme.** Supabase prints a bare `postgresql://`, and asyncpg is
the only driver installed. `Settings` coerces a bare URL and logs a warning rather than failing
(`app/core/config.py`), but set it correctly and the warning stays out of the log.

URL-encode the password: `@`, `/`, `#` and `?` in a password will otherwise be read as part of the
connection string's structure. An unencoded `@` does not fail as a password error — it re-splits the
string, and the *host* becomes the tail of the password, so the deploy dies on DNS instead.

**Check the string before setting it.** `fly secrets set` accepts anything, and the first thing that
disagrees is a release command four minutes later:

```bash
python scripts/check_db_url.py --connect     # prompts; nothing is echoed or kept in history
```

It parses the URL the way asyncpg will, prints it back with the password redacted, resolves the host,
and — with `--connect` — opens it and asks the server what it is. Every failure in the table below is
one it catches in under a second.

### Deploy

```bash
fly deploy
```

Or, once `FLY_API_TOKEN` is set as a repository secret under the `production` environment, run the
**Deploy Backend** workflow from the Actions tab. Generate the token with
`fly tokens create deploy -x 999999h`.

### When the deploy fails

`fly.toml` runs `alembic upgrade head` as its `release_command`, on a throwaway machine, *before*
any traffic moves. That is the design — a schema step that cannot run must not put a half-migrated
app in front of a field on a tee — but it means the failure happens somewhere the deploy output
barely shows. The traceback is in the logs:

```bash
fly logs --app threes-api --no-tail | tail -40
fly releases --app threes-api            # which version failed, and when
```

**`--no-tail` buffers minutes, not hours** — measured at ~100 lines, which on a healthy app is
nothing but health checks. A runtime error that happened an hour ago is already gone. Leave
`fly logs --app threes-api` tailing in one terminal and reproduce the failure in another; that is
the only reliable way to catch one.

Three errors that name nothing resembling their cause, all seen on the first real deploy:

| What the log says | What is actually wrong |
|---|---|
| `ModuleNotFoundError: No module named 'psycopg2'` | `DATABASE_URL` names no driver. SQLAlchemy's default for a bare `postgresql://` is psycopg2, which this project has never depended on. Use `postgresql+asyncpg://`. |
| `asyncpg…InternalServerError: (ENOTFOUND) tenant/user postgres.<ref> not found` | Right credentials, wrong pooler fleet. `<pooler-host>` must be the one the dashboard prints for *this* project. |
| `socket.gaierror: [Errno -2] Name or service not known` | The host does not resolve. Either a placeholder survived, or an unencoded `@` in the password re-split the URL and the host is now a fragment of it. `check_db_url.py` prints the host it actually parsed. |
| The **browser** reports `blocked by CORS policy: No 'Access-Control-Allow-Origin' header`, and the network tab shows **500** | Not CORS. An unhandled exception used to be answered by Starlette's `ServerErrorMiddleware`, which sits *outside* `CORSMiddleware`, so the 500 went out bare and the browser blamed the only thing it could name. `CatchUnhandledErrors` now answers inside CORS, so the console says 500 and `fly logs` has the traceback. The 500 behind this one was `DATABASE_URL` on 6543 — the row above. |

`fly secrets list` showing every secret as **Staged** is not a cause. An app with no machines yet has
nowhere to apply them; they land on the first release that succeeds.

---

## 2. Frontend — Cloudflare Workers

A **Worker with static assets**, not a Pages project. Cloudflare creates static sites this way now,
and the difference is not cosmetic — see the routing note below, which is the one place it bites.

Create the Worker from **Workers & Pages → Create → Import a repository**, pointing at this
repository:

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Deploy command | `npx wrangler deploy` |
| Node version | 22 (also pinned by `frontend/.node-version`) |

**Root directory is the one that has to be right before any of the others can be.** It is where the
build command runs, and nothing the build needs is anywhere else: `package.json` and
`package-lock.json` are in `frontend/`, and so is `wrangler.jsonc`, which the deploy command reads.
Left empty, the build runs at the repository root — which holds no `package.json` at all, by design
— and `npm ci` fails before a line of this project executes. That is the second row of the table
below, and it is worth checking first because every other setting is judged against a build that
never started.

The output directory is not a dashboard field here. `frontend/wrangler.jsonc` names it
(`assets.directory: "./dist"`), which is the point of the config file existing.

### Routing: why there is no `_redirects`

Pages served an SPA with a `/*  /index.html  200` catch-all in `public/_redirects`. **On Workers that
rule breaks the site outright**, because per Cloudflare's docs "redirects are always followed,
regardless of whether or not an asset matches the incoming request" — so the catch-all matches
`/assets/index-*.js` and `/sw.js` too, and every one of them is served `index.html`. Nothing loads.

`wrangler.jsonc` uses `not_found_handling: "single-page-application"` instead, which fires only when
nothing matched. That is what makes a cold `/join/THR-…` from a QR code resolve.

`_headers` is unaffected and still committed: it decorates responses rather than routing them, so a
`/*` rule there carries no equivalent hazard.

### Environment variables — and which of the two places they go

All three are required:

```
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
VITE_API_BASE_URL=https://threes-api.fly.dev
```

They belong in **Settings → Build → Variables and secrets**. Either kind works: Cloudflare exposes
build variables *and* build secrets to the build, and differs only in whether the value stays
readable in the dashboard afterwards.

**A Worker has a second, unrelated "Variables and secrets" under its runtime settings, and putting
them there does nothing.** Those are bindings handed to Worker code at request time; this site is
static assets with no server code to read them, and Vite finished hours earlier. Vite inlines
`VITE_*` **at build time**, which is the whole difficulty: the values have to exist when
`npm run build` runs, or there is nothing to inline and no later setting can supply it.

**Changing a build variable does not rebuild.** The live deployment keeps whatever bundle it already
has. Re-run the build from **Deployments → Retry**, or push a commit.

**The publishable key, never the secret one.** Whatever goes here ships inside a static asset that
anyone can read. Two guards check this, and neither is a substitute for reading the prefix: the
build refuses an `sb_secret_` value (`frontend/build-env.ts`), and `src/lib/env.ts` refuses one
again at startup.

### When the build fails

Six things account for almost everything, and only the fifth fails in a way that names itself —
which is why it was added.

| What the log says | What is actually wrong |
|---|---|
| `Error: No lock file (package-lock.json, yarn.lock, pnpm-lock.yaml) found` | The build command says **`npx`** where it should say `npm`. `npx ci` finds an unrelated registry package called `ci` and runs *that*; the message is its, not npm's. `frontend/package-lock.json` is committed and fine. |
| `npm error code EUSAGE` / `npm ci` `can only install with an existing package-lock.json` | **Root directory** is not `frontend`, so npm is standing at the repository root — where there is no `package.json` and no lockfile, by design. Not the same as the row above, though both blame the lockfile: check `Executing user build command:`. `npx` means the row above, `npm` means this one. |
| A Vite or esbuild syntax error on a build that passes locally | Node is too old. `vite` declares `^20.19.0 \|\| >=22.12.0`; `frontend/.node-version` and `engines` in `package.json` both pin it, and `NODE_VERSION` in the dashboard overrides them. The least likely of the six now — Cloudflare's default is 24.18.0, which already satisfies that range. |
| The build succeeds, the site loads blank, and the JS request returns HTML | A `/*` catch-all in `_redirects`. On Workers those are followed even when an asset matches, so the whole bundle is served `index.html`. Routing belongs in `wrangler.jsonc`, not `_redirects`. |
| `Cannot build: the frontend configuration is incomplete` | Exactly what it says — the named `VITE_*` variables are not in the **build** environment. This is the guard working; see the row below for what it is preventing. |
| The build succeeds, the JS is served correctly, and the page is still blank with a console error naming a `VITE_` variable | An older build, made before the guard existed, with no values to inline. `grep -o 'supabase\.co' dist/assets/index-*.js` on the served bundle returns nothing. Set the build variables and **re-run the build** — the deployed bundle cannot be repaired in place. |

Two lines near the top of every log settle most of it before you read the error.

`Executing user build command:` separates the two lockfile-shaped messages outright — `npx` is the
first row, `npm` is the second.

`Detected the following tools from environment:` is the more useful one, and easy to misread. It
names what Cloudflare pinned, and **empty means it found no version file** — but the first thing
that implies is the *root directory*, not the Node version, because `.node-version` lives in
`frontend/` and Cloudflare only looks inside the configured root. An empty tools line arrives
alongside `No dependencies detected to cache. Skipping.` and the `EUSAGE` failure, and those three
together are one symptom, not three: **the build is standing in the wrong directory.** Read it as
the Node row only once the root directory is known to be right.

### The domain

The app is served from **`https://app.threes.golf`**, which is the origin every other setting in this
runbook has to match.

`app.` rather than the apex because this is an application rather than a marketing site, and it
leaves `threes.golf` free for one later. The apex is not wasted: it redirects, so the short domain is
still what goes on a printed sign at a registration desk.

Attach `app.threes.golf` to the Worker and Cloudflare creates the DNS record and issues the
certificate. Then three redirect rules, all 301, all to the canonical origin:

```
https://threes.golf/*         -> https://app.threes.golf/$1
https://www.threes.golf/*     -> https://app.threes.golf/$1
https://<worker>.workers.dev/*  -> https://app.threes.golf/$1
```

The `.workers.dev` one is not tidiness. `CORS_ORIGINS` names one origin, so that address would
otherwise serve a site that loads and then fails every API call — the worst kind of broken, because
it looks fine. The apex rule needs a proxied placeholder record to attach to (`A` → `192.0.2.1`,
orange cloud); that is Cloudflare's standard recipe for redirecting an apex.

**Moving the zone: check the mail.** `threes.golf` was on DreamHost nameservers with live MX records
(`mx1`/`mx2.dreamhost.com`) and nothing else — no A, no CNAME, no TXT. Cloudflare's onboarding scan
imports existing records, but confirm those two survived before and after the nameserver change:

```bash
dig +short MX threes.golf
```

It is the only step here whose failure costs something that has nothing to do with the deployment.

---

## 3. Supabase Auth

In **Authentication → URL Configuration**:

| Field | Value |
|---|---|
| Site URL | `https://app.threes.golf` |
| Redirect URLs | `https://app.threes.golf/**` |
| Redirect URLs | `http://localhost:5173/**` |

**Both matter, and the second is the one that is easy to get wrong.** Supabase honours the
`emailRedirectTo` the app asks for only if it matches the allow list. When it does not, the request
does not fail — it **silently substitutes the Site URL**, mails that instead, and returns success to
the caller. So a wrong allow list and a wrong Site URL produce one symptom between them, and fixing
only the Site URL hides the other.

The allow-list entries need `/**` on the end — not `/*`, and not the bare origin.
`LoginPage.tsx` asks to come back to
`window.location.origin + window.location.pathname`, so the values that must match are
`https://app.threes.golf/` for an ordinary sign-in and `https://app.threes.golf/join/THR-8K2QF` for
somebody who scanned a QR code at registration. Supabase's matching is glob-style: `*` matches "any
sequence of non-separator characters" and stops at a `/`, `**` crosses them, and a trailing slash is
significant — their own example notes that `http://localhost:3000/*` does not match
`http://localhost:3000/foo/`. A bare `https://app.threes.golf` matches neither of ours. `/*` matches
only the first. `frontend/src/features/auth/LoginPage.test.tsx` pins both strings so the app end of
this contract cannot drift away from the dashboard end.

The `localhost` entry keeps local sign-in working. Once Site URL is `app.threes.golf`, a dev-server
login with no matching entry falls back to production — which looks like the dev server being broken.

### Reading it out of the email

`redirect_to` is a plain query parameter on the emailed link, so a mistake here is visible **without
clicking anything**:

```
…/auth/v1/verify?token=…&type=magiclink&redirect_to=http://localhost:3000
```

`localhost:3000` is the specific tell that the fallback fired: nothing in this project uses port
3000 — Vite dev is 5173, the API is 8000 — so it can only have come from an untouched Supabase Site
URL. Anything other than the origin you requested the link from means the allow list did not match.

### Preview builds are a different question

A wildcard for preview builds (`https://*.workers.dev/**`) buys less than it looks like — a wildcard
across *origins*, not across paths, and unrelated to the `/**` above. `app/main.py` passes
`allow_origins` an exact-match list — Starlette does no pattern matching — so a preview build would
complete its login and then fail every API call. Letting previews through means `allow_origin_regex`
in the backend, which is a deliberate decision to let any branch build read production data, not a
config tweak. Production origin only until that is actually wanted.

### Sending the mail: custom SMTP is not optional

**Supabase's built-in email service is capped at 2 messages per hour, and that cap cannot be
raised.** It exists for kicking the tyres, not for running an event — two is not enough to sign in
one fourball. Every sign-in sends a message, so the cap is reached by the third person to arrive at
registration, and the ones after that get nothing with no indication why. This is the single most
likely thing to stop a golf day working, and until it was hit in anger nothing in this runbook
mentioned it.

The way out is a sender of your own. Resend is already set up for reminders (§4), the domain is
already verified, and Supabase takes it as plain SMTP. In **Authentication → Emails → SMTP
Settings**:

| Field | Value |
|---|---|
| Host | `smtp.resend.com` |
| Port | `465` |
| Username | `resend` |
| Password | the same `RESEND_API_KEY` the backend already holds |
| Sender email | the `EMAIL_FROM` address, which must be on the **verified** Resend domain |

**Then raise the limit, which is a second step.** Configuring SMTP does not lift the cap by itself —
it only moves the cap from Supabase's number to yours, and the default it leaves behind is still far
below a full field. In **Authentication → Rate Limits**, set the emails-per-hour figure above the
largest field you expect to sign in within an hour, with headroom for people who lose the first link
and ask for another. Registration is bursty — the whole field arrives inside the same ten minutes —
so size it for the burst rather than the average. Skipping this step reproduces the original symptom
at a different number, which is worse, because it looks like the fix did not work.

Leave **Confirm email** off (`mailer_autoconfirm`). A magic link is itself proof of the address, so
a separate confirmation would be a second message per signup and double the volume for nothing.
Turning it off is *not* a way to reduce sending, though, and was tried as one: `signInWithOtp` sends
a message on every attempt regardless.

You can read the current state of all of this without opening the dashboard:

```bash
curl -s "https://<project-ref>.supabase.co/auth/v1/settings" -H "apikey: <publishable-key>"
```

`"email": true` under `external` means the provider is on; `"mailer_autoconfirm": true` means
confirmations are off. The publishable key is safe to use here — it already ships in the bundle.

### The password bypass, and how to turn it off

Until the SMTP work above is done, the link often does not arrive at all, so the app also offers
signing in with a password — behind **"Can't get the email?"** on the sign-in screen. It works
because this project has confirmations off (`mailer_autoconfirm: true`), which means
`supabase.auth.signUp` returns a session immediately and **sends nothing**. No dashboard change is
needed to make it work; the Email provider is already on.

It is controlled by `VITE_ENABLE_PASSWORD_LOGIN`, which is **on when unset** — a bypass that has to
be switched on is no use to somebody already locked out. Only `false` and `0` turn it off, so a typo
leaves it in place rather than silently removing the only way in.

**To remove it once SMTP works:** set `VITE_ENABLE_PASSWORD_LOGIN=false` in the Cloudflare **build**
variables — Settings → Build → Variables and secrets, not the Worker runtime bindings (§2 covers why
that distinction bites) — and **re-run the build**. Saving a build variable does not rebuild on its
own, and Vite inlines the value, so nothing changes until it does.

**To sign in as an account that already exists**, set a password on it in **Authentication → Users →
(the user) → Update password**. Signing up again with the same address will not do it: Supabase
answers an already-registered address without setting a password, so an account created by magic
link stays reachable only by magic link until you do this. Using a fresh address instead needs no
dashboard access at all.

Worth being honest about the trade: with confirmations off, a password signup does not prove the
person owns the address. That was already true of magic-link signups here for the same reason, so
this changes nothing about the actual posture — but it is the reason to take the flag off rather
than leave it on indefinitely.

### When the link arrives but does not sign anyone in

Corporate mail is the awkward case, and corporate golf days are the target. Outlook Safe Links and
similar scanners **pre-fetch URLs in incoming mail**, and a magic-link token is single-use — so the
scanner spends it and the player clicks a link that is already dead. Nothing is misconfigured and
nothing will show up in logs.

The app now says so rather than silently returning to the sign-in form: `features/auth/callback-error.ts`
reads the `error_code` Supabase puts on the callback URL and `LoginPage` shows it, so an expired or
already-used link reads as "send yourself a new one" instead of looking like a broken button. That
makes it legible, not fixed. The actual fix is a 6-digit code, which a scanner cannot consume, and
that needs a code-entry screen the app does not have yet. Worth building before a pilot whose
attendees are all on corporate mail.

---

## 4. Reminders

Only needed when you want the app mailing players.

1. Create a Resend account and **verify the sending domain**. An unverified domain is accepted by
   the API and then quietly not delivered, which looks exactly like the feature not working.
2. Set `RESEND_API_KEY` and `EMAIL_FROM` (above). `EMAIL_FROM` must be on the verified domain.
3. Set `APP_URL` to `https://app.threes.golf`. Links in reminder emails are built from it, and a
   wrong value produces mail whose links reach nobody — worse than mail that doesn't send.
4. For the day-before sweep, add two repository secrets under the `production` environment:
   `API_BASE_URL` (the Fly URL) and `CRON_SECRET` (**the same value** as the Fly secret).
5. Run the `Reminder Sweep` workflow by hand to check it answers 200, then **restore its schedule** —
   it is `workflow_dispatch`-only today, because an hourly cron against a backend that did not exist
   yet failed on every run and taught everyone to ignore it. The `on:` block in
   `.github/workflows/reminder-sweep.yml` carries the cron line to put back.

The sweep endpoint refuses everything while `CRON_SECRET` is unset — a route that mails an entire
field must not default to open — and answers 404 rather than advertising that it exists.

## 5. Rotate the database password

Do this once, at the end of the first deploy. The password has been handled during development and
should not be the one a production database keeps.

**Settings → Database → Reset database password**, then:

```bash
fly secrets set DATABASE_URL="postgresql+asyncpg://postgres.<ref>:<new-url-encoded-password>@<pooler-host>:5432/postgres"
```

Setting a secret triggers a redeploy on its own. Update your local `backend/.env` too if it points
at Supabase rather than the local Postgres.

---

## Verifying

```bash
curl https://threes-api.fly.dev/health          # {"status":"ok"}
fly checks list --app threes-api                # a passing check, not an empty table
fly logs                                        # the release command's alembic output
```

`fly checks list` rather than `fly config validate`. Validation only proves the TOML parses — it
answers "✓ Configuration is valid" for `[[http_service.banana_checks]]` — so a health check block
under a key Fly does not recognise is accepted, ignored, and never runs.

CORS is checkable without a browser, which is worth doing before wondering whether the frontend is
at fault:

```bash
curl -s -D - -o /dev/null -X OPTIONS https://threes-api.fly.dev/health \
  -H "Origin: https://app.threes.golf" -H "Access-Control-Request-Method: GET" \
  | grep -i access-control-allow-origin
```

A returned header is the pass. A 400 with no header means `CORS_ORIGINS` does not contain that exact
origin.

Then, in a browser, in this order — each step depends on the one before it:

1. Load `https://app.threes.golf`. It should render the sign-in screen, not a blank page. A blank
   page with a console error naming a `VITE_` variable means step 2's environment variables are
   incomplete.
2. Load `https://threes.golf`. It should 301 to `app.threes.golf` — the redirect is the whole reason
   a domain this short is worth owning, since it is what gets printed on a sign.
3. Request a magic link and, before clicking it, read `redirect_to=` out of the URL. It must say
   `https://app.threes.golf/`; `localhost:3000` means Supabase fell back to Site URL because the
   allow list did not match (§3). Then follow it. The app calls `POST /players`; a CORS error here
   means `CORS_ORIGINS` does not match the origin exactly (scheme and host, no trailing slash).
4. **Request a fourth link within the same hour.** Two successes prove nothing — two was always
   allowed. This is the only step that actually tests the SMTP work in §3, and it is the one that
   was failing when a real field tried to sign in. If the fourth does not arrive, the rate limit was
   not raised; SMTP alone does not do it.
5. Click a link twice. The second time should say the link has already been used, on the sign-in
   screen, with the form ready. Silence there means the callback error handling regressed — it is
   the difference between a player knowing to ask for another link and concluding the app is broken.
6. Create a tournament, open the invite card, and **scan the QR from a phone**. It should resolve
   `/join/THR-…` from a cold load — this is the check that `not_found_handling` is working, and it
   cannot be done from the desktop tab that already has the app loaded.
7. Join from that phone, draw a round, score a hole, and watch the leaderboard move on the other
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
  Content-Security-Policy: default-src 'self'; connect-src 'self' https://asrijzarthrqgyuujigw.supabase.co wss://asrijzarthrqgyuujigw.supabase.co https://threes-api.fly.dev; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; base-uri 'none'; frame-ancestors 'none'
```

Three of those directives are load-bearing for a specific reason:

- **`wss:`** — the Realtime subscription is a WebSocket, and `connect-src` covers it separately from
  the https origin.
- **The two font hosts.** `index.html` loads Archivo from `fonts.googleapis.com`, which then fetches
  the font files from `fonts.gstatic.com` — two hosts, hence `style-src` *and* `font-src`. Omit them
  and the page still renders, in a fallback face, which is the kind of breakage that gets blamed on
  anything but a header.
- **`style-src 'unsafe-inline'`** — needed while any inline style attribute remains in the bundle.
  Check the console for violations before deciding it can be dropped.

## Cost

One always-warm `shared-cpu-1x` machine with 512MB, plus Supabase and Cloudflare Workers, which are
both free at this scale. The always-warm part is a deliberate choice rather than a default: see the
comment in `fly.toml` about cold starts between holes.
