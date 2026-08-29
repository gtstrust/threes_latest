"""Telling players about an event before it happens.

Two ways in, one path out. The organiser can send now, and a scheduler sweeps for
events coming up. Both compose the same message and both record what they did, so
"has this field been told?" has one answer rather than two.

**Who gets written to.** Only participants with a `player_id` and an email — a
Virtual Player has no account by definition, and the whole point of them is that
somebody else is carrying their card. Skipping them is the behaviour, not an edge
case, and the recorded recipient count is what makes that visible afterwards.

**Sending is awaited, not backgrounded** — unlike the realtime broadcast, and
worth saying why, because the resemblance is misleading. ADR-010 backgrounds the
broadcast to avoid a read-after-write race: a client told to refetch before the
transaction commits would read a board missing the hole that triggered it. No
such hazard exists here; nobody refetches because of an email, and the record of
having sent belongs in the same transaction as the response that claims it.

`BackgroundTasks` is also actively wrong for this. `get_db` closes the session
when its dependency finalises, which FastAPI runs *before* background tasks, so a
task holding that session has nothing to query with. The broadcast escapes this
only because it takes no session at all — see `get_realtime_notifier`.

The cost is that the organiser waits for the provider, which is why the messages
go out concurrently rather than one at a time: a field of twenty is one round
trip, not twenty.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player
from app.models.reminder import ReminderKind, TournamentReminder
from app.models.tournament import Tournament
from app.repositories.course import CourseRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.player import PlayerRepository
from app.repositories.reminder import ReminderRepository
from app.services.mail import Mailer, Message

logger = logging.getLogger(__name__)

# How far ahead the sweep looks. A day is the point at which a reminder is still
# actionable — someone can still arrange the morning off, or tell the organiser
# they can't make it while there is time to fill the place.
UPCOMING_WINDOW = timedelta(days=1)


class ReminderService:
    def __init__(self, session: AsyncSession, mailer: Mailer) -> None:
        self._session = session
        self._mailer = mailer
        self._reminders = ReminderRepository(session)
        self._participants = ParticipantRepository(session)
        self._players = PlayerRepository(session)
        self._courses = CourseRepository(session)

    async def last_sent(self, tournament_id: UUID) -> TournamentReminder | None:
        return await self._reminders.last_sent(tournament_id)

    async def send_now(self, tournament: Tournament, app_url: str) -> int:
        """Mail the field because the organiser asked. Returns how many went.

        Recorded as MANUAL, which is a different kind from the sweep's so that
        pressing the button neither satisfies nor cancels the day-before mail.
        """
        return await self._send(tournament, ReminderKind.MANUAL, app_url)

    async def sweep(self, app_url: str, now: datetime | None = None) -> list[UUID]:
        """Mail every event coming up that hasn't been told yet.

        Returns the ids handled, so the caller can log what a run actually did
        rather than that it ran.
        """
        moment = now or datetime.now(UTC)
        due = await self._reminders.due_for_upcoming(moment + UPCOMING_WINDOW)

        handled: list[UUID] = []
        for tournament in due:
            await self._send(tournament, ReminderKind.UPCOMING, app_url, now=moment)
            handled.append(tournament.id)
        return handled

    async def _send(
        self,
        tournament: Tournament,
        kind: ReminderKind,
        app_url: str,
        now: datetime | None = None,
    ) -> int:
        recipients = await self._recipients(tournament)
        message_for = await self._compose(tournament, app_url)

        # Concurrently, because the organiser is waiting: twenty players should
        # cost one round trip rather than twenty. `send` never raises, so there
        # is nothing here for one bad address to take down with it.
        results = await asyncio.gather(
            *(self._mailer.send(message_for(player)) for player in recipients)
        )
        sent = sum(1 for delivered in results if delivered)

        # Recorded even when nothing went. "Sent to nobody" and "not sent" look
        # identical from a flag, and only the first means the sweep is done here.
        await self._reminders.record(tournament.id, kind, now or datetime.now(UTC), sent)
        logger.info("Reminder (%s) for %s: %d sent", kind.value, tournament.id, sent)
        return sent

    async def _recipients(self, tournament: Tournament) -> list[Player]:
        """The field, minus everyone there is no way to write to."""
        field = await self._participants.list_for_tournament(tournament.id)
        players: list[Player] = []
        for participant in field:
            if participant.player_id is None:
                continue  # A Virtual Player. Somebody else is carrying their card.
            player = await self._players.get_by_id(participant.player_id)
            if player is not None and player.email:
                players.append(player)
        return players

    async def _compose(self, tournament: Tournament, app_url: str) -> Callable[[Player], Message]:
        """Build a per-player message factory, resolving the course once."""
        course = (
            await self._courses.get_by_id(tournament.course_id) if tournament.course_id else None
        )
        when = _readable_date(tournament.scheduled_at)
        where = course.name if course else None
        link = f"{app_url.rstrip('/')}/t/{tournament.id}"

        details = ", ".join(part for part in (when, where) if part)
        subject = f"{tournament.name} is coming up" if when else f"Reminder: {tournament.name}"

        def build(player: Player) -> Message:
            greeting = player.display_name or "Hello"
            lines = [
                f"{greeting},",
                "",
                f"You're playing in {tournament.name}"
                + (f" — {details}." if details else ".")
                + "",
                "",
                f"Your group, the holes you're playing and the live board are here: {link}",
                "",
                "See you out there.",
            ]
            text = "\n".join(lines)
            html = (
                f"<p>{_escape(greeting)},</p>"
                f"<p>You're playing in <strong>{_escape(tournament.name)}</strong>"
                + (f" — {_escape(details)}." if details else ".")
                + "</p>"
                f'<p><a href="{link}">Your group, the holes and the live board</a></p>'
                "<p>See you out there.</p>"
            )
            return Message(to=player.email, subject=subject, text=text, html=html)

        return build


def _readable_date(when: datetime | None) -> str | None:
    """`Saturday 5 September, 8:30am`, or None when no date was ever set.

    Formatted here rather than in the template so the two message bodies cannot
    disagree about what time the event is.
    """
    if when is None:
        return None
    hour = when.hour % 12 or 12
    meridiem = "am" if when.hour < 12 else "pm"
    minute = f":{when.minute:02d}" if when.minute else ""
    return f"{when:%A %-d %B}, {hour}{minute}{meridiem}"


def _escape(value: str) -> str:
    """Minimal HTML escaping for values that reach the markup body.

    A tournament name is organiser-supplied text landing in an email somebody
    else opens, which is exactly the shape of an injection. Names are the only
    interpolated value here and none of them need markup.
    """
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
