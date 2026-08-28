from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    ParticipantServiceDep,
    TournamentServiceDep,
    reject_fun_round,
    require_organiser,
)
from app.models.participant import TournamentParticipant
from app.models.tournament import Tournament
from app.schemas.participant import ParticipantRead, SelfRegister, VirtualPlayerCreate
from app.services.participant import (
    AlreadyRegistered,
    FieldLocked,
    PlayerProfileMissing,
    RegistrationClosed,
)

router = APIRouter(prefix="/tournaments/{tournament_id}/participants", tags=["participants"])


async def _tournament_or_404(tournament_id: UUID, service: TournamentServiceDep) -> Tournament:
    tournament = await service.get_by_id(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")
    return tournament


async def _participant_or_404(
    tournament: Tournament, participant_id: UUID, service: ParticipantServiceDep
) -> TournamentParticipant:
    participant = await service.get_by_id(participant_id)
    # Check the parent too, so a valid id from another tournament reads as
    # not-found here rather than being removable through the wrong URL.
    if participant is None or participant.tournament_id != tournament.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participant not found")
    return participant


@router.post("", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED)
async def register_self(
    tournament_id: UUID,
    payload: SelfRegister,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
) -> ParticipantRead:
    """Register the caller in this tournament.

    The invitation is the tournament's join code, not its id — `POST /join/{code}`
    is the route a player actually arrives through. This one stays because it is
    the direct form for a caller who already knows the tournament, and because the
    join route delegates the rule it enforces (registration must be open) here.
    """
    tournament = await _tournament_or_404(tournament_id, tournaments)
    reject_fun_round(tournament)
    try:
        participant = await participants.self_register(
            tournament, current_user, payload.display_name
        )
    except PlayerProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        ) from None
    except (RegistrationClosed, AlreadyRegistered) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ParticipantRead.model_validate(participant)


@router.post("/virtual", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED)
async def add_virtual_player(
    tournament_id: UUID,
    payload: VirtualPlayerCreate,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
) -> ParticipantRead:
    """Add a player who has no account, scored by someone else in their group."""
    tournament = await _tournament_or_404(tournament_id, tournaments)
    reject_fun_round(tournament)
    require_organiser(tournament, current_user)
    try:
        participant = await participants.add_virtual_player(tournament, payload.display_name)
    except FieldLocked as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ParticipantRead.model_validate(participant)


@router.get("", response_model=list[ParticipantRead])
async def list_participants(
    tournament_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
) -> list[ParticipantRead]:
    """List the field, in registration order. Visible to the organiser and players in it."""
    tournament = await _tournament_or_404(tournament_id, tournaments)
    field = await participants.list_for_tournament(tournament.id)

    if tournament.organiser_id != current_user.id and not any(
        entry.player_id == current_user.id for entry in field
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organiser and players in this tournament can see the field",
        )

    return [ParticipantRead.model_validate(entry) for entry in field]


@router.delete("/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_participant(
    tournament_id: UUID,
    participant_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
) -> None:
    """Remove someone from the field.

    Organiser-only, and allowed right up until play starts — the state machine
    can't reopen registration, so without this a no-show would be stuck in the
    draw with no way to take them out.
    """
    tournament = await _tournament_or_404(tournament_id, tournaments)
    reject_fun_round(tournament)
    require_organiser(tournament, current_user)
    participant = await _participant_or_404(tournament, participant_id, participants)
    try:
        await participants.remove(tournament, participant)
    except FieldLocked as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
