from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.deps import CurrentUserDep

router = APIRouter(prefix="/rounds", tags=["rounds"])


@router.get("", response_model=None)
async def list_rounds(current_user: CurrentUserDep) -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": "Rounds endpoints not yet implemented"})
