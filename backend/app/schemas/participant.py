from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SelfRegister(BaseModel):
    """A player registering themselves. Everything is optional.

    `display_name` falls back to the player's profile name, then their email, so
    a caller can register with an empty body.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class VirtualPlayerCreate(BaseModel):
    """The organiser adding someone who has no account and no device."""

    display_name: str = Field(min_length=1, max_length=100)


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    player_id: UUID | None
    display_name: str
    is_virtual: bool
    created_at: datetime
    updated_at: datetime
