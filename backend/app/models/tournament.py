from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, String
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


class TournamentKind(str, Enum):
    """What a `tournaments` row actually is.

    A Fun Round is a casual, self-run round (Phase 2) that reuses the whole
    scoring/grouping/leaderboard machinery — so rather than a parallel set of
    tables, it *is* a tournament row carrying this discriminator. The value keeps
    the two apart wherever it matters: listings, and any tournament-only logic
    (organiser fees, sponsors) that must never apply to a casual round.
    """

    TOURNAMENT = "TOURNAMENT"
    FUN_ROUND = "FUN_ROUND"


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

    # The invitation, handed out as a link or a QR. Unique and short enough to
    # read aloud; regeneratable, which is the whole reason it isn't the id — an
    # id printed on a sign can never be withdrawn. On the shared table so a Fun
    # Round is invited exactly the same way.
    join_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)

    # What this row is: a full tournament (the default) or a casual Fun Round.
    # The engine treats both identically; the discriminator only separates them
    # in listings and in tournament-only concerns.
    kind: Mapped[TournamentKind] = mapped_column(
        SAEnum(TournamentKind, name="tournament_kind"),
        nullable=False,
        default=TournamentKind.TOURNAMENT,
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

    # Nullable so an event can be set up before the venue is booked, but a
    # tournament cannot reach ROUND_IN_PROGRESS without one — enforced in
    # RoundService.draw_round rather than in the state machine, because per
    # ADR-008 the draw is the only route to that status.
    course_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("courses.id"),
        nullable=True,
        index=True,
    )
    # The holes chosen at setup, and the draw's default selection. A fun round's
    # host picks their loop when they pick the course, which is earlier than the
    # draw that consumes it, so the answer has to outlive the request that made
    # it. NULL means nothing was chosen: the whole course. Tournaments leave it
    # NULL and pass their selection to `draw_round` instead.
    hole_numbers: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), nullable=True)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
