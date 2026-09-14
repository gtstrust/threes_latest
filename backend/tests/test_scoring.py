"""Tests for the ADR-007 scoring engine.

CLAUDE.md calls the scoring engine the most critical business logic on the
platform, so the cascade is covered level by level, including the cases where a
tie-break flag is present but unusable.
"""

import uuid

import pytest

from app.services.scoring import (
    AdvancedBy,
    DecidedBy,
    GroupStanding,
    LeaderboardRow,
    LoopHole,
    ParticipantTotals,
    allocate_shots,
    decide_advancement,
    rank_leaderboard,
    score_hole,
    shots_for_loop,
)

A = uuid.uuid4()
B = uuid.uuid4()
C = uuid.uuid4()


# --- Level 1: fewest strokes ------------------------------------------------


def test_outright_lowest_score_wins_the_hole() -> None:
    result = score_hole({A: 3, B: 4, C: 5})

    assert result.winner == A
    assert result.decided_by is DecidedBy.STROKES
    assert result.points == {A: 1, B: 0, C: 0}


def test_only_the_winner_scores() -> None:
    result = score_hole({A: 3, B: 4, C: 5})

    assert sum(result.points.values()) == 1


# --- Level 2: closest to the pin --------------------------------------------


def test_tie_on_strokes_is_broken_by_closest_to_pin() -> None:
    result = score_hole({A: 4, B: 4, C: 5}, closest_to_pin=B)

    assert result.winner == B
    assert result.decided_by is DecidedBy.CLOSEST_TO_PIN
    assert result.points == {A: 0, B: 1, C: 0}


def test_closest_to_pin_must_name_a_player_tied_on_strokes() -> None:
    """Only the tied players contest closest to the pin.

    A and B are tied; C is not in contention, so C cannot be the answer to
    "which of the tied players was closest?". Naming C is a data error rather
    than a silent fall-through to no-winner, which would hide the bug.
    """
    with pytest.raises(ValueError, match="not tied for fewest strokes"):
        score_hole({A: 4, B: 4, C: 6}, closest_to_pin=C)


def test_closest_to_pin_none_means_the_level_cannot_separate_them() -> None:
    result = score_hole({A: 4, B: 4, C: 6}, closest_to_pin=None)

    assert result.winner is None
    assert result.decided_by is DecidedBy.NO_WINNER


def test_closest_to_pin_does_not_override_an_outright_stroke_win() -> None:
    result = score_hole({A: 3, B: 4, C: 5}, closest_to_pin=B)

    assert result.winner == A
    assert result.decided_by is DecidedBy.STROKES


# --- Level 3: longest drive on the fairway ----------------------------------


def test_longest_drive_breaks_the_tie_when_closest_to_pin_cannot() -> None:
    """Neither tied player reached the green, so level 2 passes to level 3."""
    result = score_hole({A: 4, B: 4, C: 5}, closest_to_pin=None, longest_drive=A)

    assert result.winner == A
    assert result.decided_by is DecidedBy.LONGEST_DRIVE


def test_closest_to_pin_takes_precedence_over_longest_drive() -> None:
    result = score_hole({A: 4, B: 4, C: 5}, closest_to_pin=A, longest_drive=B)

    assert result.winner == A
    assert result.decided_by is DecidedBy.CLOSEST_TO_PIN


def test_longest_drive_must_name_a_player_tied_on_strokes() -> None:
    with pytest.raises(ValueError, match="not tied for fewest strokes"):
        score_hole({A: 4, B: 4, C: 6}, longest_drive=C)


def test_tie_break_arguments_are_not_checked_when_there_is_no_tie() -> None:
    """An outright stroke winner takes the hole whatever else is passed.

    With no tie there is no contest to be part of, so a stray argument is
    harmless rather than an error.
    """
    result = score_hole({A: 3, B: 4, C: 5}, closest_to_pin=C, longest_drive=B)

    assert result.winner == A
    assert result.decided_by is DecidedBy.STROKES


# --- No winner --------------------------------------------------------------


def test_holes_are_never_halved_nobody_wins_when_nothing_separates_them() -> None:
    result = score_hole({A: 4, B: 4, C: 5})

    assert result.winner is None
    assert result.decided_by is DecidedBy.NO_WINNER
    assert result.points == {A: 0, B: 0, C: 0}
    assert sum(result.points.values()) == 0


def test_all_three_tied_with_no_flags_scores_nobody() -> None:
    result = score_hole({A: 4, B: 4, C: 4})

    assert result.winner is None
    assert result.points == {A: 0, B: 0, C: 0}


def test_all_three_tied_is_still_resolvable_by_a_flag() -> None:
    result = score_hole({A: 4, B: 4, C: 4}, closest_to_pin=C)

    assert result.winner == C
    assert result.decided_by is DecidedBy.CLOSEST_TO_PIN


# --- Two-player groups (ADR-004 allows a trailing pair) ---------------------


def test_two_player_groups_use_the_same_rules() -> None:
    result = score_hole({A: 4, B: 5})

    assert result.winner == A
    assert result.points == {A: 1, B: 0}


def test_two_player_group_tie_falls_through_to_no_winner() -> None:
    result = score_hole({A: 4, B: 4})

    assert result.winner is None
    assert result.points == {A: 0, B: 0}


# --- Points are always integers, never halves -------------------------------


def test_points_are_integers_never_halves() -> None:
    for result in (
        score_hole({A: 4, B: 4, C: 5}),
        score_hole({A: 3, B: 4, C: 5}),
        score_hole({A: 4, B: 4, C: 5}, closest_to_pin=A),
    ):
        for points in result.points.values():
            assert isinstance(points, int)
            assert points in (0, 1)


# --- Input validation -------------------------------------------------------


def test_scoring_an_empty_hole_is_rejected() -> None:
    with pytest.raises(ValueError, match="no players"):
        score_hole({})


@pytest.mark.parametrize("bad", [0, -1])
def test_non_positive_strokes_are_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="1 or more"):
        score_hole({A: bad, B: 4})


# --- Leaderboard ordering ---------------------------------------------------


def test_leaderboard_orders_by_points_then_fewest_strokes() -> None:
    rows = rank_leaderboard(
        [
            ParticipantTotals(A, points=1, total_strokes=12),
            ParticipantTotals(B, points=2, total_strokes=14),
            ParticipantTotals(C, points=1, total_strokes=11),
        ]
    )

    assert [row.participant_id for row in rows] == [B, C, A]
    assert [row.position for row in rows] == [1, 2, 3]


def test_players_level_on_points_are_split_by_total_strokes() -> None:
    rows = rank_leaderboard(
        [
            ParticipantTotals(A, points=2, total_strokes=15),
            ParticipantTotals(B, points=2, total_strokes=13),
        ]
    )

    assert rows[0].participant_id == B
    assert [row.position for row in rows] == [1, 2]


def test_players_level_on_both_share_a_position_and_the_next_skips() -> None:
    rows = rank_leaderboard(
        [
            ParticipantTotals(A, points=3, total_strokes=10),
            ParticipantTotals(B, points=2, total_strokes=12),
            ParticipantTotals(C, points=2, total_strokes=12),
        ]
    )

    assert [row.position for row in rows] == [1, 2, 2]


def test_next_position_skips_after_a_shared_one() -> None:
    d = uuid.uuid4()
    rows = rank_leaderboard(
        [
            ParticipantTotals(A, points=2, total_strokes=12),
            ParticipantTotals(B, points=2, total_strokes=12),
            ParticipantTotals(C, points=2, total_strokes=12),
            ParticipantTotals(d, points=1, total_strokes=11),
        ]
    )

    assert [row.position for row in rows] == [1, 1, 1, 4]


def test_empty_leaderboard() -> None:
    assert rank_leaderboard([]) == []


def test_leaderboard_row_carries_the_totals_through() -> None:
    (row,) = rank_leaderboard([ParticipantTotals(A, points=2, total_strokes=13)])

    assert row == LeaderboardRow(position=1, participant_id=A, points=2, total_strokes=13)


# --- Knockout advancement (ADR-012) -----------------------------------------


def _card(participant, points, strokes):
    return GroupStanding(participant_id=participant, points=points, total_strokes=strokes)


def test_most_points_goes_through() -> None:
    result = decide_advancement([_card(A, 2, 12), _card(B, 1, 11), _card(C, 0, 10)])

    assert result.winner == A
    assert result.decided_by is AdvancedBy.POINTS
    assert result.tied == ()


def test_level_on_points_is_split_by_fewest_strokes() -> None:
    """The same tie-break the leaderboard uses (ADR-007), applied to one group."""
    result = decide_advancement([_card(A, 1, 13), _card(B, 1, 11)])

    assert result.winner == B
    assert result.decided_by is AdvancedBy.STROKES


def test_level_on_both_is_split_by_the_latest_hole_won() -> None:
    """Countback. A won the first hole, B the last, so B goes through."""
    result = decide_advancement([_card(A, 1, 12), _card(B, 1, 12)], [A, None, B])

    assert result.winner == B
    assert result.decided_by is AdvancedBy.COUNTBACK


def test_countback_skips_a_hole_nobody_won() -> None:
    """A halved hole is not an answer, so the question moves back a hole."""
    result = decide_advancement([_card(A, 1, 12), _card(B, 1, 12)], [B, A, None])

    assert result.winner == A
    assert result.decided_by is AdvancedBy.COUNTBACK


def test_countback_ignores_a_hole_won_by_someone_already_out() -> None:
    """Which of *these two* took a hole later — a third player's hole answers nothing.

    C won the last hole but lost the group on strokes, so the question is still
    between A and B and is settled by the hole before it.
    """
    result = decide_advancement([_card(A, 1, 12), _card(B, 1, 12), _card(C, 1, 14)], [A, B, C])

    assert result.winner == B
    assert result.decided_by is AdvancedBy.COUNTBACK


def test_an_all_square_group_goes_through_to_nobody() -> None:
    """The only case the organiser is ever asked about.

    Points come only from winning holes, so co-leaders on zero mean every hole
    was halved. There is nothing left in the data to ask.
    """
    result = decide_advancement(
        [_card(A, 0, 12), _card(B, 0, 12), _card(C, 0, 12)], [None, None, None]
    )

    assert result.winner is None
    assert result.decided_by is None
    assert set(result.tied) == {A, B, C}


def test_the_tied_players_keep_input_order() -> None:
    """The organiser picks from this list; it must not reshuffle between requests."""
    result = decide_advancement([_card(C, 0, 12), _card(A, 0, 12), _card(B, 0, 12)])

    assert result.tied == (C, A, B)


def test_a_group_with_no_holes_played_yet_separates_nobody() -> None:
    """Completing a round early is allowed; it just leaves the group undecided."""
    result = decide_advancement([_card(A, 0, 0), _card(B, 0, 0)])

    assert result.winner is None
    assert result.tied == (A, B)


def test_the_organiser_is_never_a_verdict_this_function_reaches() -> None:
    """AdvancedBy.ORGANISER is storage vocabulary for an answer from elsewhere."""
    for winners in ([A, B, None], [None, None, None], [A, A, A]):
        assert decide_advancement([_card(A, 1, 12), _card(B, 1, 12)], winners).decided_by is not (
            AdvancedBy.ORGANISER
        )


def test_a_group_with_no_players_is_rejected() -> None:
    with pytest.raises(ValueError, match="no players"):
        decide_advancement([])


def test_a_duplicated_player_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        decide_advancement([_card(A, 1, 12), _card(A, 0, 13)])


def test_rounds_survived_leads_the_ranking_only_when_it_is_set() -> None:
    """A knockout champion outranks a finalist who scored more (ADR-012)."""
    champion = ParticipantTotals(A, points=2, total_strokes=30, rounds_survived=4)
    finalist = ParticipantTotals(B, points=5, total_strokes=28, rounds_survived=3)

    assert [row.participant_id for row in rank_leaderboard([finalist, champion])] == [A, B]

    # ...and with the field left at its default, the ordering is the old one.
    assert [
        row.participant_id
        for row in rank_leaderboard([ParticipantTotals(A, 2, 30), ParticipantTotals(B, 5, 28)])
    ] == [B, A]


# ---------------------------------------------------------------------------
# Handicap allocation and net scoring (ADR-013)
# ---------------------------------------------------------------------------

HOLE_1 = uuid.uuid4()
HOLE_2 = uuid.uuid4()
HOLE_3 = uuid.uuid4()

# Holes 1, 2 and 3 of a loop, hardest first being 1 (SI 3), then 3 (SI 11), then
# 2 (SI 14) — deliberately not in hole order, because stroke index is what deals.
LOOP = [
    LoopHole(hole_id=HOLE_1, stroke_index=3),
    LoopHole(hole_id=HOLE_2, stroke_index=14),
    LoopHole(hole_id=HOLE_3, stroke_index=11),
]


@pytest.mark.parametrize(
    ("handicap", "shots"),
    [(0, 0), (2, 0), (3, 1), (8, 1), (9, 2), (18, 3), (24, 4), (54, 9)],
)
def test_a_handicap_is_pro_rated_to_the_loop(handicap: int, shots: int) -> None:
    # Three holes of eighteen, rounded half up: 3 is exactly 0.5 and goes to 1.
    assert shots_for_loop(handicap, 3) == shots


def test_pro_rating_uses_eighteen_whatever_the_course_holds() -> None:
    # The handicap is quoted against eighteen holes, so a club with nine entered
    # does not halve everybody's allowance.
    assert shots_for_loop(18, 3) == 3
    assert shots_for_loop(18, 9) == 9


def test_shots_are_dealt_to_the_hardest_holes_first() -> None:
    # Two shots over three holes go to the two hardest — 1 (SI 3) and 3 (SI 11).
    assert allocate_shots({A: 9}, LOOP)[A] == {HOLE_1: 1, HOLE_3: 1, HOLE_2: 0}


def test_shots_wrap_the_loop_when_there_are_more_than_holes() -> None:
    # Four shots: everyone gets one, and the hardest gets the extra.
    assert allocate_shots({A: 24}, LOOP)[A] == {HOLE_1: 2, HOLE_3: 1, HOLE_2: 1}


def test_every_hole_gets_an_entry_even_at_zero() -> None:
    # So a caller never has to tell "no shot here" from "not in the mapping".
    assert allocate_shots({A: 0}, LOOP)[A] == {HOLE_1: 0, HOLE_2: 0, HOLE_3: 0}


def test_holes_sharing_a_stroke_index_deal_deterministically() -> None:
    # Nothing stops a course having two holes on the same index, and the same card
    # must allocate the same way however the loop was ordered coming in.
    first = uuid.UUID(int=1)
    second = uuid.UUID(int=2)
    forwards = [LoopHole(first, 5), LoopHole(second, 5), LoopHole(HOLE_3, 11)]

    assert allocate_shots({A: 9}, forwards) == allocate_shots({A: 9}, list(reversed(forwards)))


def test_allocation_rejects_a_loop_with_no_holes() -> None:
    with pytest.raises(ValueError, match="no holes"):
        allocate_shots({A: 12}, [])


def test_allocation_rejects_a_negative_handicap() -> None:
    # Plus handicaps are out of scope (ADR-013) — a +2 pro-rates to zero shots over
    # three holes anyway, so the column would carry a sign that changes nothing.
    with pytest.raises(ValueError, match="cannot be negative"):
        allocate_shots({A: -2}, LOOP)


def test_a_net_winner_takes_a_hole_they_lost_on_gross() -> None:
    result = score_hole({A: 5, B: 6}, strokes_received={A: 0, B: 2})

    # B took more strokes and still wins it: 6 - 2 is 4, against A's 5.
    assert result.winner == B
    assert result.decided_by is DecidedBy.STROKES
    assert result.points == {A: 0, B: 1}


def test_shots_can_create_a_tie_that_gross_did_not_have() -> None:
    result = score_hole({A: 4, B: 5}, strokes_received={B: 1}, closest_to_pin=B)

    # Level on net, so the cascade drops to level 2 — which gross would never have
    # reached.
    assert result.winner == B
    assert result.decided_by is DecidedBy.CLOSEST_TO_PIN


def test_a_player_absent_from_the_allocation_receives_nothing() -> None:
    result = score_hole({A: 4, B: 4}, strokes_received={B: 1})

    assert result.winner == B


def test_net_may_be_zero_or_negative() -> None:
    # Three shots on a three. A player owed more shots than they took has played it
    # that well, and there is no floor on net — only on the gross a group reports.
    result = score_hole({A: 3, B: 7}, strokes_received={A: 3, B: 1})

    assert result.winner == A
    assert result.points == {A: 1, B: 0}


def test_gross_strokes_below_one_are_still_rejected() -> None:
    # The allocation is the server's; the strokes are the group's, and a group
    # cannot hole out in zero however many shots they are owed.
    with pytest.raises(ValueError, match="Strokes must be 1 or more"):
        score_hole({A: 0, B: 4}, strokes_received={A: 2})


def test_the_tie_break_guard_says_net_when_a_handicap_applied() -> None:
    # An error reading "fewest strokes" would send the reader to check the gross
    # numbers, where they would find no tie and no bug.
    with pytest.raises(ValueError, match="fewest net strokes"):
        score_hole({A: 4, B: 5}, strokes_received={B: 1}, closest_to_pin=C)


def test_a_scratch_event_is_the_function_it_always_was() -> None:
    # The guard that the default did not move: an empty allocation, an absent one,
    # and no argument at all must all be the same hole.
    plain = score_hole({A: 4, B: 4, C: 5}, closest_to_pin=A)

    assert score_hole({A: 4, B: 4, C: 5}, strokes_received={}, closest_to_pin=A) == plain
    assert score_hole({A: 4, B: 4, C: 5}, strokes_received=None, closest_to_pin=A) == plain
    assert plain.winner == A
