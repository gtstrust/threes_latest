from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth,
    courses,
    groups,
    participants,
    players,
    rounds,
    scores,
    tournaments,
)
from app.core.config import settings
from app.schemas.common import HealthResponse

app = FastAPI(title="Threes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(players.router)
app.include_router(courses.router)
app.include_router(tournaments.router)
app.include_router(participants.router)
app.include_router(rounds.router)
app.include_router(groups.router)
app.include_router(scores.router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
