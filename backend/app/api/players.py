from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUserDep, PlayerServiceDep, TournamentServiceDep
from app.schemas.player import PlayerRead, PlayerUpdate
from app.schemas.tournament import TournamentRead

router = APIRouter(prefix="/players", tags=["players"])


@router.post("", response_model=PlayerRead)
async def provision_profile(
    current_user: CurrentUserDep, player_service: PlayerServiceDep
) -> PlayerRead:
    """Idempotently ensure a profile row exists for the authenticated user.

    Intended to be called once by the client immediately after Supabase
    magic-link login. Safe to call repeatedly.
    """
    player = await player_service.get_or_create_profile(current_user)
    return PlayerRead.model_validate(player)


@router.get("/me", response_model=PlayerRead)
async def read_my_profile(
    current_user: CurrentUserDep, player_service: PlayerServiceDep
) -> PlayerRead:
    player = await player_service.get_by_id(current_user.id)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        )
    return PlayerRead.model_validate(player)


@router.patch("/me", response_model=PlayerRead)
async def update_my_profile(
    updates: PlayerUpdate,
    current_user: CurrentUserDep,
    player_service: PlayerServiceDep,
) -> PlayerRead:
    player = await player_service.get_by_id(current_user.id)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        )
    updated = await player_service.update_profile(player, updates)
    return PlayerRead.model_validate(updated)


@router.get("/me/tournaments", response_model=list[TournamentRead])
async def list_my_tournaments(
    current_user: CurrentUserDep, tournaments: TournamentServiceDep
) -> list[TournamentRead]:
    """Tournaments the caller is *playing in*, newest first.

    Distinct from `GET /tournaments`, which lists what they organise. Without
    this a player has no way to find an event: they can read one by id, since
    `require_can_view` admits the field, but nothing tells them the id — so
    losing the invitation link would strand them mid-day.

    Virtual players never appear here. They have no account to call the API with.
    """
    playing = await tournaments.list_for_player(current_user.id)
    return [TournamentRead.model_validate(tournament) for tournament in playing]


@router.get("/{player_id}", response_model=PlayerRead)
async def read_player(
    player_id: UUID, current_user: CurrentUserDep, player_service: PlayerServiceDep
) -> PlayerRead:
    player = await player_service.get_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return PlayerRead.model_validate(player)
