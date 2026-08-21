from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, decode_supabase_jwt
from app.services.player import PlayerService

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> CurrentUser:
    return decode_supabase_jwt(credentials.credentials)


async def get_player_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlayerService:
    return PlayerService(session)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
PlayerServiceDep = Annotated[PlayerService, Depends(get_player_service)]
