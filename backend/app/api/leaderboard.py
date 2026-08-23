from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    LeaderboardServiceDep,
    ParticipantServiceDep,
    RoundServiceDep,
    TournamentServiceDep,
    require_can_view,
)
from app.schemas.leaderboard import LeaderboardEntryRead, LeaderboardRead

router = APIRouter(tags=["leaderboard"])


@router.get("/tournaments/{tournament_id}/leaderboard", response_model=LeaderboardRead)
async def read_tournament_leaderboard(
    tournament_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    participants: ParticipantServiceDep,
    leaderboard: LeaderboardServiceDep,
) -> LeaderboardRead:
    """Cumulative standings across every round played so far.

    Valid before a ball is struck: the whole field comes back on nothing, which
    is what an organiser checking their setup expects to see.
    """
    tournament = await tournaments.get_by_id(tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")

    await require_can_view(tournament, current_user, participants)

    entries = await leaderboard.for_tournament(tournament)
    return LeaderboardRead(
        tournament_id=tournament.id,
        round_id=None,
        entries=[LeaderboardEntryRead.model_validate(entry) for entry in entries],
    )


@router.get("/rounds/{round_id}/leaderboard", response_model=LeaderboardRead)
async def read_round_leaderboard(
    round_id: UUID,
    current_user: CurrentUserDep,
    tournaments: TournamentServiceDep,
    rounds: RoundServiceDep,
    participants: ParticipantServiceDep,
    leaderboard: LeaderboardServiceDep,
) -> LeaderboardRead:
    """Standings for one round, over the players drawn into it."""
    round_ = await rounds.get_by_id(round_id)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Round not found")

    tournament = await tournaments.get_by_id(round_.tournament_id)
    if tournament is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Round not found")

    await require_can_view(tournament, current_user, participants)

    entries = await leaderboard.for_round(round_)
    return LeaderboardRead(
        tournament_id=tournament.id,
        round_id=round_.id,
        entries=[LeaderboardEntryRead.model_validate(entry) for entry in entries],
    )
