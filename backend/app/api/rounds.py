from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    ParticipantServiceDep,
    RoundServiceDep,
    TournamentServiceDep,
    reject_fun_round,
    require_can_view,
    require_organiser,
)
from app.models.round import Round
from app.models.tournament import Tournament
from app.schemas.round import RoundDraw, RoundRead, RoundWithGroups
from app.services.round import (
    DrawNotPossible,
    RoundNotDrawable,
    RoundNotInProgress,
)

router = APIRouter(tags=["rounds"])


async def _tournament_or_404(tournament_id: UUID, service: TournamentServiceDep) -> Tournament:
    tournament = await service.get_by_id(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")
    return tournament


async def _round_or_404(round_id: UUID, service: RoundServiceDep) -> Round:
    round_ = await service.get_by_id(round_id)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Round not found")
    return round_


@router.post(
    "/tournaments/{tournament_id}/rounds",
    response_model=RoundWithGroups,
    status_code=status.HTTP_201_CREATED,
)
async def draw_round(
    tournament_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    rounds: RoundServiceDep,
    # Last, and defaulted, so a bodyless POST still draws the whole course —
    # that was the only way to call this until now. A required schema whose
    # fields are all optional would 422 on a missing body, which is a nasty
    # thing to do to a caller that has not changed.
    payload: RoundDraw | None = None,
) -> RoundWithGroups:
    """Draw the next round and start play.

    This is the only way a tournament reaches ROUND_IN_PROGRESS — drawing the
    groups and moving the status are one action, so the two can't disagree.

    Send `hole_numbers` to play part of the course — `{"hole_numbers": [7, 8, 9]}`
    for a match over the back three of the front nine. The tournament stays
    attached to the real course; the holes played are recorded against the round.
    """
    tournament = await _tournament_or_404(tournament_id, tournaments)
    reject_fun_round(tournament)
    require_organiser(tournament, current_user)
    try:
        round_ = await rounds.draw_round(tournament, payload.hole_numbers if payload else None)
    except (RoundNotDrawable, DrawNotPossible) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RoundWithGroups.model_validate(round_)


@router.get("/tournaments/{tournament_id}/rounds", response_model=list[RoundRead])
async def list_rounds(
    tournament_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    rounds: RoundServiceDep,
    participants: ParticipantServiceDep,
) -> list[RoundRead]:
    tournament = await _tournament_or_404(tournament_id, tournaments)
    await require_can_view(tournament, current_user, participants)
    return [
        RoundRead.model_validate(round_)
        for round_ in await rounds.list_for_tournament(tournament.id)
    ]


@router.get("/rounds/{round_id}", response_model=RoundWithGroups)
async def read_round(
    round_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    rounds: RoundServiceDep,
    participants: ParticipantServiceDep,
) -> RoundWithGroups:
    """The draw: every group with its members and its loop."""
    round_ = await _round_or_404(round_id, rounds)
    tournament = await _tournament_or_404(round_.tournament_id, tournaments)
    await require_can_view(tournament, current_user, participants)

    detailed = await rounds.get_with_groups(round_.id)
    if detailed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Round not found")
    return RoundWithGroups.model_validate(detailed)


@router.post("/rounds/{round_id}/complete", response_model=RoundRead)
async def complete_round(
    round_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    rounds: RoundServiceDep,
) -> RoundRead:
    """Finish a round, moving both it and its tournament to complete."""
    round_ = await _round_or_404(round_id, rounds)
    tournament = await _tournament_or_404(round_.tournament_id, tournaments)
    require_organiser(tournament, current_user)
    try:
        completed = await rounds.complete_round(tournament, round_)
    except RoundNotInProgress as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return RoundRead.model_validate(completed)
