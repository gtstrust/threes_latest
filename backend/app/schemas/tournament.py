from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.tournament import (
    SUPPORTED_FORMATS,
    Tournament,
    TournamentFormat,
    TournamentStatus,
)


class TournamentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    format: TournamentFormat = Field(
        default=TournamentFormat.ROUND_ROBIN,
        description="Only ROUND_ROBIN is accepted; KNOCKOUT is not implemented yet.",
    )
    course_id: UUID | None = None
    scheduled_at: datetime | None = None

    @field_validator("format")
    @classmethod
    def _reject_unimplemented_format(cls, value: TournamentFormat) -> TournamentFormat:
        """Refuse formats the platform can't actually run.

        Accepting KNOCKOUT would fail silently — the event would run as a round
        robin and the organiser would only discover nobody is being eliminated
        partway through the day.
        """
        if value not in SUPPORTED_FORMATS:
            supported = ", ".join(sorted(fmt.value for fmt in SUPPORTED_FORMATS))
            raise ValueError(
                f"{value.value} is not implemented yet. Supported formats: {supported}"
            )
        return value


class TournamentUpdate(BaseModel):
    """Every field optional — only what's supplied is changed."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    course_id: UUID | None = None
    scheduled_at: datetime | None = None


class TournamentStatusUpdate(BaseModel):
    status: TournamentStatus


class TournamentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    organiser_id: UUID
    # The invitation, and **null for anyone but the organiser** — see `for_viewer`.
    join_code: str | None = None
    status: TournamentStatus
    format: TournamentFormat
    course_id: UUID | None
    scheduled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def for_viewer(cls, tournament: Tournament, viewer_id: UUID) -> "TournamentRead":
        """The tournament as this caller may see it.

        The field can already read a tournament, so returning the join code to
        everyone would let any player invite people the organiser never chose.
        Handing out the invitation is the organiser's job; regenerating is the
        recovery if it spreads anyway.
        """
        read = cls.model_validate(tournament)
        if tournament.organiser_id != viewer_id:
            read.join_code = None
        return read
