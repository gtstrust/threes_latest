"""Accepting an invitation.

The one route in the app reachable by someone with no relationship to the event
yet — which is the point. Every other read is guarded, and guarding an invitation
refuses exactly the people it was sent to: before this existed, a player sent a
tournament link met "Only the organiser and players in this tournament can view
it", with the join button sitting behind the very fetch that failed.

Safe to open because the code is the credential and the preview carries nothing
worth guarding: the event's name, who is running it, and how many are in. Not the
field, not the draw, not a score. Same trade ADR-010 makes for public channels.
"""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    FunRoundServiceDep,
    ParticipantServiceDep,
    PlayerServiceDep,
    TournamentServiceDep,
)
from app.models.tournament import Tournament, TournamentKind, TournamentStatus
from app.schemas.join import JoinPreview
from app.schemas.participant import ParticipantRead, SelfRegister
from app.services.fun_round import FunRoundFull
from app.services.participant import (
    AlreadyRegistered,
    FieldFull,
    PlayerProfileMissing,
    RegistrationClosed,
)

router = APIRouter(prefix="/join", tags=["join"])


async def _by_code(code: str, tournaments: TournamentServiceDep) -> Tournament:
    event = await tournaments.get_by_join_code(code)
    if event is None:
        # Deliberately the same answer as a code that never existed: a regenerated
        # invitation must not be distinguishable from a typo, or the old link
        # confirms the event is still there.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No event with that code. Check the link, or ask for a new one.",
        )
    return event


async def _can_join(
    event: Tournament,
    participants: ParticipantServiceDep,
    fun_rounds: FunRoundServiceDep,
) -> bool:
    """Whether the button would work, so the client can say why not.

    Both kinds have a ceiling, reached differently: a fun round is one group and
    so is fixed at four, while a tournament's is whatever the organiser set, if
    anything.
    """
    if event.status is not TournamentStatus.REGISTRATION_OPEN:
        return False
    if event.kind is TournamentKind.FUN_ROUND:
        return not await fun_rounds.is_full(event)
    return not await participants.is_full(event)


@router.get("/{code}", response_model=JoinPreview)
async def preview_invitation(
    code: str,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
    fun_rounds: FunRoundServiceDep,
    players: PlayerServiceDep,
) -> JoinPreview:
    """What you were invited to. Any signed-in caller holding the code."""
    event = await _by_code(code, tournaments)
    field = await participants.list_for_tournament(event.id)
    host = await players.get_by_id(event.organiser_id)
    return JoinPreview.build(
        event,
        host_name=(host.display_name or host.email) if host else "Someone",
        player_count=len(field),
        can_join=await _can_join(event, participants, fun_rounds),
    )


@router.post("/{code}", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED)
async def accept_invitation(
    code: str,
    payload: SelfRegister,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
    fun_rounds: FunRoundServiceDep,
) -> ParticipantRead:
    """Take your place in the event this code names.

    A fun round goes through `FunRoundService.join` rather than straight to
    `self_register`, so its single-group cap keeps enforcing itself here — the cap
    is a rule about fun rounds, not about the endpoint that happens to be joining.
    """
    event = await _by_code(code, tournaments)
    try:
        if event.kind is TournamentKind.FUN_ROUND:
            participant = await fun_rounds.join(event, current_user, payload.display_name)
        else:
            participant = await participants.self_register(
                event, current_user, payload.display_name
            )
    except PlayerProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        ) from None
    except (RegistrationClosed, AlreadyRegistered, FunRoundFull, FieldFull) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ParticipantRead.model_validate(participant)
