"""Points calculation engine — see CLAUDE.md ADR-007.

Pure and synchronous by design: no database access, no I/O, nothing async. Every
function here takes plain data and returns plain data, which is what makes the
platform's most critical business logic exhaustively testable without fixtures.
Persistence and orchestration belong in the service layer that calls this.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

ParticipantId = UUID

WINNING_POINTS = 1
LOSING_POINTS = 0


class DecidedBy(str, Enum):
    """Which level of the ADR-007 cascade produced a hole's result.

    Recorded alongside the result so the UI can explain *why* a hole was won
    ("won on closest to the pin") and so a disputed hole can be audited.
    """

    STROKES = "strokes"
    CLOSEST_TO_PIN = "closest_to_pin"
    LONGEST_DRIVE = "longest_drive"
    NO_WINNER = "no_winner"


@dataclass(frozen=True)
class HoleResult:
    """Outcome of one hole for one group. `winner` is None when nobody won it."""

    winner: ParticipantId | None
    decided_by: DecidedBy
    points: Mapping[ParticipantId, int]


@dataclass(frozen=True)
class LoopHole:
    """One hole of a loop, with the difficulty ranking shots are dealt by.

    Only the two fields allocation needs. Deliberately not the `Hole` model: this
    module takes plain data, and importing from `app.models` here would invert the
    dependency the whole codebase leans on.
    """

    hole_id: UUID
    stroke_index: int


def shots_for_loop(playing_handicap: int, holes_in_loop: int) -> int:
    """How many shots a handicap is worth over a loop of this length (ADR-013).

    A playing handicap is an 18-hole figure, so it is pro-rated: three holes of
    eighteen is a sixth of it. Rounded half up, and done in integers — a float
    here would make the boundary cases depend on binary representation, and 4.5
    shots has to land the same way every time.

    Eighteen is the divisor whatever the course holds, because that is what the
    handicap is quoted against. A club with nine holes entered does not halve
    everybody's allowance.

    Raises:
        ValueError: If the handicap is negative or the loop is empty.
    """
    if playing_handicap < 0:
        raise ValueError(f"A playing handicap cannot be negative; got {playing_handicap}")
    if holes_in_loop < 1:
        raise ValueError("Cannot pro-rate a handicap over a loop with no holes")
    return (playing_handicap * holes_in_loop * 2 + 18) // 36


def allocate_shots(
    handicaps: Mapping[ParticipantId, int],
    loop: Sequence[LoopHole],
) -> dict[ParticipantId, dict[UUID, int]]:
    """Deal each player's shots across the holes of one loop (ADR-013).

    Hardest hole first, by stroke index, then round again: with four shots over
    three holes the hardest gets two and the others one each. That is the order
    every golfer expects, and it is the whole reason this depends on
    `stroke_index` rather than spreading shots evenly.

    **Ties in stroke index are broken on hole id**, which matters more than it
    looks: there is no unique constraint on `(course_id, stroke_index)`, so two
    holes really can share one. Without the second key the order would come from
    whatever the caller happened to pass, and the same card could allocate
    differently on a re-submission.

    Args:
        handicaps: Playing handicap per participant. A player absent from this
            mapping receives nothing, which is what a scratch event looks like.
        loop: The holes being played, in any order — this sorts them itself.

    Returns:
        Shots per participant per hole. Every player in `handicaps` gets an entry
        for every hole, zero included, so a caller never has to distinguish "no
        shot here" from "not in the mapping".

    Raises:
        ValueError: If the loop is empty, or a handicap is negative.
    """
    if not loop:
        raise ValueError("Cannot allocate shots over a loop with no holes")

    hardest_first = sorted(loop, key=lambda hole: (hole.stroke_index, str(hole.hole_id)))

    allocation: dict[ParticipantId, dict[UUID, int]] = {}
    for participant_id, handicap in handicaps.items():
        shots = shots_for_loop(handicap, len(loop))
        base, extra = divmod(shots, len(hardest_first))
        allocation[participant_id] = {
            hole.hole_id: base + (1 if position < extra else 0)
            for position, hole in enumerate(hardest_first)
        }
    return allocation


def score_hole(
    strokes: Mapping[ParticipantId, int],
    *,
    strokes_received: Mapping[ParticipantId, int] | None = None,
    closest_to_pin: ParticipantId | None = None,
    longest_drive: ParticipantId | None = None,
) -> HoleResult:
    """Decide who won a hole, per the three-level cascade in ADR-007.

    Levels are tried in order and the first that separates the tied players wins
    it: fewest strokes, then closest to the pin, then longest drive on the
    fairway. Holes are never halved — if no level separates them, nobody wins and
    everyone scores zero.

    Closest to the pin and longest drive are contested **only among the players
    tied on strokes**. If A and B tie, the question is which of A and B was
    closer to the pin; C's ball is irrelevant however near the hole it finished.
    Naming a player who isn't tied is therefore a caller error, not something to
    quietly ignore — silently returning "no winner" would hide a real data bug
    behind a plausible-looking result.

    Both tie-break arguments are only consulted when there is actually a tie. An
    outright stroke winner takes the hole regardless of what is passed.

    **Handicaps change what a stroke counts as, not what the cascade is**
    (ADR-013). Pass `strokes_received` and every level above runs on *net*
    strokes instead; omit it and this is exactly the function it was before, which
    is what makes a scratch event provably unchanged.

    Args:
        strokes: **Gross** strokes taken this hole, for every player in the group.
        strokes_received: Shots each player's handicap gave them on this hole,
            from `allocate_shots`. None or empty means a scratch event. A player
            absent from it receives nothing.
        closest_to_pin: Whichever of the *tied* players was closest to the pin.
            None means this level cannot separate them — nobody reached the green
            or the group could not tell.
        longest_drive: Whichever of the *tied* players hit the longest drive that
            *finished on the fairway*. None means this level cannot separate them
            — typically because no tied player found the fairway.

    Returns:
        The winner (or None), which level decided it, and each player's points.

    Raises:
        ValueError: If no strokes were supplied, any **gross** stroke count is
            below 1, or a tie-break argument names a player who is not tied for
            fewest net strokes.
    """
    if not strokes:
        raise ValueError("Cannot score a hole with no players")

    invalid = {pid: count for pid, count in strokes.items() if count < 1}
    if invalid:
        raise ValueError(f"Strokes must be 1 or more; got {invalid}")

    received = strokes_received or {}
    # Gross is what the group reported and is validated above. Net is what decides
    # the hole, and carries **no floor**: three shots on a three is a net zero, and
    # a player owed more shots than they took has genuinely played it that well.
    deciding = {pid: count - received.get(pid, 0) for pid, count in strokes.items()}

    fewest = min(deciding.values())
    tied = {pid for pid, count in deciding.items() if count == fewest}

    if len(tied) == 1:
        return _hole_result(next(iter(tied)), DecidedBy.STROKES, strokes)

    # Levels 2 and 3 are contested only among the players tied on strokes.
    _require_tied("closest_to_pin", closest_to_pin, tied, net=bool(received))
    _require_tied("longest_drive", longest_drive, tied, net=bool(received))

    if closest_to_pin is not None:
        return _hole_result(closest_to_pin, DecidedBy.CLOSEST_TO_PIN, strokes)

    if longest_drive is not None:
        return _hole_result(longest_drive, DecidedBy.LONGEST_DRIVE, strokes)

    return _hole_result(None, DecidedBy.NO_WINNER, strokes)


def _require_tied(
    argument: str,
    flagged: ParticipantId | None,
    tied: set[ParticipantId],
    *,
    net: bool = False,
) -> None:
    """Reject a tie-break argument naming a player who isn't tied on strokes.

    `net` only changes the wording. On a handicap event the tie is on net strokes,
    and an error saying "fewest strokes" would send whoever reads it to check the
    gross numbers — where they would find no tie and no bug.
    """
    if flagged is not None and flagged not in tied:
        kind = "fewest net strokes" if net else "fewest strokes"
        raise ValueError(
            f"{argument}={flagged} is not tied for {kind}. Only players "
            f"tied on strokes contest closest to the pin and longest drive; "
            f"tied players are {sorted(str(pid) for pid in tied)}"
        )


def _hole_result(
    winner: ParticipantId | None,
    decided_by: DecidedBy,
    strokes: Mapping[ParticipantId, int],
) -> HoleResult:
    return HoleResult(
        winner=winner,
        decided_by=decided_by,
        points={pid: WINNING_POINTS if pid == winner else LOSING_POINTS for pid in strokes},
    )


@dataclass(frozen=True)
class ParticipantTotals:
    """A player's accumulated result across a loop, ready to be ranked."""

    participant_id: ParticipantId
    points: int
    total_strokes: int
    #: How many rounds this player was still alive for (ADR-012). Zero for every
    #: round robin, where the sort key below is then a constant and the ordering
    #: is exactly what it was before knockout existed.
    rounds_survived: int = 0


@dataclass(frozen=True)
class LeaderboardRow:
    position: int
    participant_id: ParticipantId
    points: int
    total_strokes: int
    rounds_survived: int = 0


def rank_leaderboard(totals: Iterable[ParticipantTotals]) -> list[LeaderboardRow]:
    """Order players by points, breaking ties on fewest total strokes (ADR-007).

    Over three holes with no half-points a player's total is an integer 0-3, so
    players finishing level on points is the norm rather than the exception —
    hence the stroke tie-break carrying real weight here.

    Players level on both points and strokes genuinely share a position, and the
    next position skips accordingly (1, 2, 2, 4) as is conventional in golf.

    **`rounds_survived` leads the sort, and is zero everywhere but a knockout**
    (ADR-012). A knockout champion can finish behind a beaten finalist on
    cumulative points — they played the same nine holes — so a board ordered on
    points alone would be reporting a different competition from the one that was
    run. For a round robin every value is 0, which makes it a constant leading
    key: the ordering, the shared positions and the stable-sort tie-break are
    all exactly what they were before knockout existed.
    """
    ordered = sorted(
        totals,
        key=lambda total: (-total.rounds_survived, -total.points, total.total_strokes),
    )

    rows: list[LeaderboardRow] = []
    for index, entry in enumerate(ordered):
        previous = ordered[index - 1] if index else None
        is_tied_with_previous = previous is not None and (
            entry.rounds_survived,
            entry.points,
            entry.total_strokes,
        ) == (previous.rounds_survived, previous.points, previous.total_strokes)

        rows.append(
            LeaderboardRow(
                position=rows[-1].position if is_tied_with_previous else index + 1,
                participant_id=entry.participant_id,
                points=entry.points,
                total_strokes=entry.total_strokes,
                rounds_survived=entry.rounds_survived,
            )
        )
    return rows


class AdvancedBy(str, Enum):
    """Which level of the knockout cascade sent a player through (ADR-012).

    Stored beside the player it named, like `DecidedBy`: "she went through on
    countback" is a different event from "the organiser sent her through", and an
    answer recomputed later records neither.
    """

    POINTS = "points"
    STROKES = "strokes"
    COUNTBACK = "countback"
    ORGANISER = "organiser"


@dataclass(frozen=True)
class GroupStanding:
    """One player's card over one group's loop — what a knockout is decided on."""

    participant_id: ParticipantId
    points: int
    total_strokes: int


@dataclass(frozen=True)
class Advancement:
    """Who goes through from one group, and what decided it.

    `winner` is None exactly when `decided_by` is None, and `tied` is non-empty
    exactly then — the players an organiser has to choose between. It mirrors the
    way a tied hole reports `tied_participants`: the engine says who is still
    level rather than inventing an answer.
    """

    winner: ParticipantId | None
    decided_by: AdvancedBy | None
    tied: tuple[ParticipantId, ...]


def decide_advancement(
    standings: Iterable[GroupStanding],
    hole_winners: Sequence[ParticipantId | None] = (),
) -> Advancement:
    """Decide which player goes through from one knockout group (ADR-012).

    Four levels, stopping at the first that separates the players still level:
    most points, then fewest total strokes, then **countback** — whoever won the
    latest hole of the loop — and if nothing does, nobody goes through and the
    organiser adjudicates.

    Countback walks the loop backwards and takes the first hole won by one of the
    players still tied. Holes nobody won are skipped, and so are holes won by
    somebody already out on points or strokes: the question is which of *these
    two* took a hole later, and a third player's hole answers nothing — the same
    scoping ADR-007 puts on closest to the pin.

    A group can genuinely finish with nobody on anything: `score_hole` returns
    `NO_WINNER` whenever nothing separates tied players, so "every hole has a
    winner" is not an invariant and this must not assume it. Note what that
    implies, because it is why the fourth level is rare — points come *only* from
    winning holes, so co-leaders on zero points mean every hole was halved.
    Countback therefore settles every tie except a group that finished completely
    all square, which is the one case no stored data can answer.

    Args:
        standings: Every player in the group, with what they scored over the loop.
        hole_winners: The group's hole winners **in playing order** — index 0 is
            the first hole of the loop, None where nobody won it, and a short
            sequence where holes are unplayed.

    Returns:
        The player who advances and the level that named them, or no winner and
        the players still level.

    Raises:
        ValueError: If `standings` is empty or names a participant twice.
    """
    cards = list(standings)
    if not cards:
        raise ValueError("Cannot decide a group with no players")
    duplicates = len(cards) - len({card.participant_id for card in cards})
    if duplicates:
        raise ValueError(f"standings contains {duplicates} duplicate participant id(s)")

    most = max(card.points for card in cards)
    level = [card for card in cards if card.points == most]
    if len(level) == 1:
        return Advancement(level[0].participant_id, AdvancedBy.POINTS, ())

    fewest = min(card.total_strokes for card in level)
    level = [card for card in level if card.total_strokes == fewest]
    if len(level) == 1:
        return Advancement(level[0].participant_id, AdvancedBy.STROKES, ())

    # Countback: the latest hole taken by one of the players still level. A None
    # is never in a set of UUIDs, so unwon holes fall through without a guard.
    contenders = {card.participant_id for card in level}
    for winner in reversed(hole_winners):
        if winner in contenders:
            return Advancement(winner, AdvancedBy.COUNTBACK, ())

    # ORGANISER is never returned here — it is the vocabulary for an answer that
    # arrives through another door entirely, once a human has been asked.
    return Advancement(None, None, tuple(card.participant_id for card in level))
