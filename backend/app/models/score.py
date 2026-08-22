from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# The one place a model imports from the service layer, against the usual
# routes -> services -> repositories -> models direction. DecidedBy is part of
# score_hole's return contract (HoleResult.decided_by), so defining a second copy
# here is how the database labels quietly drift from what the engine actually
# returns. scoring.py imports nothing from app.*, which is what keeps this from
# becoming a cycle — do not add a models import there.
from app.services.scoring import DecidedBy

# SQLAlchemy stores a Python enum's *name* by default, which would put "STROKES"
# in the database while the API emits "strokes". DecidedBy is the first enum here
# whose values differ from its names, so spell out that the values are what's
# persisted — the database label then matches the wire format and ADR-007's
# vocabulary. The migration creates the type with these same lowercase labels.
decided_by_enum = SAEnum(
    DecidedBy,
    name="decided_by",
    values_callable=lambda enum: [member.value for member in enum],
)


class HoleScore(Base, TimestampMixin):
    """One participant's strokes on one hole, and the points they earned for it.

    Points are stored rather than derived so the leaderboard is a plain SUM. They
    are always 0 or 1 — ADR-007 admits no half-points — and are written by the
    server from `score_hole`, never accepted from the client (ADR-002).
    """

    __tablename__ = "hole_scores"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "hole_id", "participant_id", name="uq_hole_scores_group_hole_participant"
        ),
        CheckConstraint("strokes >= 1", name="ck_hole_scores_strokes_positive"),
        CheckConstraint("points IN (0, 1)", name="ck_hole_scores_points_range"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hole_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("holes.id"), nullable=False, index=True
    )
    # Cascade for the same reason as group_members: participants cascade from the
    # tournament, and a restricting FK here would block deleting one.
    participant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournament_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strokes: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class HoleResult(Base, TimestampMixin):
    """What the ADR-007 cascade decided for one group on one hole.

    Separate from HoleScore because the two answer different questions: the scores
    are what the players reported, this is what the engine made of them. A
    correction rewrites the scores and recomputes this row.

    `winner_participant_id` is NULL when nobody won the hole — holes are never
    halved, so the alternative to one winner is no winner, not a shared one.

    The two tie-break columns hold *who that level named*, and are populated only
    when that level actually decided the hole (ADR-007: nothing is recorded unless
    it decided something). A flag supplied for a hole that had no tie is discarded.
    """

    __tablename__ = "hole_results"
    __table_args__ = (
        UniqueConstraint("group_id", "hole_id", name="uq_hole_results_group_hole"),
        CheckConstraint(
            "closest_to_pin_participant_id IS NULL OR decided_by = 'closest_to_pin'",
            name="ck_hole_results_ctp_decided",
        ),
        CheckConstraint(
            "longest_drive_participant_id IS NULL OR decided_by = 'longest_drive'",
            name="ck_hole_results_longest_drive_decided",
        ),
        CheckConstraint(
            "(winner_participant_id IS NULL) = (decided_by = 'no_winner')",
            name="ck_hole_results_winner_matches_decided_by",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hole_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("holes.id"), nullable=False, index=True
    )
    winner_participant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournament_participants.id", ondelete="CASCADE"),
        nullable=True,
    )
    decided_by: Mapped[DecidedBy] = mapped_column(decided_by_enum, nullable=False)
    closest_to_pin_participant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournament_participants.id", ondelete="CASCADE"),
        nullable=True,
    )
    longest_drive_participant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournament_participants.id", ondelete="CASCADE"),
        nullable=True,
    )
