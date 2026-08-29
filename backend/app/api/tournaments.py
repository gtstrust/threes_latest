from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    ParticipantServiceDep,
    TournamentServiceDep,
    reject_fun_round,
    require_can_view,
    require_organiser,
)
from app.models.tournament import Tournament
from app.schemas.join import JoinCodeRead
from app.services.participant import CapBelowField
from app.schemas.tournament import (
    TournamentCreate,
    TournamentRead,
    TournamentStatusUpdate,
    TournamentUpdate,
)
from app.services.tournament import (
    InvalidTransition,
    OrganiserProfileMissing,
    RoundDrivenStatus,
)

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


async def _get_or_404(tournament_id: UUID, service: TournamentServiceDep) -> Tournament:
    tournament = await service.get_by_id(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")
    return tournament


@router.post("", response_model=TournamentRead, status_code=status.HTTP_201_CREATED)
async def create_tournament(
    payload: TournamentCreate,
    current_user: CurrentUserDep,
    service: TournamentServiceDep,
) -> TournamentRead:
    """Create a tournament owned by the caller, in the CREATED state."""
    try:
        tournament = await service.create(current_user, payload)
    except OrganiserProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        ) from None
    return TournamentRead.model_validate(tournament)


@router.get("", response_model=list[TournamentRead])
async def list_my_tournaments(
    current_user: CurrentUserDep, service: TournamentServiceDep
) -> list[TournamentRead]:
    """List tournaments the caller organises, newest first."""
    tournaments = await service.list_for_organiser(current_user.id)
    return [TournamentRead.model_validate(tournament) for tournament in tournaments]


@router.get("/{tournament_id}", response_model=TournamentRead)
async def read_tournament(
    tournament_id: UUID,
    current_user: CurrentUserDep,
    service: TournamentServiceDep,
    participants: ParticipantServiceDep,
) -> TournamentRead:
    tournament = await _get_or_404(tournament_id, service)
    await require_can_view(tournament, current_user, participants)
    return TournamentRead.for_viewer(tournament, current_user.id)


@router.post("/{tournament_id}/join-code", response_model=JoinCodeRead)
async def regenerate_join_code(
    tournament_id: UUID,
    current_user: CurrentUserDep,
    service: TournamentServiceDep,
) -> JoinCodeRead:
    """Mint a new invitation, retiring the old one. Organiser only.

    The reason the invitation is a code rather than the tournament's id: a QR
    printed on a sign outlives the day it was printed for, and a link passed on
    beyond the guest list has to be withdrawable without deleting the event.
    """
    tournament = await _get_or_404(tournament_id, service)
    reject_fun_round(tournament)
    require_organiser(tournament, current_user)
    updated = await service.regenerate_join_code(tournament)
    return JoinCodeRead(join_code=updated.join_code)


@router.patch("/{tournament_id}", response_model=TournamentRead)
async def update_tournament(
    tournament_id: UUID,
    updates: TournamentUpdate,
    current_user: CurrentUserDep,
    service: TournamentServiceDep,
    participants: ParticipantServiceDep,
) -> TournamentRead:
    tournament = await _get_or_404(tournament_id, service)
    reject_fun_round(tournament)
    require_organiser(tournament, current_user)
    if "max_players" in updates.model_fields_set:
        try:
            await participants.require_cap_fits_field(tournament, updates.max_players)
        except CapBelowField as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    updated = await service.update_details(tournament, updates)
    return TournamentRead.for_viewer(updated, current_user.id)


@router.post("/{tournament_id}/status", response_model=TournamentRead)
async def change_tournament_status(
    tournament_id: UUID,
    payload: TournamentStatusUpdate,
    current_user: CurrentUserDep,
    service: TournamentServiceDep,
) -> TournamentRead:
    """Move a tournament through the ADR-003 state machine.

    Handles the registration transitions and finishing the tournament.
    ROUND_IN_PROGRESS and ROUND_COMPLETE are not settable here — they belong to
    the round endpoints, so drawing a round and starting play stay a single
    action rather than two that can disagree.

    Illegal moves are rejected with 409 rather than 400: the request is
    well-formed, it just conflicts with the tournament's current state.
    """
    tournament = await _get_or_404(tournament_id, service)
    reject_fun_round(tournament)
    require_organiser(tournament, current_user)
    try:
        updated = await service.transition(tournament, payload.status)
    except (InvalidTransition, RoundDrivenStatus) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TournamentRead.model_validate(updated)
