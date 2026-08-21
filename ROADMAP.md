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
| M4 | Grouping (ADR-004) + scoring engine — pure, exhaustively tested | ⬜ Blocked¹ |
| M5 | Rounds, round holes (stroke index), group generation | ⬜ |
| M6 | Score submission + points persistence (ADR-002) | ⬜ |
| M7 | Leaderboard + Supabase Realtime | ⬜ |

¹ M4 is blocked on two rules decisions — see [Open questions](#open-questions).

### Frontend

Not started; `frontend/` does not exist yet. Flutter **web only** for MVP.

- Magic-link auth + profile provisioning
- Organiser: create tournament, manage registration, generate rounds
- Player: score entry for own group, including entering scores for Virtual Players
- Live leaderboard

### Explicitly out of scope for MVP

Knockout **bracket progression** (seeding, elimination advancement). A corporate golf day needs
rounds plus a cumulative leaderboard; `format` is stored as a column but knockout advancement is
not implemented.

---

## Phase 2 — Post-pilot

Pursued only once the pilot validates the format and the fee.

- Native iOS/Android builds (ADR-006)
- Offline-first score sync — Hive-backed pending submissions, last-write-wins conflict
  resolution (ADR-005). Revisited **only if** pilot feedback shows on-course connectivity is
  actually a problem.
- AI invitation + summary generation
- Fun Rounds
- Longest drive, closest to pin
- Social friends, gamification

## Phase 3 — Commercial

- Stripe payment processing (per-player entry fees, replacing manual invoicing)
- Golf club / corporate accounts
- Sponsors (logo + name on leaderboards and invitation emails)

---

## Open questions

Both block the M4 scoring engine:

1. **How are ties on a hole scored in a group of three?** The documented rule — 1 pt for winning a
   hole, 0.5 for a halved hole, 0 for losing — is two-player language. If all three tie, is it 0.5
   each, ⅓ each, or 1 each? If two tie for lowest, do they take 0.5 each or 1 each? This decides
   whether points can be non-halves, and therefore the column type.

2. **Where does hole difficulty come from?** Countback is defined as performance on the
   hardest-ranked hole, but nothing currently records which hole that is. Current plan is a
   `round_holes.stroke_index` entered by the organiser, rather than a course reference table.
