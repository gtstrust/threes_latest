from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    ParticipantServiceDep,
    RoundServiceDep,
    TournamentServiceDep,
    require_can_view,
)
from app.schemas.round import GroupRead

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
