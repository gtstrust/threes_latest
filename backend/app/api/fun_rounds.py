from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    FunRoundServiceDep,
    ParticipantServiceDep,
    PlayerServiceDep,
    require_organiser,
)
from app.models.tournament import Tournament
from app.schemas.fun_round import (
    FunRoundCreate,
    FunRoundDetail,
    FunRoundPreview,
    FunRoundRead,
    FunRoundStart,
)
from app.schemas.participant import ParticipantRead, SelfRegister, VirtualPlayerCreate
from app.schemas.round import RoundWithGroups
from app.services.fun_round import (
    FunRoundFull,
    FunRoundHolesUnavailable,
    FunRoundNotStartable,
    FunRoundNotStarted,
)
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
    except FunRoundHolesUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
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
    """The whole round — its field and, once started, its group. Players only.

    `require_can_view` is not reused here only because its wording is a
    tournament's, and the person most likely to meet this 403 is a mate who has
    just tapped an invite. They get sent to the preview instead of being told they
    aren't in a tournament they never heard of.
    """
    fun_round = await _fun_round_or_404(fun_round_id, service)
    if fun_round.organiser_id != current_user.id and (
        await participants.get_for_player(fun_round.id, current_user.id) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You're not in this round yet — join it first",
        )
    return await _detail(fun_round, service)


@router.get("/{fun_round_id}/preview", response_model=FunRoundPreview)
async def preview_fun_round(
    fun_round_id: UUID,
    current_user: CurrentUserDep,
    service: FunRoundServiceDep,
    players: PlayerServiceDep,
) -> FunRoundPreview:
    """Enough to recognise an invite and decide to join. Any signed-in caller.

    A fun round is invited by sharing its URL, so this one route is deliberately
    not view-guarded — guarding it would refuse exactly the people the link was
    sent to. It is safe to open because it carries nothing worth guarding: no
    field, no draw, no scores. That is the same trade ADR-010 makes for public
    channels, where a guessed topic reveals only that somebody scored.
    """
    fun_round = await _fun_round_or_404(fun_round_id, service)
    field = await service.list_field(fun_round)
    host = await players.get_by_id(fun_round.organiser_id)
    return FunRoundPreview.build(
        fun_round,
        host_name=(host.display_name or host.email) if host else "Someone",
        player_count=len(field),
        is_full=await service.is_full(fun_round),
    )


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
    except (
        FunRoundNotStartable,
        FunRoundHolesUnavailable,
        RoundNotDrawable,
        DrawNotPossible,
    ) as exc:
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
