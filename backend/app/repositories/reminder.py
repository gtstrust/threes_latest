from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reminder import ReminderKind, TournamentReminder
from app.models.tournament import Tournament, TournamentKind, TournamentStatus

# The statuses an event can be reminded about. Once a round is in progress the
# players are on the course and a reminder is noise; once it is complete it is
# an untruth.
REMINDABLE_STATES = (
    TournamentStatus.REGISTRATION_OPEN,
    TournamentStatus.REGISTRATION_CLOSED,
)


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self, tournament_id: UUID, kind: ReminderKind, sent_at: datetime, recipient_count: int
    ) -> TournamentReminder:
        reminder = TournamentReminder(
            tournament_id=tournament_id,
            kind=kind,
            sent_at=sent_at,
            recipient_count=recipient_count,
        )
        self._session.add(reminder)
        await self._session.flush()
        await self._session.refresh(reminder)
        return reminder

    async def last_sent(self, tournament_id: UUID) -> TournamentReminder | None:
        """The most recent reminder of any kind, for "last sent two hours ago"."""
        result = await self._session.execute(
            select(TournamentReminder)
            .where(TournamentReminder.tournament_id == tournament_id)
            .order_by(TournamentReminder.sent_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def has_sent(self, tournament_id: UUID, kind: ReminderKind) -> bool:
        """Whether this kind has already gone out. What makes the sweep idempotent."""
        result = await self._session.execute(
            select(TournamentReminder.id).where(
                TournamentReminder.tournament_id == tournament_id,
                TournamentReminder.kind == kind,
            )
        )
        return result.first() is not None

    async def due_for_upcoming(self, until: datetime) -> Sequence[Tournament]:
        """Real tournaments starting before `until` that have had no UPCOMING mail.

        Three filters, each load-bearing:

        - `scheduled_at IS NOT NULL` — an event with no date cannot be "coming up".
          This is the column's first reader; it has been settable since M2 and
          nothing has ever looked at it.
        - the status range — see `REMINDABLE_STATES`.
        - `kind = TOURNAMENT` — a fun round is arranged in a group chat an hour
          beforehand. Mailing its four players about it would be a stranger use of
          their inbox than not.

        The already-sent check is a NOT EXISTS rather than a flag, so a sweep that
        crashes halfway through re-runs safely: events already mailed are excluded
        by what actually happened, not by a marker somebody has to remember to set.
        """
        already_sent = (
            select(TournamentReminder.tournament_id)
            .where(TournamentReminder.kind == ReminderKind.UPCOMING)
            .scalar_subquery()
        )
        result = await self._session.execute(
            select(Tournament)
            .where(
                Tournament.kind == TournamentKind.TOURNAMENT,
                Tournament.scheduled_at.is_not(None),
                Tournament.scheduled_at <= until,
                Tournament.status.in_(REMINDABLE_STATES),
                Tournament.id.not_in(already_sent),
            )
            .order_by(Tournament.scheduled_at)
        )
        return result.scalars().all()
