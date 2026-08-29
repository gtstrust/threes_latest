"""Routes called by machines rather than people.

One today: the reminder sweep, which a scheduler hits so events coming up get
mailed without an organiser having to remember. It sits apart from the rest of
the API because it authenticates differently — there is no player behind it, so
there is no bearer token to verify and no `CurrentUser` to derive.

**A shared secret, not a JWT.** The alternative is minting a token for a robot,
which means either a long-lived credential that looks exactly like a player's or
a service account this app has no concept of. A header compared against one
setting is smaller and says plainly what it is.

**Unset means closed.** A route that mails an entire field must not be open by
default, so a missing `CRON_SECRET` refuses everything rather than skipping the
check — the failure mode of the opposite choice is a stranger mailing your
players, and it would be invisible until they told you.
"""

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import is_configured, settings
from app.core.deps import ReminderServiceDep
from app.schemas.reminder import SweepResultRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

CRON_HEADER = "X-Cron-Key"


def _require_cron_key(provided: str | None) -> None:
    """Check the caller holds the scheduler's secret.

    `compare_digest` rather than `==`: the comparison is against a fixed secret
    over a network, which is the textbook shape for a timing oracle. Cheap
    insurance on a route worth guarding.
    """
    if not is_configured(settings.cron_secret):
        # 404, not 503: an unconfigured internal route should not advertise that
        # it exists and is merely switched off.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    assert settings.cron_secret is not None  # narrowed by is_configured
    if provided is None or not secrets.compare_digest(provided, settings.cron_secret):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad cron key")


@router.post("/reminders/sweep", response_model=SweepResultRead)
async def sweep_reminders(
    reminders: ReminderServiceDep,
    x_cron_key: Annotated[str | None, Header(alias=CRON_HEADER)] = None,
) -> SweepResultRead:
    """Mail every event coming up that hasn't been told yet.

    Awaited rather than backgrounded, unlike the organiser's own send: a scheduler
    wants the answer to "did that work?" in the response it already waits for, and
    there is no person here for a slow provider to keep waiting.

    Idempotent by construction. The query excludes events that already have an
    UPCOMING reminder recorded, so a run that fails halfway through can simply be
    run again — what has been sent is established by what happened, not by a flag
    somebody has to remember to set.
    """
    _require_cron_key(x_cron_key)

    handled = await reminders.sweep(settings.app_url)
    logger.info("Reminder sweep mailed %d event(s)", len(handled))
    return SweepResultRead(events_reminded=len(handled))
