from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# Imported rather than restated. `AdvancedBy` is part of `decide_advancement`'s
# return contract, and a second copy here is how the database label drifts from
# the vocabulary ADR-012 uses — the same reasoning that brings `DecidedBy` into
# `models/score.py` and `LoopStyle` into `models/tournament.py`. `scoring.py`
# imports nothing from `app.*`, which is what keeps this from being a cycle.
from app.services.scoring import AdvancedBy


class RoundStatus(str, Enum):
    """A round's own lifecycle, distinct from the tournament's.

    A tournament runs several rounds, so its single status can only describe the
    current one. This is what says which of the earlier rounds are finished.
    """

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"


class Round(Base, TimestampMixin):
    """One stage of a tournament: a draw of groups, each playing its own loop."""

    __tablename__ = "rounds"
    __table_args__ = (
        UniqueConstraint("tournament_id", "round_number", name="uq_rounds_tournament_number"),
        CheckConstraint("round_number >= 1", name="ck_rounds_number_positive"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tournament_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RoundStatus] = mapped_column(
        SAEnum(RoundStatus, name="round_status"),
        nullable=False,
        default=RoundStatus.PENDING,
    )

    groups: Mapped[list["Group"]] = relationship(
        back_populates="round",
        cascade="all, delete-orphan",
        order_by="Group.group_number",
    )


class Group(Base, TimestampMixin):
    """2-3 players playing one 3-hole loop together. One group = one match."""

    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("round_id", "group_number", name="uq_groups_round_number"),
        CheckConstraint("group_number >= 1", name="ck_groups_number_positive"),
        # A level with no player, or a player with no level, is a half-written
        # verdict. ADR-009's argument for enforcing the format in the database
        # rather than only in the service: a wrong row here is a player told they
        # went through when they did not.
        CheckConstraint(
            "(advancing_participant_id IS NULL) = (advanced_by IS NULL)",
            name="ck_groups_advancement_pairs",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    round_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rounds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Who goes through, on a knockout, and which level of the ADR-012 cascade
    # named them. Both NULL on every round-robin group — forever, which is what
    # makes it provable that nothing about a round robin changed — and both NULL
    # on a knockout group the cascade could not settle, where the next draw
    # refuses until the organiser says.
    #
    # CASCADE matches `hole_results.winner_participant_id`: participants cascade
    # from the tournament, and a restricting FK here would block deleting one.
    advancing_participant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournament_participants.id", ondelete="CASCADE"),
        nullable=True,
    )
    advanced_by: Mapped[AdvancedBy | None] = mapped_column(
        SAEnum(
            AdvancedBy,
            name="advanced_by",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=True,
    )

    round: Mapped[Round] = relationship(back_populates="groups")
    members: Mapped[list["GroupMember"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    holes: Mapped[list["GroupHole"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="GroupHole.sequence",
    )


class GroupMember(Base, TimestampMixin):
    """A participant's place in a group."""

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "participant_id", name="uq_group_members_group_participant"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Cascade so deleting a tournament still works: participants cascade from the
    # tournament, and a restricting FK here would block that. It can't lose data
    # mid-event, because the field is already locked once a round exists.
    participant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournament_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    group: Mapped[Group] = relationship(back_populates="members")


class GroupHole(Base, TimestampMixin):
    """One hole of a group's loop.

    Holes hang off the group rather than the round because each group plays its
    own loop — a shotgun start, so the whole field tees off at once instead of
    queueing for the same three holes.
    """

    __tablename__ = "group_holes"
    __table_args__ = (
        UniqueConstraint("group_id", "hole_id", name="uq_group_holes_group_hole"),
        UniqueConstraint("group_id", "sequence", name="uq_group_holes_group_sequence"),
        CheckConstraint("sequence BETWEEN 1 AND 3", name="ck_group_holes_sequence_range"),
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
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    group: Mapped[Group] = relationship(back_populates="holes")
