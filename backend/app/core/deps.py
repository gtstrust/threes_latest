from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, decode_supabase_jwt
from app.models.tournament import Tournament
from app.services.player import PlayerService
from app.services.tournament import TournamentService

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> CurrentUser:
    return decode_supabase_jwt(credentials.credentials)


async def get_player_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlayerService:
    return PlayerService(session)


async def get_tournament_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TournamentService:
    return TournamentService(session)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
PlayerServiceDep = Annotated[PlayerService, Depends(get_player_service)]
TournamentServiceDep = Annotated[TournamentService, Depends(get_tournament_service)]


def require_organiser(tournament: Tournament, current_user: CurrentUser) -> None:
    """Guard actions only a tournament's organiser may take.

    Until now the only authorization in the app was "holds a valid JWT". Anything
    that changes a tournament — its details, its status, and later its rounds —
    goes through here rather than through ad-hoc checks in each route.
    """
    if tournament.organiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organiser of this tournament can do that",
        )


def require_can_view(tournament: Tournament, current_user: CurrentUser) -> None:
    """Guard reading a tournament.

    TODO(M3): widen to registered participants. Participants don't exist as a
    concept yet, so today this is organiser-only; a player invited to an event
    cannot read it until the participants table lands.
    """
    require_organiser(tournament, current_user)
