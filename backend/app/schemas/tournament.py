from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.tournament import TournamentFormat, TournamentStatus


class TournamentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    format: TournamentFormat = TournamentFormat.ROUND_ROBIN
    course_name: str | None = Field(default=None, max_length=200)
    scheduled_at: datetime | None = None


class TournamentUpdate(BaseModel):
    """Every field optional — only what's supplied is changed."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    course_name: str | None = Field(default=None, max_length=200)
    scheduled_at: datetime | None = None


class TournamentStatusUpdate(BaseModel):
    status: TournamentStatus


class TournamentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    organiser_id: UUID
    status: TournamentStatus
    format: TournamentFormat
    course_name: str | None
    scheduled_at: datetime | None
    created_at: datetime
    updated_at: datetime
