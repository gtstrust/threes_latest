"""The draw — group generation (ADR-004) and loop allocation (ADR-011).

Pure and synchronous, like the scoring engine: these take ids and return ids.
Persistence, and the choice of what order to feed players in, live in the round
service that calls this.
"""

from collections.abc import Sequence
from enum import Enum
from typing import Final
from uuid import UUID

ParticipantId = UUID
HoleId = UUID

# Final so these keep their literal types: `TARGET_GROUP_SIZE` is the default a
# `Literal[3, 4]` schema field has to accept, and a bare `int` would not fit it.
MIN_GROUP_SIZE: Final = 2
TARGET_GROUP_SIZE: Final = 3
MAX_GROUP_SIZE: Final = 4

HOLES_PER_LOOP: Final = 3


class LoopStyle(str, Enum):
    """How the holes in play are cut into loops (ADR-011).

    Values match the names so the wire format, the database enum and the ADR all
    read identically — the same convention as `TournamentStatus`.
    """

    #: Disjoint triples: 1-3, 4-6, 7-9. Eighteen holes make six loops, and groups
    #: beyond the sixth share them round-robin and tee off staggered.
    BLOCKS = "BLOCKS"
    #: Every hole in play is a starting tee. A group starting on hole *s* plays
    #: *s*, *s+1*, *s+2* counted modulo the holes in play, so eighteen holes make
    #: eighteen loops and the group on the 17th plays 17, 18, 1.
    SHOTGUN = "SHOTGUN"


def group_sizes(count: int, target: int = TARGET_GROUP_SIZE) -> list[int]:
    """Work out the group sizes for `count` players, per ADR-004.

    Three is the format and remains the default. `target` is the per-event
    setting an organiser may move to four, which exists for one reason: a real
    shotgun start needs a starting tee per group and a course has eighteen, so
    sixty-four players in threes is twenty-one groups and does not fit, while in
    fourballs it is sixteen and does. See ADR-011.

    One rule serves both targets: **fill groups of the target size; the leftover
    becomes its own group; and if that would leave somebody alone, absorb them
    into the previous group, splitting it evenly if that makes it larger than a
    group may be.**

    For a target of three that is exactly the rule ADR-004 has always described:
    3+1 is a fourball, which is legal, so seven is 3+4 and a remainder of two is
    a pair. For a target of four it is not, because 4+1 is five and no group may
    hold five — so it splits, and five is 3+2 while nine is 4+3+2.

    Under either target no group is ever outside `MIN_GROUP_SIZE`..
    `MAX_GROUP_SIZE`, and none is ever one: a lone player has nobody to play
    against, which is the whole reason the remainder cases exist.

    Raises:
        ValueError: If `target` is not a legal group size, or if `count` is
            negative, or is 1 — a lone player cannot form a group.
    """
    if not MIN_GROUP_SIZE <= target <= MAX_GROUP_SIZE:
        raise ValueError(
            f"A target group size must be between {MIN_GROUP_SIZE} and "
            f"{MAX_GROUP_SIZE}; got {target}"
        )
    if count < 0:
        raise ValueError(f"Player count cannot be negative; got {count}")
    if count == 0:
        return []
    if count == 1:
        raise ValueError("Cannot form a group from a single player")

    full, remainder = divmod(count, target)

    if remainder == 0:
        return [target] * full
    if remainder >= MIN_GROUP_SIZE:
        return [target] * full + [remainder]

    # remainder == 1: the lone player joins the previous group rather than
    # standing on a tee by themselves. `full >= 1` is guaranteed here, because a
    # remainder of one with no full group means count == 1, already rejected.
    absorbed = target + 1
    if absorbed <= MAX_GROUP_SIZE:
        return [target] * (full - 1) + [absorbed]

    # The absorbing group would be over size, so split it as evenly as it goes.
    # Only reachable at target == MAX_GROUP_SIZE, where 4+1 becomes 3+2.
    half = absorbed // 2
    return [target] * (full - 1) + [absorbed - half, half]


def build_groups(
    participant_ids: Sequence[ParticipantId], target: int = TARGET_GROUP_SIZE
) -> list[list[ParticipantId]]:
    """Split participants into groups of `target`, with the remainder absorbed.

    Order is preserved and the split is deterministic — the caller shuffles first
    if it wants randomised draws. Keeping this deterministic is what lets the
    tests assert on exact groupings.

    Raises:
        ValueError: If ids are duplicated, or the count cannot form valid groups.
    """
    duplicates = len(participant_ids) - len(set(participant_ids))
    if duplicates:
        raise ValueError(f"participant_ids contains {duplicates} duplicate id(s)")

    groups: list[list[ParticipantId]] = []
    start = 0
    for size in group_sizes(len(participant_ids), target):
        groups.append(list(participant_ids[start : start + size]))
        start += size
    return groups


def _reject_unplayable(hole_ids: Sequence[HoleId]) -> None:
    """Guard shared by both loop builders, so they refuse identically.

    Raises:
        ValueError: If there aren't enough holes for even one loop, or an id
            appears twice.
    """
    if len(hole_ids) < HOLES_PER_LOOP:
        raise ValueError(
            f"A loop needs {HOLES_PER_LOOP} holes; the course has only {len(hole_ids)} "
            "hole(s) entered"
        )

    duplicates = len(hole_ids) - len(set(hole_ids))
    if duplicates:
        raise ValueError(f"hole_ids contains {duplicates} duplicate id(s)")


def build_loops(hole_ids: Sequence[HoleId]) -> list[list[HoleId]]:
    """Chunk a course's holes into consecutive, disjoint 3-hole loops.

    Holes are expected in playing order (by hole number), so holes 1-18 give six
    loops: 1-3, 4-6, and so on. A remainder is simply unused — eight holes give
    two loops, not two and a bit — because a group has to play three.

    This is `LoopStyle.BLOCKS`, and the default. `build_shotgun_loops` is the
    other answer, and the two deliberately stay separate: this one promises
    disjoint triples with the remainder unused, that one promises overlapping
    windows with every hole a start.

    Raises:
        ValueError: If there aren't enough holes for even one loop.
    """
    _reject_unplayable(hole_ids)

    loop_count = len(hole_ids) // HOLES_PER_LOOP
    return [
        list(hole_ids[index * HOLES_PER_LOOP : (index + 1) * HOLES_PER_LOOP])
        for index in range(loop_count)
    ]


def build_shotgun_loops(hole_ids: Sequence[HoleId]) -> list[list[HoleId]]:
    """One loop per starting tee, wrapping — a real shotgun start (ADR-011).

    Every hole in play is somebody's first tee. The group starting on hole *s*
    plays *s*, *s+1*, *s+2*, counted **modulo the holes given**, so eighteen
    holes make eighteen loops and the group on the 17th plays 17, 18, 1.

    The windows overlap, and that is the point: they cannot collide. At step *t*
    the group that started on *s* is on hole *s+t*, so two groups share a hole
    only if they shared a tee. The field moves round the course as one
    procession, which is what a shotgun start is.

    Wrapping is what makes it eighteen loops rather than sixteen. Without it the
    17th and 18th tees could only ever be finishing holes, and a course's worth
    of starting positions would quietly be sixteen — the difference between a
    64-player fourball field having a tee each and not.

    Holes are expected in playing order, same as `build_loops`. The wrap is
    generated here rather than expressed by the caller, which is why sorting a
    selection into hole order upstream is the *input* to this and not a limit on
    it.

    Raises:
        ValueError: If there aren't enough holes for even one loop.
    """
    _reject_unplayable(hole_ids)

    count = len(hole_ids)
    return [
        [hole_ids[(start + step) % count] for step in range(HOLES_PER_LOOP)]
        for start in range(count)
    ]


def plan_loops(
    hole_ids: Sequence[HoleId], style: LoopStyle = LoopStyle.BLOCKS
) -> list[list[HoleId]]:
    """Cut the holes in play into loops the way this event starts (ADR-011).

    The one entry point the round service needs, so `grouping` stays the sole
    owner of the shape of a draw and `round.py` reads as orchestration.
    """
    if style is LoopStyle.SHOTGUN:
        return build_shotgun_loops(hole_ids)
    return build_loops(hole_ids)


def allocate_loops(group_count: int, loop_count: int) -> list[int]:
    """Assign each group a loop index, sharing round-robin when loops run short.

    A shotgun start wants every group on its own loop, and under
    `LoopStyle.SHOTGUN` on a full course it usually gets one: sixteen groups on
    eighteen holes take tees 1-16 and the last two sit idle.

    The course still caps it. Under `LoopStyle.BLOCKS` eighteen holes make only
    six loops, so a 24-player field (eight groups) has to double up: groups seven
    and eight go back onto loops one and two, which is what actually happens on a
    busy course — they tee off staggered. The same applies to a shotgun with more
    groups than holes in play.

    Raises:
        ValueError: If there are no loops to allocate, or a negative group count.
    """
    if loop_count < 1:
        raise ValueError("Cannot allocate groups with no loops available")
    if group_count < 0:
        raise ValueError(f"Group count cannot be negative; got {group_count}")

    return [index % loop_count for index in range(group_count)]
