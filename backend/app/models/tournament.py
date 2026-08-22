from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TournamentStatus(str, Enum):
    """Lifecycle states from ADR-003. Transitions are enforced in the service layer.

    Values match the names so the wire format, the database enum, and the ADR all
    read identically.
    """

    CREATED = "CREATED"
    REGISTRATION_OPEN = "REGISTRATION_OPEN"
    REGISTRATION_CLOSED = "REGISTRATION_CLOSED"
    ROUND_IN_PROGRESS = "ROUND_IN_PROGRESS"
    ROUND_COMPLETE = "ROUND_COMPLETE"
    TOURNAMENT_COMPLETE = "TOURNAMENT_COMPLETE"


class TournamentFormat(str, Enum):
    """Formats the database column can hold — not the ones the API will accept.

    KNOCKOUT exists here so the column doesn't need migrating when bracket
    progression is eventually built, but nothing implements it today and the API
    rejects it. See SUPPORTED_FORMATS below.
    """

    ROUND_ROBIN = "ROUND_ROBIN"
    KNOCKOUT = "KNOCKOUT"


# Formats the API will actually accept. KNOCKOUT is deliberately absent: there is
# no seeding, elimination or advancement behind it, so a tournament created as a
# knockout would run exactly like a round robin and the organiser would only find
# out mid-event. Adding a format here is the single change needed to open it up.
SUPPORTED_FORMATS: frozenset[TournamentFormat] = frozenset({TournamentFormat.ROUND_ROBIN})


class Tournament(Base, TimestampMixin):
    """A structured competition owned by the organiser who created it."""

    __tablename__ = "tournaments"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)

    # No ondelete cascade: deleting a player who organised a tournament should
    # fail loudly rather than silently destroy the event and its scores.
    organiser_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("players.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[TournamentStatus] = mapped_column(
        SAEnum(TournamentStatus, name="tournament_status"),
        nullable=False,
        default=TournamentStatus.CREATED,
    )
    format: Mapped[TournamentFormat] = mapped_column(
        SAEnum(TournamentFormat, name="tournament_format"),
        nullable=False,
        default=TournamentFormat.ROUND_ROBIN,
    )

    course_name: Mapped[str | None] = mapped_column(String, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
