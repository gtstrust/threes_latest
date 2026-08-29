from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReminderKind(str, Enum):
    """Why a reminder went out.

    Two today, and the distinction is what makes the sweep idempotent: an
    organiser pressing the button does not stop the day-before reminder going,
    and the day-before reminder going does not stop them pressing the button.
    """

    # Sent by the scheduled sweep, once, for an event about to happen.
    UPCOMING = "UPCOMING"
    # Sent because the organiser asked, any number of times.
    MANUAL = "MANUAL"


class TournamentReminder(Base):
    """A record that a reminder was sent, and to how many.

    A table rather than a column on `tournaments`, for two reasons. The sweep has
    to know whether it has already handled an event, and "already sent" is a fact
    about one *kind* of reminder rather than about the event. And the organiser's
    screen wants to say "last sent two hours ago", which needs a time, not a flag.

    No `updated_at`: a send is an event that happened, not a row that changes.
    """

    __tablename__ = "tournament_reminders"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    tournament_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[ReminderKind] = mapped_column(
        SAEnum(ReminderKind, name="reminder_kind"), nullable=False
    )

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # How many messages the mailer accepted. Zero is a real answer — a field of
    # virtual players has nobody to write to — and is worth storing rather than
    # inferring, since it is the difference between "sent to nobody" and "not
    # sent", which look identical from a flag.
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
