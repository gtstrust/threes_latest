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
| M2 | Tournament domain + ADR-003 state machine + organiser authz | ⬜ Next |
| M3 | Participants, including Virtual Players | ⬜ |
| M4 | Grouping (ADR-004) + scoring engine (ADR-007) — pure, exhaustively tested | ⬜ |
| M5 | Rounds and group generation | ⬜ |
| M6 | Score submission + points persistence (ADR-002) | ⬜ |
| M7 | Leaderboard + Supabase Realtime | ⬜ |

Scoring rules are settled — see ADR-007. Holes are never halved; a hole has one winner or none,
decided by strokes → closest to the pin → longest drive on the fairway. Points are integers.
The leaderboard breaks level players on fewest total strokes, so no per-hole difficulty ranking
is needed and M5 no longer carries a `stroke_index`.

### Frontend

Not started; `frontend/` does not exist yet. Flutter **web only** for MVP.

- Magic-link auth + profile provisioning
- Organiser: create tournament, manage registration, generate rounds
- Player: score entry for own group, including entering scores for Virtual Players
- Live leaderboard

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

## Phase 2 — Post-pilot

Pursued only once the pilot validates the format and the fee.

- **Handicaps / net scoring.** ADR-002 keeps raw strokes as the only thing the client submits and
  derives all points server-side, so net scoring can be added without changing score entry or
  re-migrating stored scores. A per-event playing handicap belongs on the participant, not the
  player, since it can differ between events.
- Native iOS/Android builds (ADR-006)
- Offline-first score sync — Hive-backed pending submissions, last-write-wins conflict
  resolution (ADR-005). Revisited **only if** pilot feedback shows on-course connectivity is
  actually a problem.
- AI invitation + summary generation
- Fun Rounds
- Standalone longest-drive and closest-to-pin **competitions** — own prizes and leaderboards. Both
  are already captured in MVP as ADR-007 tie-break inputs; what's deferred is treating them as
  contests in their own right.
- Social friends, gamification

## Phase 3 — Commercial

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
