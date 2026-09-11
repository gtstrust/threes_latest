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


def score_hole(
    strokes: Mapping[ParticipantId, int],
    *,
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

    Args:
        strokes: Strokes taken this hole, for every player in the group.
        closest_to_pin: Whichever of the *tied* players was closest to the pin.
            None means this level cannot separate them — nobody reached the green
            or the group could not tell.
        longest_drive: Whichever of the *tied* players hit the longest drive that
            *finished on the fairway*. None means this level cannot separate them
            — typically because no tied player found the fairway.

    Returns:
        The winner (or None), which level decided it, and each player's points.

    Raises:
        ValueError: If no strokes were supplied, any stroke count is below 1, or
            a tie-break argument names a player who is not tied for fewest
            strokes.
    """
    if not strokes:
        raise ValueError("Cannot score a hole with no players")

    invalid = {pid: count for pid, count in strokes.items() if count < 1}
    if invalid:
        raise ValueError(f"Strokes must be 1 or more; got {invalid}")

    fewest = min(strokes.values())
    tied = {pid for pid, count in strokes.items() if count == fewest}

    if len(tied) == 1:
        return _hole_result(next(iter(tied)), DecidedBy.STROKES, strokes)

    # Levels 2 and 3 are contested only among the players tied on strokes.
    _require_tied("closest_to_pin", closest_to_pin, tied)
    _require_tied("longest_drive", longest_drive, tied)

    if closest_to_pin is not None:
        return _hole_result(closest_to_pin, DecidedBy.CLOSEST_TO_PIN, strokes)

    if longest_drive is not None:
        return _hole_result(longest_drive, DecidedBy.LONGEST_DRIVE, strokes)

    return _hole_result(None, DecidedBy.NO_WINNER, strokes)


def _require_tied(
    argument: str,
    flagged: ParticipantId | None,
    tied: set[ParticipantId],
) -> None:
    """Reject a tie-break argument naming a player who isn't tied on strokes."""
    if flagged is not None and flagged not in tied:
        raise ValueError(
            f"{argument}={flagged} is not tied for fewest strokes. Only players "
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
