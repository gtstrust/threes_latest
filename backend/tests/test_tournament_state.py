"""Tests for the ADR-003 state machine. Pure — no database involved."""

import pytest

from app.models.tournament import TournamentStatus
from app.services.tournament import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    can_transition,
)

LINEAR_PATH = [
    TournamentStatus.CREATED,
    TournamentStatus.REGISTRATION_OPEN,
    TournamentStatus.REGISTRATION_CLOSED,
    TournamentStatus.ROUND_IN_PROGRESS,
    TournamentStatus.ROUND_COMPLETE,
    TournamentStatus.TOURNAMENT_COMPLETE,
]


def test_every_status_has_an_entry() -> None:
    """A missing key would raise KeyError at runtime rather than refusing a move."""
    assert set(ALLOWED_TRANSITIONS) == set(TournamentStatus)


@pytest.mark.parametrize(
    ("current", "target"),
    list(zip(LINEAR_PATH[:-1], LINEAR_PATH[1:], strict=True)),
)
def test_the_documented_linear_path_is_walkable(
    current: TournamentStatus, target: TournamentStatus
) -> None:
    assert can_transition(current, target)


def test_a_completed_tournament_is_terminal() -> None:
    assert ALLOWED_TRANSITIONS[TournamentStatus.TOURNAMENT_COMPLETE] == frozenset()

    for status in TournamentStatus:
        assert not can_transition(TournamentStatus.TOURNAMENT_COMPLETE, status)


def test_a_finished_round_can_start_another_one() -> None:
    """The one non-linear edge: tournaments run more than a single 3-hole loop."""
    assert can_transition(TournamentStatus.ROUND_COMPLETE, TournamentStatus.ROUND_IN_PROGRESS)


def test_registration_cannot_be_reopened() -> None:
    assert not can_transition(
        TournamentStatus.REGISTRATION_CLOSED, TournamentStatus.REGISTRATION_OPEN
    )


@pytest.mark.parametrize("status", list(TournamentStatus))
def test_a_status_cannot_transition_to_itself(status: TournamentStatus) -> None:
    assert not can_transition(status, status)


def test_states_cannot_be_skipped() -> None:
    assert not can_transition(TournamentStatus.CREATED, TournamentStatus.ROUND_IN_PROGRESS)
    assert not can_transition(
        TournamentStatus.REGISTRATION_OPEN, TournamentStatus.TOURNAMENT_COMPLETE
    )


def test_a_tournament_cannot_run_before_registration_closes() -> None:
    assert not can_transition(
        TournamentStatus.REGISTRATION_OPEN, TournamentStatus.ROUND_IN_PROGRESS
    )


def test_invalid_transition_error_names_what_was_allowed() -> None:
    error = InvalidTransition(TournamentStatus.CREATED, TournamentStatus.ROUND_COMPLETE)

    message = str(error)
    assert "CREATED" in message
    assert "ROUND_COMPLETE" in message
    assert "REGISTRATION_OPEN" in message  # what it should have done instead


def test_invalid_transition_from_a_terminal_state_says_so() -> None:
    error = InvalidTransition(
        TournamentStatus.TOURNAMENT_COMPLETE, TournamentStatus.ROUND_IN_PROGRESS
    )

    assert "terminal" in str(error)
