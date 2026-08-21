from fastapi import APIRouter

from app.core.deps import CurrentUserDep
from app.core.security import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUser)
async def read_current_user(current_user: CurrentUserDep) -> CurrentUser:
    """Return the identity carried by the caller's verified Supabase JWT.

    Pure JWT introspection — no database access. Useful for a client/dev to
    confirm a token is valid independent of whether a `players` row exists yet.
    """
    return current_user
