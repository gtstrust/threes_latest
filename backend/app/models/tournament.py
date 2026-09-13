from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# Imported rather than restated. `LoopStyle` is part of the draw's contract in
# `services/grouping.py`, and a second copy here is how the database label and
# the vocabulary ADR-011 uses quietly drift apart — the same reasoning that
# brings `DecidedBy` into `models/score.py`. `grouping.py` imports nothing from
# `app.*`, so this is not a cycle.
from app.services.grouping import MAX_GROUP_SIZE, TARGET_GROUP_SIZE, LoopStyle


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
    """How a tournament's rounds relate to each other.

    ROUND_ROBIN redraws the whole field every round and the leaderboard adds up.
    KNOCKOUT makes each group a match: one player goes through and the rest are
    out, so the field shrinks every round (ADR-012).
    """

    ROUND_ROBIN = "ROUND_ROBIN"
    KNOCKOUT = "KNOCKOUT"


# Formats the API will actually accept — every one of them, now that knockout has
# advancement behind it. The constant stays rather than being inlined: it is the
# mechanism by which a *future* format can sit in the column, and be storable and
# readable, before anything implements it. That is what it did for KNOCKOUT from
# migration 0001 until ADR-012, and it is why adding one was a one-line change.
SUPPORTED_FORMATS: frozenset[TournamentFormat] = frozenset(TournamentFormat)


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

    # An optional ceiling on the field, enforced when a player registers
    # themselves (ParticipantService.self_register). NULL means no cap — a cap is
    # something an organiser opts into once tee times or catering make the number
    # real, not a limit the platform invents for them.
    max_players: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # How this event's draw is shaped (ADR-004, ADR-011). Both live on the
    # tournament rather than on each draw because rounds two and three have to
    # come out the same shape as round one without the organiser restating
    # anything — a per-draw-only setting puts a round of threes inside a fourball
    # event one missed keystroke away. `hole_numbers` stays per-draw by contrast,
    # because the holes genuinely do vary round to round.
    #
    # Neither is nullable, unlike `max_players`: a stored default and an absent
    # one behave identically, so there is no meaningful "unset". The server
    # defaults are what let existing rows and the ORM insert without naming them.
    group_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=TARGET_GROUP_SIZE,
        server_default=text(str(TARGET_GROUP_SIZE)),
    )
    loop_style: Mapped[LoopStyle] = mapped_column(
        SAEnum(LoopStyle, name="loop_style"),
        nullable=False,
        default=LoopStyle.BLOCKS,
        server_default=LoopStyle.BLOCKS.value,
    )

    # The per-event opt-in for handicaps (ADR-013). Same shape as the two above,
    # and false unless somebody says otherwise — a scratch event is bit for bit
    # the event it was before handicaps existed. A fun round inherits this column
    # by being a `tournaments` row, but `FunRoundService.create` narrows its
    # payload by hand, so the flag has to be plumbed there explicitly.
    handicap_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # The format's floor and ceiling, enforced by the database and not only by the
    # schema: a group of five has nobody to play the ADR-007 cascade against, and
    # a wrong row is worse than a rejected write.
    __table_args__ = (
        CheckConstraint(
            f"group_size BETWEEN {TARGET_GROUP_SIZE} AND {MAX_GROUP_SIZE}",
            name="ck_tournaments_group_size",
        ),
    )
