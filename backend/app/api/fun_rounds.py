from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    FunRoundServiceDep,
    ParticipantServiceDep,
    require_can_view,
    require_organiser,
)
from app.models.tournament import Tournament
from app.schemas.fun_round import (
    FunRoundCreate,
    FunRoundDetail,
    FunRoundRead,
    FunRoundStart,
)
from app.schemas.participant import ParticipantRead, SelfRegister, VirtualPlayerCreate
from app.schemas.round import RoundWithGroups
from app.services.fun_round import FunRoundFull, FunRoundNotStartable, FunRoundNotStarted
from app.services.participant import (
    AlreadyRegistered,
    FieldLocked,
    PlayerProfileMissing,
    RegistrationClosed,
)
from app.services.round import DrawNotPossible, RoundNotDrawable, RoundNotInProgress
from app.services.tournament import OrganiserProfileMissing

router = APIRouter(prefix="/fun-rounds", tags=["fun-rounds"])


async def _fun_round_or_404(fun_round_id: UUID, service: FunRoundServiceDep) -> Tournament:
    fun_round = await service.get_by_id(fun_round_id)
    if fun_round is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fun round not found")
    return fun_round


async def _detail(fun_round: Tournament, service: FunRoundServiceDep) -> FunRoundDetail:
    field = await service.list_field(fun_round)
    round_ = await service.get_round(fun_round)
    return FunRoundDetail.build(
        fun_round,
        [ParticipantRead.model_validate(entry) for entry in field],
        RoundWithGroups.model_validate(round_) if round_ is not None else None,
    )


@router.post("", response_model=FunRoundDetail, status_code=status.HTTP_201_CREATED)
async def create_fun_round(
    payload: FunRoundCreate,
    current_user: CurrentUserDep,
    service: FunRoundServiceDep,
) -> FunRoundDetail:
    """Start a fun round: it opens for joining and puts you in the field as host."""
    try:
        fun_round = await service.create(current_user, payload)
    except OrganiserProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        ) from None
    return await _detail(fun_round, service)


@router.get("", response_model=list[FunRoundRead])
async def list_fun_rounds(
    current_user: CurrentUserDep, service: FunRoundServiceDep
) -> list[FunRoundRead]:
    """The caller's fun rounds — ones they host and ones they've joined, newest first."""
    fun_rounds = await service.list_for_player(current_user.id)
    return [FunRoundRead.from_model(fun_round) for fun_round in fun_rounds]


@router.get("/{fun_round_id}", response_model=FunRoundDetail)
async def read_fun_round(
    fun_round_id: UUID,
    current_user: CurrentUserDep,
    service: FunRoundServiceDep,
    participants: ParticipantServiceDep,
) -> FunRoundDetail:
    fun_round = await _fun_round_or_404(fun_round_id, service)
    await require_can_view(fun_round, current_user, participants)
    return await _detail(fun_round, service)


@router.post(
    "/{fun_round_id}/players", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED
)
async def join_fun_round(
    fun_round_id: UUID,
    payload: SelfRegister,
    current_user: CurrentUserDep,
    service: FunRoundServiceDep,
) -> ParticipantRead:
    """Join a fun round you were sent the link to. Anyone authenticated may join."""
    fun_round = await _fun_round_or_404(fun_round_id, service)
    try:
        participant = await service.join(fun_round, current_user, payload.display_name)
    except PlayerProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        ) from None
    except (FunRoundFull, RegistrationClosed, AlreadyRegistered) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ParticipantRead.model_validate(participant)


@router.post(
    "/{fun_round_id}/virtual", response_model=ParticipantRead, status_code=status.HTTP_201_CREATED
)
async def add_virtual_to_fun_round(
    fun_round_id: UUID,
    payload: VirtualPlayerCreate,
    current_user: CurrentUserDep,
    service: FunRoundServiceDep,
) -> ParticipantRead:
    """Add a mate with no account, whose scores the host enters. Host only."""
    fun_round = await _fun_round_or_404(fun_round_id, service)
    require_organiser(fun_round, current_user)
    try:
        participant = await service.add_virtual(fun_round, payload.display_name)
    except (FunRoundFull, FieldLocked) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ParticipantRead.model_validate(participant)


@router.post("/{fun_round_id}/start", response_model=FunRoundDetail)
async def start_fun_round(
    fun_round_id: UUID,
    current_user: CurrentUserDep,
    service: FunRoundServiceDep,
    payload: FunRoundStart | None = None,
) -> FunRoundDetail:
    """Close joining and draw the single group over its 3-hole loop. Host only."""
    fun_round = await _fun_round_or_404(fun_round_id, service)
    require_organiser(fun_round, current_user)
    try:
        await service.start(fun_round, payload.hole_numbers if payload else None)
    except (FunRoundNotStartable, RoundNotDrawable, DrawNotPossible) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(fun_round, service)


@router.post("/{fun_round_id}/finish", response_model=FunRoundDetail)
async def finish_fun_round(
    fun_round_id: UUID,
    current_user: CurrentUserDep,
    service: FunRoundServiceDep,
) -> FunRoundDetail:
    """End the round and mark the fun round complete. Host only."""
    fun_round = await _fun_round_or_404(fun_round_id, service)
    require_organiser(fun_round, current_user)
    try:
        await service.finish(fun_round)
    except (FunRoundNotStarted, RoundNotInProgress) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await _detail(fun_round, service)
