from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

MIN_HOLE_NUMBER = 1
MAX_HOLE_NUMBER = 18
MIN_PAR = 3
MAX_PAR = 6


class Course(Base, TimestampMixin):
    """A golf course. Shared reference data, not owned by a single tournament.

    Deliberately global: two organisers running events at the same club should
    end up pointing at one record rather than each typing the name their own way.
    Anyone authenticated can read a course; only its creator can edit it.
    """

    __tablename__ = "courses"
    __table_args__ = (
        # Case-insensitive, so "Royal Melbourne" and "royal melbourne" collide
        # instead of quietly becoming two courses.
        Index("uq_courses_name_lower", text("lower(name)"), unique=True),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)

    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True
    )

    holes: Mapped[list["Hole"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Hole.hole_number",
    )


class Hole(Base, TimestampMixin):
    """One hole of a course.

    `par` and `stroke_index` are nullable on purpose. Scoring never uses par —
    ADR-007 is decided on strokes alone — so an organiser can enter three hole
    numbers and start playing. `stroke_index` is here ready for Phase 2 handicaps
    rather than needing a migration then.
    """

    __tablename__ = "holes"
    __table_args__ = (
        UniqueConstraint("course_id", "hole_number", name="uq_holes_course_hole_number"),
        CheckConstraint(
            f"hole_number BETWEEN {MIN_HOLE_NUMBER} AND {MAX_HOLE_NUMBER}",
            name="ck_holes_hole_number_range",
        ),
        CheckConstraint(
            f"par IS NULL OR par BETWEEN {MIN_PAR} AND {MAX_PAR}",
            name="ck_holes_par_range",
        ),
        CheckConstraint(
            f"stroke_index IS NULL OR stroke_index BETWEEN {MIN_HOLE_NUMBER} "
            f"AND {MAX_HOLE_NUMBER}",
            name="ck_holes_stroke_index_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    course_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hole_number: Mapped[int] = mapped_column(Integer, nullable=False)
    par: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stroke_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    course: Mapped[Course] = relationship(back_populates="holes")
