from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.deps import CurrentUserDep

router = APIRouter(prefix="/scores", tags=["scores"])


@router.get("", response_model=None)
async def list_scores(current_user: CurrentUserDep) -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": "Scores endpoints not yet implemented"})
