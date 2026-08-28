# Roadmap

Phase boundaries are set by [`THREES_STRATEGY.md`](./THREES_STRATEGY.md); this file tracks what
that means concretely and where the build currently is. Domain terms used here are defined in
[`CLAUDE.md`](./CLAUDE.md).

**Phase 1 milestone:** run one real corporate golf day, with the organiser paying the per-event
fee. Everything below Phase 1 is deferred until that has happened.

---

## Phase 1 — MVP (lean validation build)

Web-only. No native apps, no AI features, no offline-first sync, no Fun Rounds
(ADR-005, ADR-006).

### Backend

| # | Milestone | Status |
|---|-----------|--------|
| — | Auth (Supabase magic-link JWT verification) | ✅ Done |
| — | Player profiles (get-or-create, read, update) | ✅ Done |
| M1 | Repo housekeeping — CI, lint, docs | ✅ Done |
| M2 | Tournament domain + ADR-003 state machine + organiser authz | ✅ Done |
| M3 | Participants, including Virtual Players | ✅ Done |
| M4 | Grouping (ADR-004) + scoring engine (ADR-007) — pure, exhaustively tested | ✅ Done |
| M5 | Courses and holes; tournaments linked to a course | ✅ Done |
| M6 | Rounds, groups, and the shotgun-start draw | ✅ Done |
| M7 | Score submission + points persistence (ADR-002) | ✅ Done |
| M8 | Leaderboard — per round and cumulative | ✅ Done |
| M9 | Supabase Realtime — the refetch signal | ✅ Done |

M7 wired `score_hole` up: strokes come in per group per hole, the engine decides the hole, and
both the strokes and the decided result are persisted (`hole_scores`, `hole_results`). M8 then
wired up `rank_leaderboard`, the last uncalled part of the engine, reading what M7 writes as
`SUM(points) GROUP BY participant_id` — `GET /tournaments/{id}/leaderboard` for the cumulative
board and `GET /rounds/{id}/leaderboard` for one round. **The whole backend scoring path is now
real**: no 501 stubs, no unreachable functions.

Both boards list the *whole field*, including players yet to score, since a board missing half
the field early in the day reads as a bug rather than as "they haven't finished a hole yet".

M9 was the last backend milestone. Realtime only tells clients to refetch the endpoints above —
ADR-001 keeps the ranking server-side — so the message deliberately carries **no scores**:
`{"tournament_id", "round_id"}` on topic `tournament:{id}`, broadcast after each hole is scored.

**This entry previously specified `wal_level=logical` plus a publication on `hole_scores`, which is
Postgres Changes. That was wrong for what M9 is meant to do** — Postgres Changes streams the score
row itself and gates delivery on an RLS policy that would restate `require_can_view` in SQL. ADR-010
records the decision to use Broadcast instead. No data table gets an RLS policy, and no `wal_level`
change is needed. The anon key belongs to the *client*, in `frontend/.env`, not to this backend.

Done: `app/services/realtime.py`, wired into `POST /groups/{id}/holes/{hole_id}/scores` as a
background task so it fires after the transaction commits, with 17 tests in `tests/test_realtime.py`
covering when it fires, what goes on the wire, and that a failed broadcast can't fail a score.
Broadcasting is off unless `SUPABASE_URL` and `SUPABASE_KEY` hold real values, so local runs, the
suite and `scripts/demo_tournament.py` are unaffected.

**Verified live.** Against a stub HTTP server, a full demo run produced 17 broadcasts (12 holes plus
5 tie-break re-submits), one topic, two round ids, and no score data in any payload. Then against the
real project: a subscriber joined `realtime:tournament:{id}`, a hole was scored through the API, and
`leaderboard_changed` arrived carrying only the two ids. **M9 is closed** — what is left for a live
leaderboard is a client to subscribe with, which is `frontend/`.

A secret key (`sb_secret_…`) is required — a publishable key is rejected by the broadcast endpoint.

Scoring rules are settled — see ADR-007. Holes are never halved; a hole has one winner or none,
decided by strokes → closest to the pin → longest drive on the fairway. Points are integers.
The leaderboard breaks level players on fewest total strokes, so the organiser never has to enter
a per-hole difficulty ranking. `stroke_index` is still on `Hole` — nullable and unused by MVP
scoring — kept ready for Phase 3 handicaps.

### Frontend

**React + Vite (TypeScript)**, web only, shipped as an installable PWA. ADR-006 records why the
stack changed from Flutter; web-only itself was never in question.

| # | Slice | Status |
|---|-------|--------|
| 1 | Shell, magic-link auth, profile provisioning, PWA install | ✅ Done |
| 2 | Organiser: create a course and tournament, manage the field | ✅ Done |
| 3 | Organiser: draw a round, complete it, finish the tournament | ✅ Done |
| 4 | Player: see my group, enter scores, walk the ADR-007 tie-break | ✅ Done |
| 5 | Live leaderboard, refetching on the ADR-010 signal | ✅ Done |

**Not yet done: anyone has actually logged in.** The magic-link flow has never run
against the real project, because it needs the `sb_publishable_` key in `frontend/.env`.
Everything either side of it is tested, but the first click-through is still ahead.

Slice 4 is the one to get right: score entry is a conversation, not a form. Strokes go in, and if
they tie the API answers with `tied_participants` — the app then asks *only those players* who was
closest to the pin, and re-posts the same hole with the answer.

### Explicitly out of scope for MVP

Knockout **bracket progression** (seeding, elimination, advancement). A corporate golf day needs
rounds plus a cumulative leaderboard.

`KNOCKOUT` remains a value of the `tournament_format` database enum so the column won't need
migrating when brackets are eventually built, but **the API rejects it** — `SUPPORTED_FORMATS` in
`app/models/tournament.py` lists what `POST /tournaments` will accept. Accepting it would fail
silently: the event would run exactly like a round robin and the organiser would only discover
nobody was being eliminated partway through the day. Adding the value to `SUPPORTED_FORMATS` is the
single change needed to open it back up.

---

## Phase 2 — Post-pilot engagement & growth

Pursued only once the pilot validates the format and the fee. This phase is deliberately narrow:
the features that turn a one-off event into repeat play and word-of-mouth growth. Everything else
deferred at MVP is now Phase 3 (below).

| # | Workstream | Scope | Main dependency |
|---|-----------|-------|-----------------|
| 1 | **Fun Rounds — complete** | The whole casual, non-tournament flow: start a round, pick a course, invite Threes players, add non-mobile (virtual) players, enter hole scores, view the scoreboard and opponents' holes, a quick leaderboard, finish the round. | Reuses the pure engine (`services/scoring.py` `score_hole`, `services/grouping.py`) unchanged, but needs a `Round` **not** foreign-keyed to a `Tournament` — today every round is created via `RoundService.draw_round` on a tournament. That decoupling is the bulk of the work. |
| 2 | **Invite / join-links + QR** | Organiser generates a shareable join link and QR for a tournament (and for a fun round); joining by link instead of hand-shared UUID. | A join-token endpoint on the backend; a share/QR surface on the frontend. Today joining is by knowing the tournament id. |
| 3 | **Player caps** | An optional maximum field size per tournament, enforced at self-registration. | A `max_players` field on the tournament model/schema; a guard in `ParticipantService.self_register` (which enforces no maximum today). |
| 4 | **Reminders** | Notify players of an upcoming event (and, later, that scoring is open). | An email/notification channel — **none exists yet** (no `EMAIL_FROM`, no outbound mail). This is the one item that pulls new infrastructure forward. |
| 5 | **Referrals** | A referral loop so existing players bring new organisers/players. | Referral codes + attribution; overlaps with invites (#2) and the growth strategy stub. |
| 6 | **Per-player stats / history** | A player's previous rounds and improvement tracking — by hole, by course, and overall. | A stats/aggregation read path across tournaments; today the only aggregates are the two per-tournament leaderboard sums. |

## Phase 3 — Later

Everything else deferred, gathered into one bucket behind the Phase 2 growth work — deeper product
features alongside the commercial build. Pursued after Phase 2, and each planned on its own when
picked up.

**Product & platform**

- **Handicaps / net scoring.** ADR-002 keeps raw strokes as the only thing the client submits and
  derives all points server-side, so net scoring can be added without changing score entry or
  re-migrating stored scores. A per-event playing handicap belongs on the participant, not the
  player, since it can differ between events.
- Native iOS/Android builds (ADR-006)
- Offline-first score sync — pending submissions queued locally, last-write-wins conflict
  resolution (ADR-005). Revisited **only if** pilot feedback shows on-course connectivity is
  actually a problem.
- AI invitation + summary generation
- Standalone longest-drive and closest-to-pin **competitions** — own prizes and leaderboards. Both
  are already captured in MVP as ADR-007 tie-break inputs; what's deferred is treating them as
  contests in their own right.
- Social friends, gamification
- Realtime private channels (RLS on `realtime.messages`), the reason the broadcast payload is kept
  empty (ADR-010)

**Commercial**

- Stripe payment processing (per-player entry fees, replacing manual invoicing)
- Golf club / corporate accounts
- Sponsors (logo + name on leaderboards and invitation emails)

---

## Open questions

None currently blocking. Scoring rules were settled in ADR-007.

Worth revisiting after the pilot:

- **How often does "nobody wins the hole" actually fire?** It should be uncommon — the tie-breaks are
  contested only among the tied players, so a hole only goes unwon when those players genuinely can't
  be separated (typically none found the fairway). Worth confirming against real play before deciding
  whether the cascade needs a fourth level.
