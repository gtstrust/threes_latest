# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is the `frontend/` package of the Threes monorepo. See [`../CLAUDE.md`](../CLAUDE.md) for the
project spec, domain concepts and ADRs, and [`../backend/CLAUDE.md`](../backend/CLAUDE.md) for the
API this talks to. This file covers only what is specific to the client and takes several files to
piece together. `README.md` next to it is the quick start.

## Commands

Node 22 (`.node-version`); npm, with `package-lock.json` committed.

```bash
npm install
cp .env.example .env          # then fill in the sb_publishable_ key

npm run dev                   # http://localhost:5173
npm run build                 # tsc -b && vite build → dist/
npm run preview               # serve the built bundle

npm test                      # vitest, once
npm run test:watch
npx vitest run src/lib/env.test.ts        # one file
npx vitest run -t "playing order"         # by name

npm run typecheck             # tsc -b
npm run lint                  # oxlint
```

The dev port is `strictPort`, so a second dev server fails rather than sliding to 5174 — 5173 is
the origin the backend's `CORS_ORIGINS` and Supabase's redirect allow-list know about, and one on
another port loads fine but cannot reach the API, which reads to a user as "Could not reach the
server".

## Architecture

### The data path: `api.ts` → `queries.ts` → features

`lib/api.ts` is the only place this app fetches. It attaches the Supabase access token as a bearer
and turns every failure into `ApiError { status, detail }`. Two things it does that callers rely on:

- **It flattens FastAPI's two error shapes.** `HTTPException` gives `{detail: "a sentence"}`; a
  Pydantic failure gives `{detail: [{loc, msg, type}, …]}`. Rendering the second raw puts
  `[object Object]` in front of a player standing on a tee, so `readDetail` collapses both to a
  sentence here rather than at each call site. Show `error.detail`; it is written for a human.
- **No token is a 401 with the message `Not signed in`**, thrown before any request goes out. That
  is deliberately distinguishable from a server 401: nothing was rejected, there was nothing to
  reject.

Four statuses mean something specific and should be branched on rather than shown raw — **404** on
`/players/me` (no profile row yet; see below), **409** a state-machine refusal (ADR-003/ADR-008),
**422** most often a tie-break naming a player who is not tied (ADR-007), and **503** the backend
could not reach Supabase to verify the token — the session is fine, so retry rather than sign out.

**Never `supabase.from(...)`.** ADR-001 holds literally: `supabase-js` is auth and the realtime
channel, nothing else. The tables carry deny-all RLS, so such a call returns nothing rather than
failing in a way you would notice.

### Query keys, and the prefix that does not cover everything

`lib/queries.ts` holds one `keys` object and every hook in the app. The keys are shaped so that one
invalidation can cover a whole tournament — but **only some of them sit under that prefix, and this
is the easiest thing here to get wrong**:

- `['tournament', id]` covers the tournament, its field, its rounds and its **cumulative**
  leaderboard. Invalidating the prefix moves all four.
- `keys.roundLeaderboard(roundId)` is `['round', roundId, 'leaderboard']` and `keys.card(groupId)`
  is `['group', groupId, 'card']`. **Neither is under it.** They are keyed by the thing they belong
  to, which is not the tournament.

That is why the two call sites that matter each fire more than one invalidation:
`LeaderboardPage.tsx` invalidates the tournament subtree *and* the round board it is showing, and
`useSubmitHole` invalidates the group's card *and* the tournament subtree — the latter so the
scorer's own board moves without waiting for the round trip through Supabase, since they are the one
person who already knows.

Add a key under the wrong root and nothing errors: the board simply stops moving, which on the day
looks like the app hanging rather than like a bug.

### Realtime is an invalidation, not a feed

`lib/realtime.ts` is the client half of ADR-010. The server broadcasts a contentless ping on
`tournament:{id}` after each hole; the client answers by refetching through FastAPI, where
`require_can_view` decides what this caller may see.

- **`tournamentTopic()` must match `TOURNAMENT_TOPIC` server-side.** Two independent string builders
  agreeing by hand is the whole contract.
- **Never render from the payload.** It carries a round id purely so a caller can scope its
  invalidation. The moment something renderable arrives in it, there is a second, unguarded read
  path in the app — exactly what ADR-010 exists to prevent.
- **`subscribeToTournament` returns an unsubscribe; call it on unmount.** Leaving channels open
  across navigation gives you a socket per screen visited and a board that refetches once per stale
  subscription.

Only the two leaderboard pages subscribe. Everything else finds out on its own refetch, which is the
ADR's position, not an omission.

### One route is public, and the guard is now a layout route

`RequireAuth` used to wrap `<Routes>`, so every path in the app was gated — including
`/join/:code`, whose "only unguarded read" reputation is a *backend* fact about the join preview
endpoint, not a client one. `/how-it-works` changed that: it is the explainer, it carries no player,
event or score data, and it has to be readable by somebody who has just been handed an invitation
and does not yet have an account.

So `App.tsx` now has two top-level routes — the explainer, and a **pathless layout route** whose
element is `<RequireAuth><Outlet /></RequireAuth>` wrapping everything else. Every existing path is
untouched inside it. Deliberately *not* a second `<Routes>` under a `path="*"`: descendant routes
re-base every child path against the parent match, which is a quiet way to break fourteen working
URLs for one new page.

`src/routes.test.tsx` is the only test that renders `App` rather than a screen, and it exists for
this: the explainer resolves signed out, and `/t/:id` and `/join/:code` still do not. Both failure
modes are silent otherwise.

### Help lives beside the screen it explains

`features/help/content.ts` holds every word of the explainer and of the per-screen panels, with no
JSX — the same split as `format.ts`, and for the same Fast Refresh reason. It also makes the one
thing here that rots silently testable: a `HelpPanel` links into the walkthrough by slug, and a
renamed step would still compile, still render, and land the reader on step one with no error
anywhere. `content.test.ts` checks every link.

`HelpPanel` is a `<details>`, so open/close, the keyboard and the screen-reader announcement are all
free. **Note it puts its prose in the DOM while closed**, which is why two existing tests moved from
`getByText` to `getByRole('heading', …)`: the panel on score entry previews the tie-break questions
in the same words the screen asks them in, so a plain text query now matches twice. Prefer the role
query on any screen carrying a panel.

### Auth: a verified token is not a profile row

This is the first thing that goes wrong against this API. A Supabase token proves identity, but the
`players` row is created lazily — until `POST /players` succeeds, every other `/players` route 404s.

`features/auth/session.tsx` does that once on the way in and `RequireAuth` holds the app back until
it has. Two ordering details there look incidental and are not:

- **The referral code is read off the URL before the magic-link round trip**, which discards the
  query string. `captureReferral` / `takeReferral` exist for that gap alone.
- **`takeCallbackError` is memoised, and is used as a lazy `useState` initialiser.** StrictMode calls
  the initialiser twice, and only the first call takes the error off the URL; without the memo the
  second sees a clean URL and the error vanishes.

`lib/supabase.ts` pins `flowType: 'implicit'` rather than inheriting it. It is the SDK's current
default and everything here assumes it — the callback is read out of the fragment and there is no
`exchangeCodeForSession` anywhere. If that default ever flips to PKCE, the link comes back as
`?code=`, the failure is swallowed by an internal debug-only `catch`, and login dies in production
with a green build.

Password sign-in lives behind `VITE_ENABLE_PASSWORD_LOGIN` (on unless set to `false`) and is
temporary — see "Important Context" in `../CLAUDE.md` for why, and when it comes off.

### The pure modules, and the line they must not cross

Four modules are plain data in, plain data out, each with a `.test.ts` beside it, mirroring the way
`scoring.py` and `grouping.py` are pure on the server:

- **`features/scoring/cascade.ts`** — what to ask the group *next*. It never decides who won a hole;
  the server does (ADR-002). It has to remember what has already been asked, because a group reaches
  the longest-drive question only by *declining* the pin one ("none of us reached the green") and
  nothing is sent to the server in that case, so the response cannot express it. That is what `Asked`
  is for.
- **`features/tournaments/knockout.ts`** — bracket arithmetic for telling an organiser what their
  event will look like. Advice only: it mirrors `group_sizes` (ADR-004) so a number can be shown
  *before* anyone commits, which is the last moment the field can still change. The server's draw is
  authoritative.
- **`features/rounds/loop.ts`** — sorts a group's holes by `sequence`, **never** by hole number. A
  shotgun loop wraps the turn (ADR-011), so the group starting on the 17th plays 17, 18, 1; sorting
  those by number reads "1, 17, 18" and sends them to a tee three holes away with another group
  already on it.
- **`features/tournaments/when.ts`** — `scheduled_at` is an instant with an offset;
  `<input type="datetime-local">` reads and writes a naive local wall-clock string. Converting by
  hand in a component is where an 8:30am tee time becomes 6:30pm and the reminder fires on the wrong
  day.

`features/tournaments/format.ts` is separate from its components for a different reason: React Fast
Refresh only reloads a file cleanly when it exports components alone.

### TypeScript and build settings that reject valid-looking code

- **`erasableSyntaxOnly`** (`tsconfig.app.json`) rejects any type-directed syntax that emits runtime
  code — no `enum`, and no constructor parameter properties. `ApiError` declares its fields and
  assigns them in the body for exactly this reason; writing `constructor(readonly status: number)`
  fails to compile.
- **`verbatimModuleSyntax`** means type-only imports must say `import type`.
- **`noUnusedLocals` / `noUnusedParameters`** are on, so a stubbed-out parameter is a build failure,
  not a warning.
- **`App.tsx` narrows route params in small wrapper components.** `useParams` gives
  `string | undefined` for a param the path cannot have matched without, so each route has a wrapper
  that checks and redirects. That is why no screen carries a `!` or an impossible branch — keep new
  routes to the same shape.
- **`npm run build` fails when the `VITE_*` config is absent** — `requireEnv()` in
  `vite.config.ts`, backed by `build-env.ts`. It exists because the site once went live as a blank
  page built from nothing. It is **`apply: 'build'` only**, and that is load-bearing:
  `vitest.config.ts` imports the same config and `vite dev` reads it on every start, so a check
  outside that guard would make a missing `.env` break the test suite instead of the build.
- **`vitest.config.ts` is a separate file** because Vitest 4 no longer widens Vite's `UserConfig`
  with a `test` key — putting it in `vite.config.ts` is a type error, not a warning.

### The PWA, and what it deliberately does not cache

`VitePWA` precaches the shell only. **There is no runtime caching of API responses**, by decision:
ADR-005 defers offline sync, and a service worker quietly serving a stale leaderboard is worse than
an honest error, because a player would trust a board that had stopped moving.

`public/_headers` is copied into the assets directory and read by Workers. `/sw.js: no-cache` is the
one header there whose absence is a bug rather than missing hardening — `registerType: 'autoUpdate'`
only works if the browser can see that `sw.js` changed, and an edge-cached one pins players to an old
build. There is deliberately no CSP yet: a correct `connect-src` has to name both the Supabase
project and the Fly API, and a wrong one breaks magic-link login outright rather than degrading.
`docs/DEPLOYMENT.md` has it as a post-deploy step.

### Testing

`src/features/screens.test.tsx` renders **every** screen against fixtures captured from a running
backend. It is not a substitute for clicking through, but it catches the class of bug that shows a
player a white screen on a tee box — a bad destructure, a missing provider, a route that never
resolves.

Mock `lib/api`, not `fetch`: `vi.mock('../lib/api')` with `importActual` so `ApiError` stays real
while `api.get` / `api.post` are spies. Mock `lib/realtime`'s `subscribeToTournament` to a no-op
unsubscribe in anything that renders a leaderboard. `src/test/setup.ts` is only jest-dom.

Keep types in `src/lib/types.ts` in step with `backend/app/schemas/` by hand — and note that
tournament status values are **UPPERCASE** on the wire (`REGISTRATION_OPEN`); lowercase is a 422.
