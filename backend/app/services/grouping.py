"""The draw — group generation (ADR-004) and shotgun-start loop allocation.

Pure and synchronous, like the scoring engine: these take ids and return ids.
Persistence, and the choice of what order to feed players in, live in the round
service that calls this.
"""

from collections.abc import Sequence
from uuid import UUID

ParticipantId = UUID
HoleId = UUID

MIN_GROUP_SIZE = 2
MAX_GROUP_SIZE = 3

HOLES_PER_LOOP = 3


def group_sizes(count: int) -> list[int]:
    """Work out the group sizes for `count` players, per ADR-004.

    Groups are of three wherever possible, falling back to pairs. The case worth
    knowing about is a remainder of one: four players must be 2+2 rather than
    3+1, and seven must be 3+2+2, because a group of one has nobody to play
    against. So when one player would be left over, the last group of three is
    broken up into two pairs instead.

    Raises:
        ValueError: If `count` is negative, or is 1 — a lone player cannot form
            a group.
    """
    if count < 0:
        raise ValueError(f"Player count cannot be negative; got {count}")
    if count == 0:
        return []
    if count == 1:
        raise ValueError("Cannot form a group from a single player")

    remainder = count % MAX_GROUP_SIZE
    threes = count // MAX_GROUP_SIZE

    if remainder == 0:
        return [MAX_GROUP_SIZE] * threes
    if remainder == 2:
        return [MAX_GROUP_SIZE] * threes + [MIN_GROUP_SIZE]

    # remainder == 1: trade a three for two pairs so nobody is left alone.
    # threes >= 1 is guaranteed here because count >= 4 (count of 1 was rejected).
    return [MAX_GROUP_SIZE] * (threes - 1) + [MIN_GROUP_SIZE, MIN_GROUP_SIZE]


def build_groups(participant_ids: Sequence[ParticipantId]) -> list[list[ParticipantId]]:
    """Split participants into groups of three, falling back to pairs.

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
    for size in group_sizes(len(participant_ids)):
        groups.append(list(participant_ids[start : start + size]))
        start += size
    return groups


def build_loops(hole_ids: Sequence[HoleId]) -> list[list[HoleId]]:
    """Chunk a course's holes into consecutive 3-hole loops.

    Holes are expected in playing order (by hole number), so holes 1-18 give six
    loops: 1-3, 4-6, and so on. A remainder is simply unused — eight holes give
    two loops, not two and a bit — because a group has to play three.

    Raises:
        ValueError: If there aren't enough holes for even one loop.
    """
    if len(hole_ids) < HOLES_PER_LOOP:
        raise ValueError(
            f"A loop needs {HOLES_PER_LOOP} holes; the course has only {len(hole_ids)} "
            "hole(s) entered"
        )

    duplicates = len(hole_ids) - len(set(hole_ids))
    if duplicates:
        raise ValueError(f"hole_ids contains {duplicates} duplicate id(s)")

    loop_count = len(hole_ids) // HOLES_PER_LOOP
    return [
        list(hole_ids[index * HOLES_PER_LOOP : (index + 1) * HOLES_PER_LOOP])
        for index in range(loop_count)
    ]


def allocate_loops(group_count: int, loop_count: int) -> list[int]:
    """Assign each group a loop index, sharing round-robin when loops run short.

    A shotgun start wants every group on its own loop, but the course caps that:
    18 holes make only six loops, so a 24-player field (eight groups) has to
    double up. Groups seven and eight go back onto loops one and two, which is
    what actually happens on a busy course — they tee off staggered.

    Raises:
        ValueError: If there are no loops to allocate, or a negative group count.
    """
    if loop_count < 1:
        raise ValueError("Cannot allocate groups with no loops available")
    if group_count < 0:
        raise ValueError(f"Group count cannot be negative; got {group_count}")

    return [index % loop_count for index in range(group_count)]
