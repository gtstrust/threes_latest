# CLAUDE.md — Threes Golf Platform

## Project Overview

Threes is a short-form competitive golf platform where players compete over 3-hole loops instead of traditional 18-hole rounds. The platform manages tournaments (round-robin and knockout — see ADR-012), casual "fun rounds," real-time leaderboards, and player profiles.

**MVP Target:** Corporate Golf Days — structured events where an organiser controls the entire course.

**MVP is a lean validation build** — web-only, no native apps, no AI features, no offline-first sync. See [`THREES_STRATEGY.md`](./THREES_STRATEGY.md) for the rationale and [`ROADMAP.md`](./ROADMAP.md) for what's Phase 1 vs Phase 2. The goal is to run one real corporate golf day, paid for via the per-event organiser fee, before investing in the full-featured build.

## Current Implementation Status

**Phase 1 and Phase 2 are both code-complete, backend and frontend.** The remaining milestone is
the thing itself: running one real corporate golf day.

Two files own status, and this one deliberately does not duplicate them — the copies drifted apart
once already:

- **[`ROADMAP.md`](./ROADMAP.md) is the source of truth for what is built** and what each phase
  covers. Check it before assuming a feature is missing.
- **[`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) is the source of truth for what is deployed**, and
  is the runbook. Note that the backend is live — a bad migration is a production problem now, not
  a local one.

Within `docs/`, only `DEPLOYMENT.md` and `SCREENS.md` are written — `ARCHITECTURE.md`, `API.md`
and `SECURITY.md` in the structure below are still target layout.

**The ADRs live in this file**, under "Architecture Decisions" below — not in `docs/`. ADR-001
through ADR-012 are cited all over the codebase, tests and commit messages, and this is the only
place they resolve to. **ADR-013 is cited by nothing yet** — it records the decided shape of Phase 3
handicaps rather than describing code that exists, and is written down so the answer is ready when
an organiser first asks for it.

See [`backend/CLAUDE.md`](./backend/CLAUDE.md) for backend-specific commands, the auth/JWT model,
and implementation gotchas (e.g. new models must be registered in `app/models/__init__.py` or
Alembic autogenerate silently no-ops), and [`frontend/CLAUDE.md`](./frontend/CLAUDE.md) for the
client's — the query-key/realtime invalidation contract, the profile-provisioning gate, and the
tsconfig settings that reject valid-looking code.

## Repository Structure

```
threes/
├── backend/                  # FastAPI Python backend
│   ├── app/
│   │   ├── api/              # Route handlers (routers)
│   │   │   ├── auth.py           courses.py      players.py
│   │   │   ├── tournaments.py    participants.py rounds.py
│   │   │   ├── groups.py         scores.py       leaderboard.py
│   │   │   ├── fun_rounds.py     join.py         # Phase 2
│   │   │   └── internal.py       # cron-only, X-Cron-Key auth
│   │   ├── core/             # config.py, db.py, deps.py, errors.py, http.py, security.py
│   │   ├── models/           # SQLAlchemy ORM — 12 tables across 8 modules
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic layer
│   │   │   ├── scoring.py        # Points engine + leaderboard ranking (pure)
│   │   │   ├── score_entry.py    # Persists what scoring.py decides
│   │   │   ├── leaderboard.py    # Standings — zero-fills the field, then ranks
│   │   │   ├── tournament.py     # Tournament state machine
│   │   │   ├── grouping.py       # Draw: group sizes + shotgun loops (pure)
│   │   │   ├── round.py          # Round lifecycle — draw + field + course
│   │   │   ├── advancement.py    # ADR-012 knockout verdicts, written at complete_round
│   │   │   ├── realtime.py       # ADR-010 broadcast (NullNotifier by default)
│   │   │   ├── course.py         participant.py  player.py
│   │   │   └── fun_round.py      join_code.py    reminders.py  mail.py  stats.py
│   │   ├── repositories/     # Database access layer
│   │   └── main.py           # FastAPI app entry point
│   ├── migrations/           # Alembic migrations
│   ├── scripts/              # dev_token.py, check_db_url.py, demo_tournament.py
│   ├── tests/                # ~360 tests across 23 files; needs a real Postgres
│   ├── pyproject.toml        alembic.ini    README.md   CLAUDE.md
│   └── Dockerfile            fly.toml       docker-compose.yml
├── frontend/                 # React + Vite web app (PWA)
│   ├── src/
│   │   ├── features/         # Feature-first, mirroring the backend's slices
│   │   │   ├── auth/  tournaments/  rounds/  scoring/  leaderboard/  courses/
│   │   │   └── fun-rounds/  join/  invite/  referrals/  stats/     # Phase 2
│   │   ├── lib/              # env, api, supabase, realtime, queries, theme, types
│   │   ├── components/       # ui.tsx — shared Page/Loading/ErrorNote primitives
│   │   ├── test/
│   │   └── App.tsx           # every route is declared here
│   ├── public/               # _headers, PWA icons
│   ├── build-env.ts          # build-time VITE_* guard (see vite.config.ts)
│   ├── wrangler.jsonc        # Cloudflare Worker (static assets, SPA fallback)
│   ├── .node-version         # 22
│   └── package.json          vite.config.ts  vitest.config.ts  README.md  CLAUDE.md
├── docs/
│   ├── DEPLOYMENT.md         # the runbook, and what is deployed
│   └── SCREENS.md            # every screen by role, and the gaps — sourced from `notes`
│       # ARCHITECTURE.md, API.md, SECURITY.md are still target layout
├── .github/
│   └── workflows/
│       ├── backend-ci.yml       frontend-ci.yml
│       ├── deploy-backend.yml   # manual (workflow_dispatch) Fly deploy
│       ├── reminder-sweep.yml   # manual; the hourly cron is commented out
│       └── claude.yml           claude-code-review.yml
├── CLAUDE.md                 # This file — including all thirteen ADRs
├── ROADMAP.md
└── THREES_STRATEGY.md
```

There is no root `README.md` and no `CONTRIBUTING.md`; `backend/README.md` and `frontend/README.md`
are the per-package entry points, and the contribution conventions are under "Coding Conventions"
below.

Note `docker-compose.yml`, `Dockerfile` and `fly.toml` live in **`backend/`**, not at the root —
the compose file's build context and the Docker build context are both that directory.

## Development Commands

Each package documents its own commands, and this section deliberately does not restate them —
they are the fastest-drifting thing in the repo and the copies multiply quietly:

- **[`backend/CLAUDE.md`](./backend/CLAUDE.md)** — setup, `pytest`, `ruff`, `mypy`, Alembic.
- **[`frontend/CLAUDE.md`](./frontend/CLAUDE.md)** — `npm` scripts, and the tsconfig and Vite
  settings that reject valid-looking code.

What is only true at this level:

```bash
cd backend && docker compose up -d   # compose, Dockerfile and fly.toml live HERE, not at the root
                                     # Postgres on host port 5433 (not 5432) + API on :8000
cd frontend && npm run dev           # :5173, strictPort — see below
```

- **The backend tests need Postgres running, always**, even the pure ones (`test_scoring.py`,
  `test_grouping.py`): `tests/conftest.py` connects at module import time.
- **CI runs two checks no local command does** — `ruff format --check .` and `alembic upgrade head`.
  A locally clean `ruff check` can still fail CI on formatting, and a model change with no migration
  fails there rather than here.
- **The frontend dev port is fixed at 5173** because that origin is in the backend's `CORS_ORIGINS`
  and Supabase's redirect allow-list. `strictPort` makes a second dev server fail rather than slide
  to 5174 and fall out of both.

### Deployment

`docs/DEPLOYMENT.md` is the runbook and records the failure modes already hit; this is only the shape
of it.

- **Backend → Fly.io** (Sydney). `fly deploy` from `backend/`, or run the manual **Deploy Backend**
  workflow. Migrations are not a deploy step: `fly.toml`'s `release_command` runs
  `alembic upgrade head` against the new image before it takes traffic.
- **Frontend → Cloudflare Workers** (static assets, not Pages). Deployed by Cloudflare's dashboard
  Git integration — **there is no frontend deploy workflow**. The `VITE_*` values belong in the
  build variables, not the Worker runtime bindings, because Vite inlines them at build time.
- **Supabase** holds the database and auth. The magic-link redirect allow-list needs `/**`, not `/*`.

## Architecture Decisions

### ADR-001: All data flows through FastAPI
The client does NOT query Supabase directly for data (except Auth and Realtime subscriptions). All CRUD operations go through FastAPI endpoints. This ensures consistent business logic, validation, and audit logging.

### ADR-002: Scoring engine is server-side only
All points calculation and tie-breaking happens on the backend. The client submits raw strokes; the server returns calculated results. This prevents score manipulation and ensures consistency.

### ADR-003: Tournament state machine
Tournaments follow a strict state machine: `CREATED → REGISTRATION_OPEN → REGISTRATION_CLOSED → ROUND_IN_PROGRESS → ROUND_COMPLETE → TOURNAMENT_COMPLETE`. Invalid transitions are rejected by the API.

### ADR-004: Groups of 3, with a pair or a fourball to absorb the remainder
Three is the format, so the draw makes groups of 3 wherever it can. The other two sizes exist only to place players a clean split would leave over: a remainder of two becomes a **pair** (5 is 3+2), and a remainder of one is folded into a **fourball** (7 is 3+4). A group of one is never produced — a lone player has nobody to play against, which is the whole reason the other sizes exist.

**Amended: four used to be 2+2.** Four is the standard social grouping, and four mates playing a loop together are one match. Splitting them into two pairs meant each hole was decided *within* a pair, so nobody actually played against the other two — a materially different competition from the one they thought they were in. Four players is now a single group of four, which falls straight out of the remainder-of-one rule rather than needing a special case.

Nothing in the scoring engine changed with it: `score_hole` takes a mapping of any size, and ADR-007's cascade is defined over "the players tied on strokes" without reference to how many there are. The cost is that a fourball has a slightly lower chance of an outright stroke winner than a three, so tie-breaks are asked marginally more often.

**Amended again: the target size is a per-event setting, defaulting to three.** `group_sizes` now
takes a target and `tournaments.group_size` carries it — 3 unless an organiser chooses 4.
Everything above is what a target of 3 does, unchanged; a target of 4 is the same sentence with the
divisor moved.

The generalised remainder rule is one sentence: **fill groups of the target size, give the leftover
players their own group, and if that would leave somebody alone, absorb them into the previous
group — splitting it as evenly as possible if that makes it larger than a group may be.** For a
target of three that is exactly the rule above: 3+1 is 4, which is allowed, so 7 is 3+4. For a
target of four it is not: 4+1 is 5, which is not a legal group, so it splits, and 5 is 3+2 while 9
is 4+3+2. Under either target no group is ever outside 2–4 and none is ever 1.

**Why four is now offered, having been argued against.** The objection stands and is not withdrawn:
dividing the whole field by four would turn every group into a fourball and quietly stop the
platform being about threes. What changed is that it is no longer *the platform* dividing — it is
one organiser making one explicit choice for one event, and the default is still three.

The reason they need it is arithmetic that only appears at scale, and it is ADR-011's: a true
shotgun start needs one starting tee per group, and a course has eighteen. Sixty-four players in
threes is twenty-one groups, which does not fit; in fourballs it is sixteen, which does. Refusing
fours would not keep that day about threes — it would put groups on shared tees teeing off
staggered, which is a different day again.

The cost is the one already recorded: a fourball has a slightly lower chance of an outright stroke
winner, so ADR-007's tie-break is asked marginally more often. Nothing in the scoring engine
changes.

### ADR-005: Offline-resilient score entry — Phase 3
Deferred from MVP (see `THREES_STRATEGY.md` §2). MVP score submission is online-only with retry-on-failure and a connectivity warning; no local persistence. Phase 3 revisits this only if pilot feedback shows on-course connectivity is actually a problem: pending submissions would be queued in IndexedDB, synced when connectivity returns, shown with a "pending" indicator, and the server would resolve conflicts (last-write-wins with timestamp). The service worker deliberately does **not** cache API responses today — a stale leaderboard served silently is worse than an honest error, because a player would trust a board that had stopped moving.

### ADR-006: Web-first for MVP
The app targets web only for MVP — no iOS/Android builds, no app store submission. This removes Fastlane, TestFlight, and Play Store review latency from the pilot's critical path. Native builds are Phase 3, pursued once the pilot validates the format and the fee.

**Amended: the stack is React + Vite, not Flutter.** Web-only was always the decision; what changed is what builds it. Three reasons, all specific to this app rather than general:

- **Flutter's advantage was already deferred by this very ADR.** It earns its keep by giving web *and* real native from one codebase. Deciding native is Phase 3 and conditional on the pilot means paying Flutter web's costs now for a benefit deliberately not collected yet.
- **Flutter web's weaknesses land on the critical path.** CanvasKit ships ~1.5–2MB before first paint and paints text to canvas — no find-in-page, weak accessibility, poor form autofill. The critical path here is a player opening a magic link on 4G, on a course, typing an email into a login field. Measured: the whole React app, including `supabase-js`, is **136 kB gzipped**.
- **This project is on Supabase's newest auth surface** — ES256 via JWKS and `sb_publishable_` keys. `supabase-js` receives these first; `supabase_flutter` trails. That is the one part of the client which cannot route through FastAPI, so being on the well-trodden path there matters more than anywhere else.

Native is kept open through the **PWA**, not through the framework: the app installs to a home screen, full-screen, with no store review. If the pilot shows store presence is genuinely wanted, Capacitor wraps the same bundle without a rewrite. That keeps this ADR's original bet intact — the pilot decides whether native is worth it, and nothing is paid for it beforehand.

The cost, accepted: if Threes later wants genuinely native apps with native feel, Flutter or React Native means writing the UI a second time. That is a Phase 3 problem, and it is smaller than shipping a slow pilot.

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

**A noted cost of that tie-break, made maximal by ADR-011.** Points are won *within* a group, over
the same three holes, so the primary sort is unaffected by which loop a group drew. Only the
tie-break is exposed: fewest total strokes compares a player who drew three par-3s with one who
drew three par-5s. A shotgun start makes this as large as it gets — with sixteen groups on eighteen
tees, no two groups play the same three holes.

Nothing is done about it, for the reason this ADR already gives when it rejected countback: every
fix needs data the organiser is not required to enter. `par` is deliberately nullable, so a
strokes-to-par tie-break would either break for courses that never entered par or silently switch
rules depending on how complete the data was — worse than honest imprecision. Two mitigations
already exist: several rounds with re-randomised groups spread the luck, and with integer points
over nine holes the tie-break separates far fewer players than it looks like it will.

**Forward compatibility with handicaps (Phase 3):** because the client submits only raw strokes (ADR-002) and points are always derived server-side, net scoring can be layered on later without changing the score-entry path or re-migrating stored scores. **ADR-013 collects that promise** — it runs this same cascade on net strokes, adding one optional argument and changing no level of it.

### ADR-008: Play statuses are owned by the round endpoints
`ROUND_IN_PROGRESS` and `ROUND_COMPLETE` cannot be set through `POST /tournaments/{id}/status`. Drawing a round and starting play are one action (`POST /tournaments/{id}/rounds`), as are finishing a round and ending it (`POST /rounds/{round_id}/complete`).

Allowing the status to move on its own would let a tournament sit in `ROUND_IN_PROGRESS` with no round drawn, or in `ROUND_COMPLETE` with a round still marked in progress — two sources of truth quietly disagreeing. The status endpoint still owns the registration transitions and `ROUND_COMPLETE → TOURNAMENT_COMPLETE`.

The readiness check for "no course set" moved into the draw for the same reason: it's now the only route to `ROUND_IN_PROGRESS`, so a copy left on the status endpoint would have been unreachable.

### ADR-009: Scores are stored in two tables — reported and derived
A scored hole is written to **two** tables. `hole_scores` is what the players reported: one row per participant, holding their strokes and the points those strokes earned them. `hole_results` is what the ADR-007 cascade made of it: one row per group per hole, holding the winner, which of the three levels decided it, and the tie-break answer if one was used.

The split is along the line between **fact and judgement**. Strokes are reported by the group and are the only thing the client sends (ADR-002); everything in `hole_results` is the server's conclusion about them. Keeping them in one table would mean a row that is partly evidence and partly verdict, with no way to say which columns a correction is allowed to touch.

**Points live on the score row, not in the result row.** They are per-participant, so they belong beside each participant's strokes — and it makes the leaderboard `SUM(points) GROUP BY participant_id` rather than a walk over per-hole verdicts. Points are stored rather than recomputed on read because ADR-007's `decided_by` exists so a disputed hole can be audited, and an audit trail that is recalculated on demand records nothing: it would only ever show what today's code thinks, not what the group was told on the day.

**The database enforces ADR-007, not just the service.** Three check constraints on `hole_results`: a tie-break participant may be stored only when `decided_by` names that level ("nothing is recorded unless it actually decided a hole"), and `winner_participant_id IS NULL` exactly when `decided_by = 'no_winner'` — holes are never halved, so the alternative to one winner is none, never a shared one. These are invariants of the format rather than of one code path, and a wrong row is worse than a rejected write: it is a player told they won a hole they did not.

**The cost, accepted:** the two tables can disagree if anything writes one without the other, so both are always written together by `ScoreEntryService`, and re-submitting a hole rewrites both. That single upsert path is also how a correction and a late tie-break answer arrive, which is why there is no separate endpoint for either.

**Rejected:** storing only strokes and calling `score_hole` on every read. It is simpler and cannot drift, but it discards `decided_by` — the record of *why* a hole was awarded — and makes the leaderboard recompute the entire field on every poll, which is exactly the read path M8 needs to be cheap.

### ADR-010: Realtime is a signal, not a feed — Broadcast, not Postgres Changes
Supabase Realtime tells clients the leaderboard moved. It **carries no scores**: the message is
`{"tournament_id": ..., "round_id": ...}` on topic `tournament:{id}`, and the client answers it by
refetching `GET /tournaments/{id}/leaderboard` — through FastAPI, where `require_can_view` already
decides who may see what.

**Broadcast rather than Postgres Changes.** Postgres Changes streams the `hole_scores` row itself
and gates delivery on **RLS** — a SELECT policy walking
`hole_scores → groups → rounds → tournaments → tournament_participants`, which is `require_can_view`
written again in SQL, covered by no Python test and free to drift. Broadcast keeps ADR-001 literally
true instead: no second read path to secure, and no data table carries an RLS policy.

**The signal is sent after the commit, not inside it.** `get_db` commits when its dependency
finalises, which FastAPI runs *before* background tasks, so `POST /groups/{id}/holes/{hid}/scores`
schedules the broadcast with `BackgroundTasks` rather than awaiting it — awaiting would ping
mid-transaction, and a client quick enough to act would refetch a board missing the very hole that
caused the refetch. That ordering is the framework's, not this code's, so `tests/test_realtime.py`
pins it.

**A failed broadcast is swallowed** — the hole is already committed, and a player who has just holed
a putt should not see an error because Supabase was slow. They find out on their next poll.

**Public channels, for now.** The topic is keyed by tournament UUID and the payload says nothing, so
an eavesdropper who guessed one would learn only that somebody scored. Private channels (RLS on
`realtime.messages`) are Phase 3, and are the reason the payload is worth keeping empty.

**Only score entry signals.** A draw or a completed round also change what a client should show, but
it learns those on its own refresh; `round_drawn` / `round_complete` wait until the frontend shows
they are needed.

### ADR-011: A shotgun start is one group per tee, and the loop wraps

Two ways of cutting the holes in play into loops, chosen per event by `tournaments.loop_style`:

- **`BLOCKS`** — the default, and everything that existed before. Disjoint triples, 1-3, 4-6, 7-9,
  so eighteen holes make six loops. Groups beyond the sixth share loops round-robin and tee off
  staggered.
- **`SHOTGUN`** — every hole in play is a starting tee. A group starting on hole *s* plays *s*,
  *s+1*, *s+2*, counted **modulo the holes in play**, so eighteen holes make eighteen loops and the
  group on the 17th plays 17, 18, 1.

The windows overlap, and that is the point: they cannot collide. At step *t* the group that started
on *s* is on hole *s+t*, so two groups share a hole only if they started on the same tee — one
procession round the course, which is what a shotgun is.
`test_no_two_groups_are_ever_on_the_same_hole` asserts that per step.

**Wrapping is what makes it eighteen loops rather than sixteen.** Without it the 17th and 18th could
only ever be finishing holes, which is the difference between a 64-player fourball field having a
tee each and not. The wrap is **generated, not typed**: the loop builder does the modular arithmetic
itself, so an organiser never expresses "17, 18, 1" and `_select_holes` is free to go on sorting a
selection into hole order — that sort is this design's input, not a limit on it.

**Groups may still outnumber tees** — twenty-two groups of three on eighteen holes. The existing
round-robin sharing in `allocate_loops` handles it unchanged, and no draw is refused for it.

**A selection's shape is checked against the style, so in the service rather than the schema.**
`BLOCKS` needs whole triples (a multiple of three); `SHOTGUN` needs only three holes, since every one
is a start — a shotgun over 1-10 is ten loops. The style lives on the tournament, so the request body
cannot tell which rule applies and a schema enforcing "a multiple of three" would 422 the common
shotgun case. The check sits in `RoundService._check_selection`, beside the other thing only the
service knows — whether the course has those holes — and answers **409** alongside it.

**Why two functions rather than a flag.** `build_loops` promises disjoint triples with the remainder
unused; `build_shotgun_loops` promises overlapping windows with every hole a start. A boolean would
give two contracts one docstring and one test table, so they stay separate behind a `plan_loops`
dispatcher, and `build_loops`' original tests survive untouched as the guard that the default did
not move.

### ADR-012: A knockout advances one player per group, and the verdict is stored

In a `KNOCKOUT` tournament each group is a match and **one player goes through**; the rest are out.
A 64-player fourball field is sixteen groups, then four, then one, then a champion — and 64 is the
largest bracket that fits three rounds, because 65 players need four.

**Who goes through is decided by four levels, stopping at the first that separates them:**

1. **Most points** over the loop.
2. **Fewest total strokes**, the same tie-break the leaderboard uses (ADR-007).
3. **Countback — whoever won the latest hole.** Holes nobody won are skipped, and so are holes won
   by a player already out on points or strokes: the question is which of *these two* took a hole
   later, the same scoping ADR-007 puts on closest to the pin.
4. **The organiser adjudicates.**

**The fourth level is rarer than it looks.** Points come *only* from winning holes, so co-leaders on
zero mean every hole was halved. Countback therefore settles every tie except a group that finished
completely all square — at worst, where the closest-to-pin question is never answered, about **4.6%
of fourball loops**. Nothing in the data can break that tie, and between a coin and a human the
human is better: they are standing there and can send the group back down the last hole.

**Countback rather than a play-off or a re-draw.** A play-off needs the field still on the course
and the light to hold; re-drawing both breaks the bracket's arithmetic — a round of four would
produce a final of five. Countback costs nothing: `hole_results` already holds one winner per hole
and `group_holes.sequence` the order.

**The verdict is stored, not recomputed.** `groups.advancing_participant_id` and
`groups.advanced_by` are written when the round completes — ADR-009's argument applied to a bracket:
an audit trail recalculated on demand would only show what today's code thinks, not who the field
was told had gone through. It also makes the next draw a read rather than a re-derivation.

**They are written at `complete_round`**, the moment a round's scores stop changing: `submit_hole`
already refuses a round that is not `IN_PROGRESS`, and there is no route back to it, so a verdict
can never fall out of step with the scores behind it. Completing a round does **not** refuse an
undecided group — the organiser has to be able to close the round while the field walks in — and the
refusal lands at the next draw, where it actually blocks something.

**Both columns are nullable, and a check constraint pairs them.** A round-robin group has neither,
forever, which is what makes it provable that nothing about a round robin changed. A knockout group
the cascade could not settle also has neither, and the next draw **refuses**, naming the groups
(409) rather than guessing or dropping the group from the bracket.
`(advancing_participant_id IS NULL) = (advanced_by IS NULL)` is enforced in the database for
ADR-009's reason: a half-written verdict is a player told they went through when they did not.

**The organiser fills a gap; they do not overwrite an answer.** Adjudicating a group that already
has a verdict is a **409**. They are the backstop for "nothing separated them", not an editor of
results — and a completed round's scores are closed, so there is no correction to serve either.

**The bracket is re-randomised each round, not seeded.** `build_groups` is order-preserving, so
carrying the previous round's order forward would put group 1's winner against group 2's every time
— a fixed bracket whose shape came from nothing but registration order surviving round one. Seeding
stays out of scope: there is no handicap or ranking to seed *from* until Phase 3.

**The last player is a refusal, not a transition.** When one player remains the draw answers **409**
naming the champion and pointing at the status endpoint; ending the tournament stays the organiser's
to press (ADR-003, ADR-008). Without the guard the draw reaches `group_sizes(1)` and answers "Cannot
form a group from a single player", which is true and unreadable as "you have a champion".

**The leaderboard ranks a knockout by how far a player got**, then points, then strokes. A champion
can finish *behind* a beaten finalist on cumulative points — one who advanced twice on strokes may
have won no holes at all — so a board ordered on points would report a different competition from
the one that was run. `rounds_survived` is the last round a player was drawn into plus one if they
won it, putting the champion alone at the top by construction. It defaults to 0, a constant leading
sort key for every round robin and therefore no change to one; on the wire it is **null** rather
than 0 there, because 0 would read as "went out immediately".


### ADR-013: Handicaps are pro-rated to the loop, and the cascade runs on net — Phase 3

Deferred, and **designed rather than built** — the phase boundary in `ROADMAP.md` still holds and
nothing below is implemented. This ADR exists because the answer is needed the first time an
organiser asks, and because the shape of it constrains things that *are* built: what `stroke_index`
is for, why `points` is integer-only, and why ADR-002 keeps raw strokes on the wire.

A player's **playing handicap** is an 18-hole figure. Pro-rate it to the loop —
`round_half_up(handicap × holes_in_loop ÷ 18)` — to get the **shots** they receive over those three
holes. Order the loop's holes by `stroke_index` ascending and deal the shots from the hardest: every
hole gets `shots ÷ len(loop)`, and the remainder goes to the hardest holes first. A player's **net
strokes** on a hole are their gross strokes minus the shots they received there. ADR-007's cascade
then runs **unchanged, on net**: fewest net strokes, then closest to the pin, then longest drive on
the fairway, each contested only among the players tied on net.

```
Loop = holes 7 (SI 3), 8 (SI 14), 9 (SI 11)     ->  difficulty order: 7, 9, 8

hcp  4  ->  round(4 x 3 / 18) = 1 shot   ->  7:1  9:0  8:0
hcp 22  ->  round(22 x 3 / 18) = 4 shots ->  7:2  9:1  8:1

Hole 7    gross   shots   net
  A         5       1       4
  B         8       2       6      -> A wins the hole, decided_by = 'strokes'
```

Integer arithmetic, no floats: `shots = (handicap * holes_in_loop * 2 + 18) // 36`.

**The cascade is not extended, and `DecidedBy` gains no member.** Level 1 is still "fewest strokes";
a handicap changes what a stroke counts as, not what the cascade is. That is the whole reason to
express this as net strokes rather than as a new tie-break level — the four labels stand, the three
check constraints on `hole_results` stand, and no `ALTER TYPE` is needed. **Points do not change
either**: 1 for the hole, 0 otherwise, no halves. `hole_scores` carries `CHECK (points IN (0, 1))`,
so a scheme scoring anything else would need a migration, and this one does not.

**Full allocation, not the matchplay difference.** The obvious alternative is the convention a
fourball actually plays to: the lowest handicap in the group goes off scratch and everyone else
receives the difference. It is truer to the game and keeps net close to gross. It breaks on the
leaderboard. Points are won *within* a group, so the primary sort survives either way — but the
tie-break is fewest total strokes **across the whole field**, comparing players who never met. Under
the difference model a 22-handicapper drawn against a scratch player receives four shots and the
same player drawn against three other 22s receives none: same player, same round, two different
stroke totals, one board. ADR-007 already accepts one imprecision in that tie-break; this would add
a second, structural rather than incidental, and invisible to the field. Full allocation gives a
player the same net total whoever they were drawn with, which is the property a cross-group board
needs.

**Allocating by `stroke_index`, having refused to depend on `par`.** ADR-007 rejected a
strokes-to-par tie-break because `par` is nullable, so the rule would "either break for courses that
never entered par or silently switch rules depending on how complete the data was". That argument is
about a rule applying to *every* event. This one applies only where an organiser has explicitly
turned handicaps on, and it fails **loudly and early**: the draw refuses (409) when any hole in play
has no stroke index, naming them, before anyone tees off. Nothing silently switches rules and no
scratch event is touched. The alternative — spreading shots evenly across the loop and ignoring
difficulty — needs no data the organiser must enter, but puts a lone shot on an arbitrary hole,
which every golfer in the group will notice.

**The draw refuses a participant with no handicap, too**, rather than defaulting them to 0. A
missing number almost always means "not entered yet", and 0 is the *hardest* handicap there is, so
guessing silently penalises exactly the player nobody remembered to ask. Handicaps freeze when the
field does — editable until `ROUND_IN_PROGRESS`, and fixed once play starts, for the same reason the
field is.

**Where the numbers live.** `tournaments.handicap_enabled` is the per-event opt-in, non-null with a
server default of false, exactly like `group_size` and `loop_style`.
`tournament_participants.playing_handicap` is nullable and per event — a playing handicap differs
between events, and a Virtual Player has no `players` row to carry one. **`hole_scores` gains
`strokes_received`**, the shots that player got on that hole, non-null defaulting to 0.

That column stores the *judgement*, not the net. Net is `strokes - strokes_received` — exact,
always, by arithmetic — so storing net as well would be two columns free to disagree, which is the
failure ADR-009 already warns about across its two tables. But the allocation itself *is* stored
rather than recomputed, for ADR-009's reason verbatim: an audit trail recalculated on demand "would
only ever show what today's code thinks, not what the group was told on the day". And **0 everywhere
on a scratch event is the proof that nothing moved** — the same device as `rounds_survived = 0` for
a round robin, and the null advancement columns on a round-robin group. A constant makes "the
existing behaviour is unchanged" provable rather than argued.

**Optional everywhere, and off by default — for fun rounds as much as tournaments.** Handicaps are
never implied by anything: not by a format, not by a course having stroke indices, not by one
participant having a handicap recorded. `handicap_enabled` is false unless somebody sets it, and a
scratch event is bit-for-bit the event it is today. A fun round is a `tournaments` row
(`kind = FUN_ROUND`), so it inherits the column the same way it inherits the draw, the cascade and
the leaderboard — and `FunRoundService.start` delegates to `RoundService.draw_round`, so both
draw-time refusals apply to a fun round without a second implementation.

**Inheriting the column is not the same as being able to set it**, and this is the part easy to get
wrong: `FunRoundService.create` narrows its payload by hand to `name` and `course_id`, so a fun
round would carry `handicap_enabled` and have no way on earth to turn it on. `FunRoundCreate` has to
plumb it through explicitly, as does the host's setup screen.

**Who types the number differs between the two**, because the field is assembled differently. A
tournament organiser owns the field and sets each participant's handicap on it. A fun round has no
organiser managing anyone — mates join themselves by link — so a player supplies their own handicap
when they join, and the host supplies one for each Virtual Player they add. Same column, two doors.

**A fun round checks its stroke indices at setup, not at the draw.** `create` already validates the
hole selection immediately rather than deferring it, because deferring "would surface it at the
first tee, with the group already assembled". The identical argument covers a missing stroke index:
four mates who ticked handicaps and walked to the tee should not discover there that the course has
no indices. The draw's refusal stays as the backstop — it is the same check — but for a fun round
the honest place to fail is the setup form.

**Nothing about score entry changes**, which is ADR-002's promise being collected rather than a
convenience. The client goes on submitting raw strokes and only raw strokes; the server allocates,
decides and stores. `rank_leaderboard` and `decide_advancement` need no edit at all — both rank on
total strokes, and feeding them net is a substitution one layer down in the aggregate.

**Plus handicaps are out of scope, deliberately.** A +2 player pro-rates to `round(-0.33) = 0` shots
over three holes, so the column would carry a sign that never changes a result.
`playing_handicap` is constrained `BETWEEN 0 AND 54`.

**Net may be zero or negative**, and that is legal — a 3 with three shots is a net 0. The engine
goes on rejecting a *gross* stroke count below 1 and places no floor on net.

**The costs, accepted.** ADR-007's noted tie-break imprecision widens slightly: net totals are
compared across loops of differing difficulty *and* differing allocation, though the second part is
self-correcting, since shots are dealt by each loop's own indices. A handicap event depends on data
an organiser must enter, which nothing else on the platform does — contained by the draw's refusal
and by leaving scratch events alone. And every screen showing a stroke now shows two numbers: gross
is what the group reported and will argue about, net is what decided it, and neither silently
replaces the other.

**The prerequisite, easy to miss.** `stroke_index` has been accepted by `PUT /courses/{id}/holes`
since migration `0002` and is **null in every row**, because no screen has ever sent one — the
course setup posts bare hole numbers. A course hole editor (`docs/SCREENS.md` #4) is therefore a
hard dependency of this ADR, not a nicety alongside it.

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

### TypeScript (Frontend)

- **TypeScript strict**, React 19, Vite
- Feature-first folders under `src/features/`; shared plumbing in `src/lib/`
- Naming: `kebab-case` or `PascalCase` for files matching their default export, `camelCase` for variables/functions, `PascalCase` for components and types
- Server state lives in TanStack Query, not in `useState`. There is almost no client state — the realtime signal is a cache invalidation
- **`supabase-js` is for auth and the realtime subscription only.** Never `.from(...)`: every byte of data comes through FastAPI (ADR-001), and the tables carry deny-all RLS so such a call returns nothing rather than failing loudly
- Types in `src/lib/types.ts` mirror `backend/app/schemas/`, hand-written. If that file outgrows a screen, generate from `/openapi.json` rather than letting it drift
- No business logic in components — the scoring cascade belongs in a tested module
- Plain HTML form controls wherever possible: autofill, the email keyboard and password managers all work for free, and that is most of what makes the app usable one-handed outdoors

### General

- Commit messages follow Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`
- Branch naming: `feat/tournament-creation`, `fix/score-validation`, `docs/api-spec`
- All environment variables in `.env` files (never committed)
- Secrets in environment variables, never in code

## Environment Variables

### Backend (.env)

Only these are read (`app/core/config.py`; `extra="ignore"`, so anything else in `.env` is
silently dropped rather than rejected). No `ANTHROPIC_API_KEY` — AI generation is Phase 3.

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-secret-key            # sb_secret_… — a publishable key breaks the broadcast
SUPABASE_JWT_SECRET=your-jwt-secret     # a random local string, NOT a Supabase value
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5433/threes_dev
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
APP_URL=http://localhost:5173           # what invite and reminder links point at
RESEND_API_KEY=your-resend-key          # outbound mail; unset = NullMailer
EMAIL_FROM=Threes <noreply@example.com>
CRON_SECRET=your-cron-secret            # X-Cron-Key on /internal; unset = those routes 404
```

The literal placeholder values in `.env.example` are load-bearing: `PLACEHOLDER_SETTINGS` in
`config.py` treats them as "unconfigured", which is how the app boots, and the test suite runs,
without a real Supabase project. `DATABASE_URL` is also coerced — a bare `postgresql://` is
rewritten to `postgresql+asyncpg://` rather than failing on a missing driver.

### Frontend (.env)

Vite inlines `VITE_*` at build time, so everything here ships to the browser in a
static asset. That is fine for these three — and is exactly why the **secret** key
must never appear among them. `src/lib/env.ts` refuses to start if it finds one.

```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_your-key-here
VITE_API_BASE_URL=http://localhost:8000
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
  optional because scoring never uses either today (ADR-007 is strokes alone), so an organiser can
  enter three hole numbers and start. `stroke_index` is present ready for Phase 3 handicaps, where
  it stops being optional: ADR-013 deals shots by it, so a handicap event whose holes lack one is
  refused at the draw. **Nothing populates it yet** — the course setup posts bare hole numbers, so
  every stored `stroke_index` is null. A course only needs the holes actually being played — a
  3-hole loop needs 3, not 18.
- **Round**: One stage of a tournament — a draw of groups all playing simultaneously. Carries its own
  status (`PENDING` / `IN_PROGRESS` / `COMPLETE`), distinct from the tournament's, because a
  tournament runs several rounds and its single status can only describe the current one.
- **Group**: 2–4 players playing one 3-hole **loop** together. One group = one match. Three is the
  format and the **default**, and a pair or a fourball absorbs whatever a clean split leaves over;
  an organiser may set `group_size` to 4 for one event, where the same remainder rule fills
  fourballs instead (ADR-004). The 2–4 range is the same either way — it is what the format can
  hold, not what the draw aims at.
- **Loop**: The 3 holes a group plays. **Each group gets its own loop** so the whole field tees off
  at once instead of queueing, and how many can do that is the event's `loop_style` (ADR-011).
  Under **blocks** the holes are cut into consecutive, disjoint triples, so 18 holes make 6 loops.
  Under a **shotgun** every hole in play is a starting tee and the loop wraps the turn, so 18 holes
  make 18 — a group starting on the 17th plays 17, 18, 1. Past whichever ceiling applies, groups
  share loops round-robin and tee off staggered. That's expected, not an error.
- **Playing part of a course**: the draw takes an optional `hole_numbers` — `[7, 8, 9]` for a match
  played inside a normal round. The tournament stays attached to the real course record; which holes
  were played is recorded per group in `group_holes`, so a club never needs a duplicate "holes 7-9"
  course. Omitted means the whole course. Under blocks a selection must be a multiple of 3, unlike
  the course-wide default, which simply leaves a remainder unused: a course is a record of what
  exists, a selection is a statement of intent, and silently dropping part of one would be the worse
  answer. Under a shotgun it need only be 3 or more, since every hole in it is somebody's starting
  tee. That rule depends on the event's style, so it is enforced by `RoundService` as a **409**
  rather than by the request schema as a 422 (ADR-011).
- **The draw**: Round 1 groups players in **registration order**, so people play with the mates they
  signed up alongside. Round 2 onwards shuffles. Both fall out of `build_groups` being deterministic
  and order-preserving — the ordering decision lives in `RoundService`, not the pure function.
- **Knockout**: a format where each group is a match and **one player goes through** (ADR-012). 64
  players in fourballs is 16 groups, then 4, then 1, then a champion. The field shrinks every round,
  so a later round's board is a subset of the tournament's — which is what `_round_field` was always
  written for. The alternative, and the default, is **round robin**: the whole field every round,
  and the leaderboard adds up.
- **Advancing player**: the group's verdict — who went through and which level of the cascade named
  them (`points` / `strokes` / `countback` / `organiser`), stored on the group rather than
  recomputed. Null on every round-robin group, and null on a knockout group nothing could separate,
  where the next draw refuses until the organiser says.
- **Champion**: not a new noun and not a column — the advancing player of the final round. The draw
  refuses once one player is left and names them; finishing the event stays the organiser's press.
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
- **Leaderboard Tie-break**: Level players are separated by fewest total strokes across the loop —
  **net strokes** where handicaps apply (ADR-013), gross everywhere else. (This replaces the earlier
  "countback on the hardest hole" rule, which needed a per-hole difficulty ranking the organiser
  would have had to enter.)
- **Playing Handicap**: A per-event allowance for one participant —
  `tournament_participants.playing_handicap`, 0–54, Phase 3 (ADR-013). Per *event* rather than per
  player because it can differ between them, and because a Virtual Player has no `players` row to
  carry one. Editable until `ROUND_IN_PROGRESS`, frozen with the field thereafter.
- **Shots Received**: How many strokes a player's handicap gave them on one hole —
  `hole_scores.strokes_received`, defaulting to 0. Pro-rated from the playing handicap to the loop,
  then dealt to the loop's holes hardest-first by `stroke_index` (ADR-013). Stored rather than
  recomputed, for ADR-009's reason: a shot allowance is a verdict about a player, and an audit trail
  recalculated later records only what today's code thinks. **0 on every row of a scratch event**,
  which is what makes it provable that nothing about one changed.
- **Net Strokes**: Gross strokes minus shots received. Derived, never stored — the arithmetic is
  exact, and a second column would be free to disagree with the first. What ADR-007's cascade
  compares on a handicap event, and what the leaderboard and ADR-012's level 2 rank on. Gross is
  still reported alongside it everywhere a stroke appears: gross is what the group counted, net is
  what decided it. Net may be zero or negative; a *gross* count below 1 is still rejected.
- **Fun Round**: A casual, non-tournament round between friends — **built** (Phase 2). Underneath it is a `tournaments` row with `kind = FUN_ROUND`, which is why it gets the draw, scoring and leaderboard for free. The tournament-management routes hide those rows behind a **404** (`reject_fun_round`), so the two never leak into each other's screens.
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
- **Join Code**: A short, revocable code on every tournament and fun round — `THR-8K2QF`, five
  characters from an alphabet with the ambiguous glyphs (`0`/`O`, `1`/`I`/`L`) removed, because codes
  get read aloud and retyped off a phone in daylight. Backs the invite link and its QR
  (`GET`/`POST /join/{code}`). Deliberately **not** the id: an id can never be revoked, and a printed
  link outlives its event.
- **Referral Code**: The same shape with a `MATE-` prefix, standing for the player who brought
  somebody in rather than for an event. The prefix is the point — a code pasted into the wrong box
  fails loudly instead of resolving to something unrelated. Captured from the URL *before* the
  magic-link round trip discards the query string, then passed to `POST /players`.
- **Player Cap**: `tournaments.max_players`, nullable — a cap is optional and its absence means
  uncapped, not zero.
- **Reminder**: A record that a reminder went out, in `tournament_reminders`, with a `kind` of
  `UPCOMING` (the scheduled sweep, once per event) or `MANUAL` (the organiser pressing the button,
  any number of times). The split is what makes the sweep idempotent without stopping the organiser.
  Delivered through `services/mail.py`; unset `RESEND_API_KEY` means a `NullMailer`, so nothing is
  sent locally or in tests.
- **Stats**: Per-player history under `/players/me/stats` and `/players/me/stats/courses`.
- **Organiser Fee**: The MVP monetisation model — **quoted per event and invoiced separately**, billed to the organiser rather than to individual players. There is no published rate and no tier table: the course is the largest input and its price is somebody else's to set, so it varies by venue, day and group size. See `THREES_STRATEGY.md` §1, which is the source for this. Deliberately **not modelled in the database** — no fee field, no amount — because one pilot does not need the platform to know what it cost. Stripe and per-player entry fees are Phase 3.
- **Sponsor**: A company or brand attached to a tournament (Phase 3). Sponsor name and logo are displayed on leaderboards and invitation emails.

## Important Context

- The MVP launches in **Australia**, targeting corporate golf days, and "Threes" is the 3-hole
  competition format — not a card game.
- **The scoring engine is the most critical business logic** and must be exhaustively tested.
- **A password sign-in path exists alongside magic link, temporarily**, behind
  `VITE_ENABLE_PASSWORD_LOGIN` (on unless set to `false`). Supabase's built-in sender allows two
  messages an hour, so the link frequently never arrives, and this is a bypass that needs no inbox.
  Supabase stores the password, not this app, and the flag comes off once custom SMTP is configured
  (`docs/DEPLOYMENT.md` §3). Until then, "no passwords are stored" is not true of this project.
- **Phase 3 is the do-not-build list**, and `ROADMAP.md` has the detail: handicaps / net scoring,
  native apps, offline sync, AI generation, standalone longest-drive and closest-to-pin
  competitions, social, gamification, private realtime channels, and the commercial build — Stripe,
  club/corporate accounts, sponsors. Longest drive and closest to pin are *captured* in MVP because
  ADR-007 needs them to break tied holes; what is deferred is treating them as competitions in their
  own right. Handicaps are deferred but no longer undecided — **ADR-013 settles the rule**; what is
  Phase 3 is building it.
