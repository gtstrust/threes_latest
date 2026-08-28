from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.course import MAX_HOLE_NUMBER, MAX_PAR, MIN_HOLE_NUMBER, MIN_PAR


class HoleUpsert(BaseModel):
    """One hole in a bulk upsert. Only `hole_number` is required."""

    hole_number: int = Field(ge=MIN_HOLE_NUMBER, le=MAX_HOLE_NUMBER)
    par: int | None = Field(default=None, ge=MIN_PAR, le=MAX_PAR)
    stroke_index: int | None = Field(default=None, ge=MIN_HOLE_NUMBER, le=MAX_HOLE_NUMBER)


class HolesUpsert(BaseModel):
    """The full set of holes being written for a course."""

    holes: list[HoleUpsert] = Field(min_length=1)

    @field_validator("holes")
    @classmethod
    def _reject_duplicate_hole_numbers(cls, holes: list[HoleUpsert]) -> list[HoleUpsert]:
        """Catch duplicates here rather than letting the unique constraint 500.

        The payload is a set of holes, so the same number appearing twice is
        ambiguous about which one wins.
        """
        numbers = [hole.hole_number for hole in holes]
        duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
        if duplicates:
            raise ValueError(f"Duplicate hole numbers in payload: {duplicates}")
        return holes


class HoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    hole_number: int
    par: int | None
    stroke_index: int | None


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    location: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class CourseSummary(CourseRead):
    """A course as it appears in a list, with enough to tell if it can be played.

    Separate from `CourseRead` rather than a field on it: the count is a scan of
    another table, worth paying for on the list a course is chosen from and not on
    the three routes that return a single course they already hold.
    """

    hole_count: int


class CourseWithHoles(CourseRead):
    holes: list[HoleRead]
