from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.course import MAX_HOLE_NUMBER, MIN_HOLE_NUMBER
from app.models.round import RoundStatus
from app.services.grouping import HOLES_PER_LOOP
from app.services.scoring import AdvancedBy


class RoundDraw(BaseModel):
    """Which holes to draw this round's loops from. Everything is optional.

    Omitted — including no body at all — means the whole course, which is what
    every caller did before this existed and remains the right answer for an
    event that owns the venue.

    Naming holes is for playing a competition inside a normal round: three mates
    on the 7th tee agreeing that 7, 8 and 9 are the match. The course record
    stays the real one; the holes played are recorded against the round.

    What a selection *means* depends on the event's `loop_style` (ADR-011): under
    BLOCKS it is cut into disjoint triples, under SHOTGUN every hole in it is a
    starting tee. Only the style-independent rules are enforced here — see
    `_validate_selection`.
    """

    hole_numbers: list[int] | None = Field(
        default=None,
        description="Holes to play, e.g. [7, 8, 9]. Omit to use the whole course.",
    )

    @field_validator("hole_numbers")
    @classmethod
    def _validate_selection(cls, holes: list[int] | None) -> list[int] | None:
        """Reject a selection that is malformed whatever the event's start style.

        Range, duplicates and "at least one loop's worth" are true under both
        styles, so they are checked here and answer 422.

        **The shape rule is not here**, and cannot be: it depends on
        `tournaments.loop_style`, which a request body cannot see. Blocks need
        whole triples; a shotgun needs only that three holes exist, because every
        one of them is somebody's starting tee — a shotgun over holes 1-10 is ten
        loops. `RoundService._check_selection` owns that, and answers 409.

        Note the asymmetry with the default: a course carrying eight holes gives
        two loops and leaves the eighth unused, because the course is just a
        record of what exists. A *selection* is a statement of intent, so
        silently dropping the caller's fourth hole would be a worse answer than
        refusing it.
        """
        if holes is None:
            return None

        out_of_range = sorted({n for n in holes if not MIN_HOLE_NUMBER <= n <= MAX_HOLE_NUMBER})
        if out_of_range:
            raise ValueError(
                f"Hole numbers must be between {MIN_HOLE_NUMBER} and "
                f"{MAX_HOLE_NUMBER}; got {out_of_range}"
            )

        duplicates = sorted({n for n in holes if holes.count(n) > 1})
        if duplicates:
            raise ValueError(f"Duplicate hole numbers in selection: {duplicates}")

        if len(holes) < HOLES_PER_LOOP:
            raise ValueError(
                f"A loop is {HOLES_PER_LOOP} holes, so a selection needs at least "
                f"{HOLES_PER_LOOP}; got {len(holes)}"
            )

        return holes


class GroupHoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hole_id: UUID
    sequence: int


class GroupMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    participant_id: UUID


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    round_id: UUID
    group_number: int
    members: list[GroupMemberRead]
    holes: list[GroupHoleRead]
    # Who goes through, on a knockout (ADR-012). Null on every round-robin group,
    # and on a knockout group the cascade could not settle — which is what the
    # organiser's screen offers to resolve.
    advancing_participant_id: UUID | None = None
    advanced_by: AdvancedBy | None = None


class GroupAdvancementWrite(BaseModel):
    """The organiser's answer when nothing separated a group (ADR-012)."""

    participant_id: UUID


class RoundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    round_number: int
    status: RoundStatus
    created_at: datetime
    updated_at: datetime


class RoundWithGroups(RoundRead):
    groups: list[GroupRead]
