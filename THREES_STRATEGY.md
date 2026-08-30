# Threes — Strategy

> **⚠️ Mostly a stub.**
>
> `CLAUDE.md` and `ROADMAP.md` cite this file by section number as the source of truth for *why*
> the MVP is scoped the way it is, but it had never been written (and was linked as
> `../THREES_STRATEGY.md`, a path outside the repo). Most headings below still restate only what
> `CLAUDE.md` already asserts.
>
> **§1 is the exception — it records a real decision** and is now the source, with `CLAUDE.md`
> following it rather than the other way round.
>
> **The rest — market sizing, competitive positioning, the growth model — needs to be written by
> the team.** It has deliberately not been invented here.

---

## 1. Monetisation — the Organiser Fee

**Decided, for Phase 1 corporate days: the fee is quoted per event and invoiced separately.**

There is no published rate and no tier table. The largest input to what a corporate day costs is the
course, and that varies by venue, by day of the week and by group size — so any flat or tiered rate
would underprice the good venues and overprice the rest. Quoting per event is not a placeholder
until a rate exists; it is the answer while the course is somebody else's price to set.

What follows from it:

- **Billed to the organiser, not to individual players.** A corporate day is bought by one company
  for its guests; asking twelve clients each for a card would be a worse experience than the thing
  being sold.
- **Not collected in-app, and not modelled in the database.** No fee field, no amount, no invoice
  record. One pilot does not need the platform to know what it cost, and a column would be a schema
  commitment to a pricing model nobody has settled. Adding one later is cheap; unpicking a wrong one
  from live events is not.
- **Stripe and per-player entry fees remain Phase 3**, along with the rest of the commercial build.

**Still to be written:**

- What the fee has to clear to make a pilot worth running.
- Whether a published rate replaces per-event quoting once there is enough history to price from —
  and if so, what it is priced on, given the course cost is the part that moves.
- Why organiser-billed beats per-player entry fees beyond the convenience argument above.

## 2. Why the MVP defers offline-first sync

**What `CLAUDE.md` already commits to** (ADR-005):

- MVP score submission is online-only: retry-on-failure plus a connectivity warning, no local
  persistence.
- Offline-first is revisited in Phase 3 **only if** pilot feedback shows on-course connectivity is
  genuinely a problem.

**To be written:**

- The evidence behind the bet that connectivity is good enough at target venues.
- What the pilot should measure to settle it.

## 3. Why web-only for the MVP

**What `CLAUDE.md` already commits to** (ADR-006):

- The app targets web only — no iOS/Android builds, no app store submission.
- This removes Fastlane, TestFlight, and Play Store review latency from the pilot's critical path.
- Native builds are Phase 3, once the pilot validates the format and the fee.
- The stack is React + Vite, shipped as an installable PWA (ADR-006, as amended). A home-screen
  install gives most of what a player wants from an app without a store at all.

**To be written:**

- Whether players will accept a browser-based experience on-course. The pilot should measure
  this directly: how many install to the home screen, and how many bounce at the login screen.

## 4. Target market — Australian corporate golf days

**What `CLAUDE.md` already commits to:**

- MVP launches in Australia, targeting corporate golf days.
- These are structured events where an organiser controls the entire course.

**To be written:**

- Market size, how organisers are reached, and why this segment before casual players.

## 5. Post-pilot growth — invites, referrals, reminders, caps, stats

**What `CLAUDE.md`/`ROADMAP.md` already commit to** (Phase 2 — post-pilot engagement & growth):

- The next post-pilot investment is engagement & growth, not deeper platform features — those are
  Phase 3.
- The focused set: complete **Fun Rounds** (casual non-tournament play), **invite / join-links +
  QR**, **player caps**, **reminders**, **referrals**, and **per-player stats / history**.
- **Reminders** pull an outbound-email channel forward (there is none in the MVP); AI-generated
  invitation/summary *content* remains Phase 3.

**To be written:**

- Why this ordering — which of the six actually drives repeat events and referrals for corporate
  golf days, and which is a "nice to have" that could slip.
- What each is worth: does Fun Rounds widen the market beyond corporate days, or mainly deepen
  engagement within them? Does a referral loop realistically reach *organisers*, or only players?
- What the pilot should measure to confirm the bet before this phase is funded.
