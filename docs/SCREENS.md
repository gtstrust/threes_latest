# Screens, by role

Which screens exist, who each one serves, and what is missing. Checked against the user stories in
`notes` at the repo root, which is where the requirements below come from.

There is a designed version of this document published as an artifact:
<https://claude.ai/code/artifact/5acb1c5d-c609-4251-9f71-1cd7f4ccc614>. **This file is the source of
truth**; the artifact is a rendering of it, and the two are only worth keeping in step when
something material changes.

Every status here was read from the code rather than recalled. Phase labels follow
[`../ROADMAP.md`](../ROADMAP.md), which remains the source of truth for what is built.

## The four roles

Four roles get talked about. **Two of them exist.**

| Role | What represents it | Guard | Real? |
|---|---|---|---|
| **Player** | a `players` row, plus a `tournament_participants` row per event | `require_can_view`, `require_group_member` | yes |
| **Tournament organiser** | `tournament.organiser_id` — a hat worn per event, not a user attribute | `require_organiser` | yes |
| **Golf course owner** | `course.created_by` and nothing else | `require_course_owner` | thin |
| **Admin** | nothing — no role column on `players`, no `is_admin` in the backend | — | no |

Two things the table cannot show:

- **The roles overlap on purpose.** `TournamentPage` serves the organiser and the player from one
  route, branching on `isOrganiser`, because — in its own words — "a corporate organiser usually
  plays too". Splitting the roles into separate apps would fight the actual customer.
- **Role-as-a-per-event-hat is already a UI concept.** `HomePage` badges each event *Playing* or
  *Organising*, and an event you both organise and play appears once, badged *Organising*.

## The screens that exist

Twelve routed page components, plus `LoginPage`, which sits outside the router and is rendered by
`RequireAuth`. Thirteen screens across fourteen routes — `ScorePage` and `ScorecardPage` each serve
two, once for a tournament and once for a fun round.

### Shared — every signed-in golfer

| Route | Screen | What it does |
|---|---|---|
| — | `LoginPage` | Magic link, plus the temporary password bypass behind `VITE_ENABLE_PASSWORD_LOGIN` |
| `/` | `HomePage` | "Your golf" — your events, each badged Playing or Organising; entry points to a new tournament or fun round |
| `/me` | `StatsPage` | Career totals, round by round, by course, display name, appearance |

### Player, at a tournament

| Route | Screen | What it does |
|---|---|---|
| `/join/:code` | `JoinPage` | The invitation — the event, the field, and one button: "I'm in" |
| `/t/:id` | `TournamentPage` *(player half)* | Your group, who you're with, your starting tee — or "You're out" in a knockout |
| `/t/:id/leaderboard` | `LeaderboardPage` | Player, Reached, Strokes, Holes. Refetches on the realtime signal |
| `/g/:groupId` | `ScorePage` | Strokes, then the tie-break conversation — closest to the pin, then longest drive |
| `/g/:groupId/card` | `ScorecardPage` | "How each hole went" — the group's card, every player's strokes per hole |

### Organiser

| Route | Screen | What it does |
|---|---|---|
| `/new` | `NewTournamentPage` | Name, maximum players, format |
| `/t/:id` | `TournamentPage` *(organiser half)* | "Run the day" — the field, add a player without a phone, invite card and QR, draw the round, remind the field, adjudicate an all-square group |
| `/t/:id/settings` | `TournamentSettingsPage` | Name, course, tee time, maximum players, group size (threes or fourballs), start style (blocks or shotgun) |

### Fun rounds — a player hosting their own

| Route | Screen | What it does |
|---|---|---|
| `/rounds/new` | `NewFunRoundPage` | What are you playing, and which three holes |
| `/r/:id` | `FunRoundPage` | Who's in, start, leaderboard, finish |
| `/r/:id/leaderboard` | `FunRoundLeaderboardPage` | The same board, scoped to the round |
| `/r/:id/g/:groupId` | `ScorePage` *(reused)* | Identical score entry, with a back link to the fun round |

### Two structural facts, because the question was about mobile

- **There is no navigation chrome.** No tab bar, no drawer. Every screen is a `Page` — a title, an
  optional back link, and actions — reached by back link or deep link. The short paths are
  deliberate: they get texted on the day and read aloud on a tee.
- **There is not one media query in 832 lines of CSS.** The app is mobile-only by construction, so
  "which mobile screens" is simply "which screens". It also means **print** is the one output
  format with no support whatsoever.

## Checked against `notes`

### The opening list

| Story | Status | Where it lives |
|---|---|---|
| Create a tournament | built | `/new` |
| Invite players to tournament | built | Join code, link and QR on `/t/:id` |
| Player accept **or decline** | partial | Accept only — `JoinPage` offers "I'm in" and nothing else |
| Run tournament (dashboard) | built | "Run the day" on `/t/:id` |
| Remind players of tournament | built | "Remind the field", plus the scheduled sweep |
| Player can watch videos about Threes | **missing** | No help, rules or explainer content anywhere in the app |
| Player plays hole | built | `/g/:groupId`, including the tie-break cascade |
| Player finishes 3 holes | built | Scorecard, then the organiser completes the round |
| Winners | built | Leaderboard, and "Goes through" per group in a knockout |
| User referrals system | built | "Bring a mate" on `/me`, with the `MATE-` code |

### As a golfer, at a tournament

| Story | Status | Where it lives |
|---|---|---|
| See which group I am in | built | "Your group" on `/t/:id` |
| See who I'm playing with | built | Same card |
| See which hole I'm starting on | built | Sorted by loop `sequence`, so a wrapped shotgun reads 17, 18, 1 — not 1, 17, 18 |
| See my group leaderboard | partial | The scorecard shows the group's holes; there is no group-scoped ranking |
| See tournament leaderboard | built | `/t/:id/leaderboard` |
| See my tournament stats | partial | Position, points and strokes per event exist — but on `/me` afterwards, not on the event while it is live |

### As a golfer, in a fun round

| Story | Status | Where it lives |
|---|---|---|
| Start a round, select a course | built | `/rounds/new` with the course picker |
| Invite a Threes player | built | Join code, same as a tournament |
| Join a non-mobile player | built | Virtual players — scored by someone else in the group |
| Enter scores, view the scoreboard, see opponents' scores for a hole | built | `ScorePage` and `ScorecardPage`, both reused unchanged |
| Quick leaderboard, finish round | built | `/r/:id/leaderboard` and "Finish" |
| See my stats, see my previous rounds | built | "Career" and "Round by round" on `/me` |
| Track improvement by course, overall | built | "By course" on `/me` |
| Track improvement **by hole** | **missing** | Stats aggregate to career, event and course — never to a hole |
| Win badges | **missing** | No achievements model. Gamification is Phase 3 |

### As a tournament organiser

| Story | Status | Where it lives |
|---|---|---|
| Provide link / QR code to join | built | Invite card, with a revocable code |
| Set a limit on players | built | Maximum players, on creation or in settings |
| Generate groups on the fly, each round | built | Draw a round from `/t/:id` |
| Knockout — regenerate groups of winners only | built | One player advances per group; the next draw takes only those (ADR-012) |
| Round robin — regenerate using all players | built | The default; the whole field is redrawn and reshuffled |
| Set rules for regeneration | partial | Group size and start style only. No seeding, no "keep these players apart" |
| See overall leaderboard | built | `/t/:id/leaderboard` |
| Print overall leaderboard | **missing** | No print stylesheet exists — the page prints as the screen, dark ground and all |

## Screens required

Ranked by pilot risk, not by effort. The milestone is running one real corporate golf day, so a
screen the day goes wrong without outranks a screen that is merely good.

### 1. How Threes works — player, before the pilot

There is no help text anywhere in the app. A guest scans a QR on the first tee, signs in, lands on
an invitation, taps "I'm in", and the next thing they see asks how many strokes they took — with no
explanation of the three-hole format, that only one player can win a hole, or why it is suddenly
asking which of them was closest to the pin.

Highest-risk gap on this list, because it fails at the worst moment: a corporate guest who has never
heard of the format, standing on a tee, holding somebody else's phone. `notes` frames it as video;
text and a diagram ship sooner and work without signal.

**Backend needed:** none. Static content, reachable from the home screen *and* from the invitation,
so it is available before joining as well as after.

### 2. Printable leaderboard and draw sheet — organiser, before the pilot

Explicitly in `notes`, and completely absent — there is no `@media print` rule in the stylesheet, so
printing today gives the mobile screen on paper, dark ground included. A golf day needs the draw
pinned up at the first tee and the final board handed over at presentation.

Worth deciding at the same time: `display_name` is snapshotted at registration, and a corporate
field self-registering by magic link produces a board that prints
`firstname.lastname@company.com` down the page — a hazard `StatsPage` already notes.

**Backend needed:** none. This is a print stylesheet and a layout decision, not a route.

### 3. Decline an invitation — player, before the pilot

`JoinPage` has one button. A player who cannot make it has no way to say so, so the organiser cannot
tell "hasn't answered" from "isn't coming" — which is the distinction the reminder sweep should act
on, and what an organiser needs the morning they confirm numbers with the club.

**Backend needed:** a response state on the participant record, and the organiser's field list
updated to show it. Small, but not a screen-only change.

### 4. My courses — course owner, Phase 2

The screen that turns "course owner" from an accident into a role. A course can be created today,
but only from inside the flow of setting up an event, and there is no way back to it afterwards — so
a hole entered with the wrong par or stroke index stays wrong forever, on shared reference data that
other organisers will point their events at.

**Backend needed:** none. `require_course_owner` and `PUT /courses/{id}/holes` are built and tested;
nothing in the UI reaches them outside event setup — and `useUpsertHoles` does not even type
`stroke_index`, so the narrowing is on the client alone.

**This screen is a hard dependency of handicaps (ADR-013)**, which deals a player's shots by stroke
index. Until something can enter one, no handicap event can be drawn. That promotes #4 from a
tidiness fix to a prerequisite for a named Phase 3 feature.

### 5. My event, while it is running — player, Phase 2

"See my tournament stats" is half-served: position, points and strokes for an event are computed and
shown, but on the profile, after the fact. During the day a player sees the whole field's board and
their own group's card, and nothing in between that answers "how am I doing".

**Backend needed:** none — the per-event figures are already in the stats history. This is a
placement problem, and could be a card on the tournament screen rather than a new route.

### 6. Split the organiser dashboard? — open question

`TournamentPage` is 479 lines and does roughly four jobs: the player's view, the field, the draw and
the day's controls. The case for splitting is that the organiser's half is operated under pressure,
on a phone, while sixteen groups wait.

The case against is written into the file and is a good one — the organiser usually plays too, and
two routes would mean an organiser-player switching screens to see their own tee. Recorded as a
question rather than a recommendation.

### 7. Badges and achievements — player, Phase 3

In `notes`, and deliberately deferred: gamification is Phase 3. Needs an achievements model, an
awarding rule per badge, and a screen. Worth keeping out of the pilot, where what is being validated
is whether the format and the fee work at all.

### 8. Improvement by hole — player, Phase 3

`notes` asks to track improvement "by hole, by course, overall"; two of the three are built. Per-hole
pairs naturally with handicaps — but note `stroke_index` is *accepted* on every hole rather than
captured on one: the API has taken it since migration `0002` and no screen has ever sent one, so
every stored value is null. Screen #4 is what would change that, and ADR-013 is what would read it.

## The two roles with no data model

Both are worth having eventually. Neither is a screen problem.

### Golf course owner

Today this is not a role, it is a footprint: whoever first typed a course name owns that record, and
a course is shared reference data any organiser can point an event at. "My courses" above makes that
footprint usable and needs nothing new underneath it.

A *real* course owner — a club, with staff who can each edit the club's courses and see events
booked at them — is a different thing, and it is the "golf club accounts" line in Phase 3. That
needs an organisation, a membership table, and an ownership check that looks past `created_by`.
Worth separating the two: the first is days of work and the second is not.

### Admin

There is no admin at any layer: no role column, no way to grant one, no guard to check one, no
screen. Building one means auth work before any UI, and for one pilot golf day the admin is a
developer with database access.

The one existing back door is deliberately not a UI and should stay that way: `/internal`
authenticates on `X-Cron-Key` rather than a JWT, and returns 404 when that key is unconfigured, so
it never advertises that it exists.

An admin console earns its place when there is a second organiser you cannot phone. Before that it
is a screen built for one user who already has `psql`.
