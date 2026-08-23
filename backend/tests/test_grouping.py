"""Tests for the draw: ADR-004 grouping, plus shotgun-start loop allocation."""

import uuid

import pytest

from app.services.grouping import allocate_loops, build_groups, build_loops, group_sizes


def _ids(count: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(count)]


# Every count from 0 to 13, spelled out rather than computed, so a regression in
# the algorithm can't quietly change the expectation too. ADR-004: threes where
# possible, a pair or a fourball to absorb the remainder, never a group of one.
@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, []),
        (2, [2]),
        (3, [3]),
        (4, [4]),
        (5, [3, 2]),
        (6, [3, 3]),
        (7, [3, 4]),
        (8, [3, 3, 2]),
        (9, [3, 3, 3]),
        (10, [3, 3, 4]),
        (11, [3, 3, 3, 2]),
        (12, [3, 3, 3, 3]),
        (13, [3, 3, 3, 4]),
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
        assert len(group) in (2, 3, 4)


def test_a_lone_player_cannot_form_a_group() -> None:
    with pytest.raises(ValueError, match="single player"):
        group_sizes(1)

    with pytest.raises(ValueError, match="single player"):
        build_groups(_ids(1))


def test_negative_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        group_sizes(-1)


def test_four_players_are_one_fourball_not_two_pairs() -> None:
    """The standard social grouping plays as a single match.

    Splitting a fourball 2+2, as this used to, meant each hole was decided
    within a pair and nobody played against the other two — which is not the
    game four mates think they are playing.
    """
    a, b, c, d = _ids(4)
    assert build_groups([a, b, c, d]) == [[a, b, c, d]]


def test_a_leftover_player_is_absorbed_into_a_four() -> None:
    a, b, c, d, e = _ids(5)
    assert build_groups([a, b, c, d, e]) == [[a, b, c], [d, e]]

    seven = _ids(7)
    assert build_groups(seven) == [seven[0:3], seven[3:7]]


def test_order_is_preserved_so_draws_are_deterministic() -> None:
    participants = _ids(7)
    assert build_groups(participants) == [
        participants[0:3],
        participants[3:7],
    ]
    assert build_groups(participants) == build_groups(participants)


def test_duplicate_participants_are_rejected() -> None:
    duplicated = _ids(3)
    with pytest.raises(ValueError, match="duplicate"):
        build_groups([*duplicated, duplicated[0]])


# --- Loops (shotgun start) --------------------------------------------------


@pytest.mark.parametrize(
    ("hole_count", "expected_loops"),
    [
        (3, 1),
        (5, 1),  # remainder of two is unused — a group must play three
        (6, 2),
        (8, 2),
        (9, 3),
        (18, 6),  # the number that constrains a full field
    ],
)
def test_loops_are_consecutive_triples(hole_count: int, expected_loops: int) -> None:
    holes = _ids(hole_count)

    loops = build_loops(holes)

    assert len(loops) == expected_loops
    assert all(len(loop) == 3 for loop in loops)
    # Consecutive and in playing order, not shuffled.
    assert loops == [holes[i * 3 : i * 3 + 3] for i in range(expected_loops)]


def test_a_course_with_too_few_holes_cannot_make_a_loop() -> None:
    for count in (0, 1, 2):
        with pytest.raises(ValueError, match="needs 3 holes"):
            build_loops(_ids(count))


def test_duplicate_holes_are_rejected() -> None:
    holes = _ids(3)
    with pytest.raises(ValueError, match="duplicate"):
        build_loops([*holes, holes[0]])


def test_each_group_gets_its_own_loop_when_there_are_enough() -> None:
    assert allocate_loops(group_count=4, loop_count=6) == [0, 1, 2, 3]


def test_loops_are_shared_round_robin_when_groups_outnumber_them() -> None:
    """24 players is 8 groups, but 18 holes only make 6 loops."""
    assert allocate_loops(group_count=8, loop_count=6) == [0, 1, 2, 3, 4, 5, 0, 1]


def test_a_single_loop_serves_every_group() -> None:
    assert allocate_loops(group_count=3, loop_count=1) == [0, 0, 0]


def test_allocating_with_no_loops_is_rejected() -> None:
    with pytest.raises(ValueError, match="no loops"):
        allocate_loops(group_count=2, loop_count=0)


def test_allocating_a_negative_group_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        allocate_loops(group_count=-1, loop_count=2)


def test_no_groups_allocates_nothing() -> None:
    assert allocate_loops(group_count=0, loop_count=6) == []
