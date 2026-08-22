"""Tests for the ADR-004 grouping algorithm."""

import uuid

import pytest

from app.services.grouping import build_groups, group_sizes


def _ids(count: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(count)]


# Every count from 0 to 13, spelled out rather than computed, so a regression in
# the algorithm can't quietly change the expectation too. ADR-004: threes where
# possible, pairs otherwise, never a group of one.
@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, []),
        (2, [2]),
        (3, [3]),
        (4, [2, 2]),
        (5, [3, 2]),
        (6, [3, 3]),
        (7, [3, 2, 2]),
        (8, [3, 3, 2]),
        (9, [3, 3, 3]),
        (10, [3, 3, 2, 2]),
        (11, [3, 3, 3, 2]),
        (12, [3, 3, 3, 3]),
        (13, [3, 3, 3, 2, 2]),
    ],
)
def test_group_sizes(count: int, expected: list[int]) -> None:
    assert group_sizes(count) == expected


@pytest.mark.parametrize("count", range(2, 40))
def test_every_player_is_placed_exactly_once(count: int) -> None:
    participants = _ids(count)
    groups = build_groups(participants)

    placed = [pid for group in groups for pid in group]
    assert sorted(placed, key=str) == sorted(participants, key=str)
    assert len(placed) == count


@pytest.mark.parametrize("count", range(2, 40))
def test_no_group_is_ever_left_with_one_player(count: int) -> None:
    for group in build_groups(_ids(count)):
        assert len(group) in (2, 3)


def test_a_lone_player_cannot_form_a_group() -> None:
    with pytest.raises(ValueError, match="single player"):
        group_sizes(1)

    with pytest.raises(ValueError, match="single player"):
        build_groups(_ids(1))


def test_negative_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        group_sizes(-1)


def test_four_players_split_into_pairs_not_three_and_one() -> None:
    a, b, c, d = _ids(4)
    assert build_groups([a, b, c, d]) == [[a, b], [c, d]]


def test_order_is_preserved_so_draws_are_deterministic() -> None:
    participants = _ids(7)
    assert build_groups(participants) == [
        participants[0:3],
        participants[3:5],
        participants[5:7],
    ]
    assert build_groups(participants) == build_groups(participants)


def test_duplicate_participants_are_rejected() -> None:
    duplicated = _ids(3)
    with pytest.raises(ValueError, match="duplicate"):
        build_groups([*duplicated, duplicated[0]])
