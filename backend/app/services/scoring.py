"""Points calculation engine — see CLAUDE.md ADR-007.

Pure and synchronous by design: no database access, no I/O, nothing async. Every
function here takes plain data and returns plain data, which is what makes the
platform's most critical business logic exhaustively testable without fixtures.
Persistence and orchestration belong in the service layer that calls this.
"""

from collections.abc import Iterable, Mapping
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

    A flag only breaks the tie when the flagged player is themselves tied on
    strokes. If A and B are tied but C was closest to the pin, that level cannot
    separate A from B and the cascade falls through. "No winner" is therefore a
    normal outcome, not an edge case.

    Args:
        strokes: Strokes taken this hole, for every player in the group.
        closest_to_pin: The single player the group flagged as closest to the pin,
            if any. Ignored unless they are tied for fewest strokes.
        longest_drive: The single player the group flagged as having the longest
            drive that *finished on the fairway*, if any. Ignored unless they are
            tied for fewest strokes.

    Returns:
        The winner (or None), which level decided it, and each player's points.

    Raises:
        ValueError: If no strokes were supplied, or any stroke count is below 1.
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

    # Levels 2 and 3. A flag is only usable if that player is one of the tied.
    if closest_to_pin is not None and closest_to_pin in tied:
        return _hole_result(closest_to_pin, DecidedBy.CLOSEST_TO_PIN, strokes)

    if longest_drive is not None and longest_drive in tied:
        return _hole_result(longest_drive, DecidedBy.LONGEST_DRIVE, strokes)

    return _hole_result(None, DecidedBy.NO_WINNER, strokes)


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


@dataclass(frozen=True)
class LeaderboardRow:
    position: int
    participant_id: ParticipantId
    points: int
    total_strokes: int


def rank_leaderboard(totals: Iterable[ParticipantTotals]) -> list[LeaderboardRow]:
    """Order players by points, breaking ties on fewest total strokes (ADR-007).

    Over three holes with no half-points a player's total is an integer 0-3, so
    players finishing level on points is the norm rather than the exception —
    hence the stroke tie-break carrying real weight here.

    Players level on both points and strokes genuinely share a position, and the
    next position skips accordingly (1, 2, 2, 4) as is conventional in golf.
    """
    ordered = sorted(totals, key=lambda total: (-total.points, total.total_strokes))

    rows: list[LeaderboardRow] = []
    for index, entry in enumerate(ordered):
        previous = ordered[index - 1] if index else None
        is_tied_with_previous = previous is not None and (
            entry.points,
            entry.total_strokes,
        ) == (previous.points, previous.total_strokes)

        rows.append(
            LeaderboardRow(
                position=rows[-1].position if is_tied_with_previous else index + 1,
                participant_id=entry.participant_id,
                points=entry.points,
                total_strokes=entry.total_strokes,
            )
        )
    return rows
