from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.deps import CurrentUserDep

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.get("", response_model=None)
async def list_tournaments(current_user: CurrentUserDep) -> JSONResponse:
    return JSONResponse(
        status_code=501, content={"detail": "Tournaments endpoints not yet implemented"}
    )
