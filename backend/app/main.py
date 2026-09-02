import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth,
    courses,
    fun_rounds,
    groups,
    internal,
    join,
    leaderboard,
    participants,
    players,
    rounds,
    scores,
    tournaments,
)
from app.core.config import settings
from app.core.errors import CatchUnhandledErrors
from app.schemas.common import HealthResponse

# Uvicorn configures its own loggers and adds no handler to the root one, so
# without this anything logged outside `uvicorn.*` falls through to
# `logging.lastResort` and arrives unformatted, or not at all. Uvicorn's loggers
# do not propagate, so this adds no duplicate access log. It is what makes the
# traceback in `CatchUnhandledErrors` — and config.py's DATABASE_URL warning —
# actually reach `fly logs`.
logging.basicConfig(level=logging.INFO)

API_DESCRIPTION = """\
Short-form competitive golf: 3-hole loops instead of 18-hole rounds.

### Authenticating

Every route but `GET /health` needs a bearer token, and **this API has no login
endpoint**. Supabase Auth issues tokens directly to the client (magic link) and
this server only verifies them, so there is nothing here to POST credentials to.

* **In a browser** — the frontend signs in through Supabase and sends the
  `access_token` from the session.
* **Locally, or to use *Authorize* below** —
  `python scripts/dev_token.py --email you@example.com` signs one with
  `SUPABASE_JWT_SECRET`. Development only.

`GET /auth/me` returns the claims a token carries without a database lookup, so
it answers "is my token good?" separately from "do I have a profile?".
`POST /players` is the idempotent call that creates the profile, and must be made
once after signing in before anything else will find you.
"""

app = FastAPI(title="Threes API", description=API_DESCRIPTION)

# Order is the point, and it reads backwards: `add_middleware` inserts at the
# front, so the *last* one added is the outermost. CORS must be outside the error
# handler, or the 500 it writes goes out without CORS headers and the browser
# reports a CORS failure instead of the error. See `app/core/errors.py`.
app.add_middleware(CatchUnhandledErrors)

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
app.include_router(fun_rounds.router)
app.include_router(join.router)
app.include_router(internal.router)
app.include_router(groups.router)
app.include_router(scores.router)
app.include_router(leaderboard.router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
