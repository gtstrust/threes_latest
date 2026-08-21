from uuid import UUID

import jwt
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.core.config import settings


class CurrentUser(BaseModel):
    """The authenticated principal, derived directly from a verified Supabase JWT."""

    id: UUID
    email: str | None = None


def decode_supabase_jwt(token: str) -> CurrentUser:
    """Verify a Supabase-issued access token and return the identity it carries.

    Targets Supabase's documented shared-secret (SUPABASE_JWT_SECRET) HS256 flow.
    If a project migrates to JWKS/asymmetric signing later, only this function
    needs to change — callers depend on the CurrentUser contract, not the algorithm.
    """
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth is not configured: SUPABASE_JWT_SECRET is unset",
        )

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return CurrentUser(id=UUID(subject), email=payload.get("email"))
