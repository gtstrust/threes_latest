"""Group generation algorithm — see CLAUDE.md ADR-004.

Pure and synchronous, like the scoring engine: takes participant ids, returns
groups. Persistence lives in the round service that calls this.
"""

from collections.abc import Sequence
from uuid import UUID

ParticipantId = UUID

MIN_GROUP_SIZE = 2
MAX_GROUP_SIZE = 3


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
