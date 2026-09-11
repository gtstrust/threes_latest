"""Tests for the draw: ADR-004 grouping, plus ADR-011 loop building."""

import uuid

import pytest

from app.services.grouping import (
    HOLES_PER_LOOP,
    MAX_GROUP_SIZE,
    MIN_GROUP_SIZE,
    LoopStyle,
    allocate_loops,
    build_groups,
    build_loops,
    build_shotgun_loops,
    group_sizes,
    plan_loops,
)


def _ids(count: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(count)]


# Every count from 0 to 13, spelled out rather than computed, so a regression in
# the algorithm can't quietly change the expectation too. ADR-004: threes where
# possible, a pair or a fourball to absorb the remainder, never a group of one.
#
# This is the *default* target, and every entry below predates group_size being a
# setting. Left exactly as it was on purpose: it is the proof that adding the
# parameter moved nothing for the threes the platform is named after.
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
    # Passing the default explicitly must be the same call.
    assert group_sizes(count, target=3) == expected


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


# --- Fourballs (ADR-004, amended) -------------------------------------------


# Spelled out for the same reason as the threes table above. The rule is one
# sentence — fill groups of the target, the leftover becomes its own group, and a
# player who would be left alone is absorbed into the previous one, splitting it
# if that would make it oversize. For fours that last clause bites where it never
# did for threes: 3+1 is a legal fourball, but 4+1 is not, so it becomes 3+2.
@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (2, [2]),
        (3, [3]),
        (4, [4]),
        (5, [3, 2]),  # not [4, 1] — nobody plays alone
        (6, [4, 2]),
        (7, [4, 3]),
        (8, [4, 4]),
        (9, [4, 3, 2]),
        (10, [4, 4, 2]),
        (11, [4, 4, 3]),
        (12, [4, 4, 4]),
        (13, [4, 4, 3, 2]),
        (14, [4, 4, 4, 2]),
        (15, [4, 4, 4, 3]),
        (16, [4, 4, 4, 4]),
        (17, [4, 4, 4, 3, 2]),
        (18, [4, 4, 4, 4, 2]),
        (19, [4, 4, 4, 4, 3]),
        (20, [4, 4, 4, 4, 4]),
    ],
)
def test_group_sizes_for_fourballs(count: int, expected: list[int]) -> None:
    assert group_sizes(count, target=4) == expected


def test_sixty_four_players_are_sixteen_fourballs() -> None:
    """The whole reason the target is a setting.

    A shotgun start needs a tee per group and a course has eighteen. Sixty-four
    players in threes is twenty-one groups, which does not fit; in fourballs it
    is sixteen, which does.
    """
    assert group_sizes(64, target=4) == [4] * 16
    assert len(group_sizes(64)) == 21  # ...and in threes it still does not fit


@pytest.mark.parametrize("target", (2, 3, 4))
@pytest.mark.parametrize("count", range(2, 70))
def test_every_target_produces_only_legal_groups(count: int, target: int) -> None:
    """The invariants, over a range no spelled-out table reaches."""
    sizes = group_sizes(count, target=target)

    assert sum(sizes) == count
    assert all(MIN_GROUP_SIZE <= size <= MAX_GROUP_SIZE for size in sizes)
    assert 1 not in sizes


@pytest.mark.parametrize("target", (2, 3, 4))
def test_a_lone_player_cannot_form_a_group_at_any_target(target: int) -> None:
    with pytest.raises(ValueError, match="single player"):
        group_sizes(1, target=target)


@pytest.mark.parametrize("target", (0, 1, 5, 18))
def test_an_impossible_target_is_rejected(target: int) -> None:
    with pytest.raises(ValueError, match="target group size must be between"):
        group_sizes(12, target=target)


def test_build_groups_takes_the_target_through() -> None:
    participants = _ids(9)
    assert build_groups(participants, target=4) == [
        participants[0:4],
        participants[4:7],
        participants[7:9],
    ]


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


# --- Shotgun loops (ADR-011) ------------------------------------------------


@pytest.mark.parametrize("hole_count", (3, 6, 10, 18))
def test_a_shotgun_makes_one_loop_per_starting_tee(hole_count: int) -> None:
    """Every hole in play is somebody's first tee, so N holes give N loops.

    Six from eighteen — what BLOCKS gives — is the thing that made a 64-player
    shotgun impossible.
    """
    loops = build_shotgun_loops(_ids(hole_count))

    assert len(loops) == hole_count
    assert all(len(loop) == HOLES_PER_LOOP for loop in loops)


def test_a_shotgun_loop_wraps_the_turn() -> None:
    """The case `_select_holes` used to say was not expressible."""
    holes = _ids(18)

    loops = build_shotgun_loops(holes)

    assert loops[0] == holes[0:3]  # start on 1: 1, 2, 3
    assert loops[15] == holes[15:18]  # start on 16: 16, 17, 18
    assert loops[16] == [holes[16], holes[17], holes[0]]  # start on 17: 17, 18, 1
    assert loops[17] == [holes[17], holes[0], holes[1]]  # start on 18: 18, 1, 2


def test_a_three_hole_course_gives_three_rotations() -> None:
    """The degenerate case, which BLOCKS answers with a single shared loop."""
    a, b, c = _ids(3)

    assert build_shotgun_loops([a, b, c]) == [[a, b, c], [b, c, a], [c, a, b]]


@pytest.mark.parametrize("hole_count", (3, 6, 10, 18))
def test_no_two_groups_are_ever_on_the_same_hole(hole_count: int) -> None:
    """The property that makes a shotgun a shotgun, rather than a collision.

    At step t the group that started on s is on hole s+t, so two groups share a
    hole only if they shared a tee. Asserted per step: at every point in the
    round, the holes in use are all distinct.
    """
    loops = build_shotgun_loops(_ids(hole_count))

    for step in range(HOLES_PER_LOOP):
        in_use = {loop[step] for loop in loops}
        assert len(in_use) == len(loops)


def test_a_shotgun_refuses_the_same_things_blocks_does() -> None:
    """One guard, so the two builders cannot drift on what they reject."""
    for count in (0, 1, 2):
        with pytest.raises(ValueError, match="needs 3 holes"):
            build_shotgun_loops(_ids(count))

    holes = _ids(3)
    with pytest.raises(ValueError, match="duplicate"):
        build_shotgun_loops([*holes, holes[0]])


def test_plan_loops_dispatches_on_style() -> None:
    holes = _ids(18)

    assert plan_loops(holes) == build_loops(holes)
    assert plan_loops(holes, style=LoopStyle.BLOCKS) == build_loops(holes)
    assert plan_loops(holes, style=LoopStyle.SHOTGUN) == build_shotgun_loops(holes)


def test_sixteen_fourballs_each_get_their_own_tee() -> None:
    """The event this exists for, in the two pure functions that decide it."""
    loops = plan_loops(_ids(18), style=LoopStyle.SHOTGUN)
    groups = group_sizes(64, target=4)

    allocation = allocate_loops(len(groups), len(loops))

    assert allocation == list(range(16))
    assert len(set(allocation)) == 16  # sixteen distinct tees, nobody sharing


# --- Knockout brackets (ADR-012) --------------------------------------------


def _bracket(players: int, target: int) -> list[int]:
    """The field size at the start of each round, until one player is left."""
    rounds = []
    while players > 1:
        rounds.append(players)
        players = len(group_sizes(players, target))
    return rounds


def test_sixty_four_is_three_rounds_of_fourballs() -> None:
    """The event ADR-012 is built for: 64 -> 16 -> 4 -> 1, and 4 is 4 * 4 * 4."""
    assert _bracket(64, 4) == [64, 16, 4]
    assert group_sizes(4, 4) == [4]  # the final is a single fourball


def test_sixty_four_is_the_largest_field_that_fits_three_rounds() -> None:
    """One more player costs a whole extra round, which is why 64 is the number."""
    assert len(_bracket(64, 4)) == 3
    assert len(_bracket(65, 4)) == 4


@pytest.mark.parametrize("target", (3, 4))
@pytest.mark.parametrize("players", range(2, 201))
def test_every_bracket_terminates(players: int, target: int) -> None:
    """A knockout always reaches a champion, and never stalls.

    `group_sizes` never returns a group of one, so the number of groups is
    strictly fewer than the number of players for every count above one — which
    is what makes the loop in `_bracket` finite rather than merely usually
    finite.
    """
    bracket = _bracket(players, target)

    assert bracket[0] == players
    assert all(later < earlier for earlier, later in zip(bracket, bracket[1:], strict=False))
    assert len(group_sizes(bracket[-1], target)) == 1  # the last round is one group
