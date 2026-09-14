from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SelfRegister(BaseModel):
    """A player registering themselves. Everything is optional.

    `display_name` falls back to the player's profile name, then their email, so
    a caller can register with an empty body.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    playing_handicap: int | None = Field(
        default=None,
        ge=0,
        le=54,
        description=(
            "Playing handicap for this event (ADR-013). Per event rather than per "
            "player, since it differs between them. Required before a handicap "
            "event can be drawn; ignored by a scratch one."
        ),
    )


class VirtualPlayerCreate(BaseModel):
    """The organiser adding someone who has no account and no device."""

    display_name: str = Field(min_length=1, max_length=100)
    playing_handicap: int | None = Field(
        default=None,
        ge=0,
        le=54,
        description=(
            "Playing handicap for this event (ADR-013). Per event rather than per "
            "player, since it differs between them. Required before a handicap "
            "event can be drawn; ignored by a scratch one."
        ),
    )


class ParticipantUpdate(BaseModel):
    """Change something about a player already in the field.

    Only the handicap today, and that is the reason this schema exists at all —
    there was no way to edit a participant before ADR-013 needed one. Everything
    else about a participant is either immutable (who they are) or a snapshot
    taken at registration (their name on the board).
    """

    playing_handicap: int | None = Field(default=None, ge=0, le=54)


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    player_id: UUID | None
    display_name: str
    is_virtual: bool
    playing_handicap: int | None
    created_at: datetime
    updated_at: datetime
