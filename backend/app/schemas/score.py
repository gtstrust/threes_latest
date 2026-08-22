from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.scoring import DecidedBy


class HoleScoreSubmit(BaseModel):
    """Strokes for every player in a group on one hole, plus any tie-break answer.

    The tie-break fields are left unset on a first submission — ADR-007 only asks
    the question once a tie appears, and then only of the tied players. Submitting
    the same hole again with one of them filled in is how the answer arrives.
    """

    strokes: dict[UUID, int] = Field(min_length=1)
    closest_to_pin: UUID | None = None
    longest_drive: UUID | None = None


class HoleScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    participant_id: UUID
    strokes: int
    points: int


class HoleResultRead(BaseModel):
    """One hole's outcome, with the strokes it was decided from."""

    model_config = ConfigDict(from_attributes=True)

    hole_id: UUID
    winner_participant_id: UUID | None
    decided_by: DecidedBy
    closest_to_pin_participant_id: UUID | None
    longest_drive_participant_id: UUID | None
    scores: list[HoleScoreRead]
    # Who the group still has to separate. Empty unless the hole came down to a
    # tie the submitted answers could not break — the client uses this to know
    # which players to ask about closest to the pin, then longest drive.
    tied_participants: list[UUID] = []
    created_at: datetime
    updated_at: datetime


class GroupCardRead(BaseModel):
    """A group's card: one entry per hole of its loop that has been played."""

    group_id: UUID
    holes: list[HoleResultRead]
