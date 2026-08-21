from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.deps import CurrentUserDep

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=None)
async def list_groups(current_user: CurrentUserDep) -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": "Groups endpoints not yet implemented"})
