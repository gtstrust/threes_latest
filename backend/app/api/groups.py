from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    AdvancementServiceDep,
    CurrentUserDep,
    ParticipantServiceDep,
    RoundServiceDep,
    TournamentServiceDep,
    reject_fun_round,
    require_can_view,
    require_organiser,
)
from app.schemas.round import GroupAdvancementWrite, GroupRead
from app.services.advancement import (
    AdvancementNotOpen,
    AlreadyAdvanced,
    NotAKnockout,
    NotInGroup,
)

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("/{group_id}", response_model=GroupRead)
async def read_group(
    group_id: UUID,
    current_user: CurrentUserDep,
    rounds: RoundServiceDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
) -> GroupRead:
    """One group with its members and the loop it's playing."""
    group = await rounds.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    round_ = await rounds.get_by_id(group.round_id)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    tournament = await tournaments.get_by_id(round_.tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    await require_can_view(tournament, current_user, participants)
    return GroupRead.model_validate(group)


@router.post("/{group_id}/advancement", response_model=GroupRead)
async def set_group_advancement(
    group_id: UUID,
    payload: GroupAdvancementWrite,
    current_user: CurrentUserDep,
    rounds: RoundServiceDep,
    advancement: AdvancementServiceDep,
) -> GroupRead:
    """Send a player through from a group nothing could separate (ADR-012).

    The backstop for the one case the cascade cannot settle: a group that
    finished completely all square, level on points and strokes with no hole won
    by anyone. Points come only from winning holes, so that is the *only* time
    this is needed — and it is the organiser's call because they are standing
    there and the data is not going to produce an answer.

    Not an edit of a result: a group that already has a verdict is refused. No
    realtime broadcast either — ADR-010 says only score entry signals, and a
    client learns a draw change on its own refresh.
    """
    context = await rounds.get_group_context(group_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    group, round_, tournament = context
    reject_fun_round(tournament)
    require_organiser(tournament, current_user)

    try:
        decided = await advancement.adjudicate(
            tournament=tournament,
            round_=round_,
            group=group,
            participant_id=payload.participant_id,
        )
    except NotInGroup as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except (NotAKnockout, AdvancementNotOpen, AlreadyAdvanced) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return GroupRead.model_validate(decided)
