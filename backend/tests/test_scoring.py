"""Tests for the ADR-007 scoring engine.

CLAUDE.md calls the scoring engine the most critical business logic on the
platform, so the cascade is covered level by level, including the cases where a
tie-break flag is present but unusable.
"""

import uuid

import pytest

from app.services.scoring import (
    DecidedBy,
    LeaderboardRow,
    ParticipantTotals,
    rank_leaderboard,
    score_hole,
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
