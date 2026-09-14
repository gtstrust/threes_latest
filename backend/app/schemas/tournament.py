from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.tournament import (
    SUPPORTED_FORMATS,
    Tournament,
    TournamentFormat,
    TournamentStatus,
)
from app.services.grouping import MIN_GROUP_SIZE, TARGET_GROUP_SIZE, LoopStyle


# A cap below this describes an event nobody could play: the draw refuses to make
# a group of one (ADR-004), so a one-player field can never tee off.
MIN_MAX_PLAYERS = MIN_GROUP_SIZE

# The two targets an organiser may actually pick. `group_sizes` accepts anything
# from 2 to 4, because the arithmetic is well defined there; which of those the
# product *offers* is an edge decision and belongs here rather than in the pure
# core. A Literal rather than ge/le so both the OpenAPI schema and the 422 name
# the two real answers instead of describing a range.
GroupSize = Literal[3, 4]


class TournamentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    max_players: int | None = Field(
        default=None,
        ge=MIN_MAX_PLAYERS,
        description="Optional ceiling on the field, enforced when players register themselves.",
    )
    format: TournamentFormat = Field(
        default=TournamentFormat.ROUND_ROBIN,
        description="Only ROUND_ROBIN is accepted; KNOCKOUT is not implemented yet.",
    )
    group_size: GroupSize = Field(
        default=TARGET_GROUP_SIZE,
        description="Players per group: 3, the format, or 4 for fourballs (ADR-004).",
    )
    loop_style: LoopStyle = Field(
        default=LoopStyle.BLOCKS,
        description=(
            "BLOCKS cuts the holes into disjoint 3-hole loops; SHOTGUN makes every "
            "hole a starting tee, so the whole field tees off at once (ADR-011)."
        ),
    )
    course_id: UUID | None = None
    scheduled_at: datetime | None = None
    handicap_enabled: bool = Field(
        default=False,
        description=(
            "Deal each player shots from their playing handicap and decide holes "
            "on net strokes (ADR-013). Off unless asked for. With it on, every "
            "hole played needs a stroke index and every player needs a handicap, "
            "both checked when the round is drawn."
        ),
    )

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
    # An explicit null removes the cap, which `exclude_unset` in the repository
    # keeps distinguishable from not mentioning it at all.
    max_players: int | None = Field(default=None, ge=MIN_MAX_PLAYERS)
    # Unlike `max_players`, None here means "not mentioned" and never "clear it":
    # there is no such thing as an event with no group size or no start style.
    group_size: GroupSize | None = None
    loop_style: LoopStyle | None = None
    handicap_enabled: bool | None = None
    course_id: UUID | None = None
    scheduled_at: datetime | None = None

    @model_validator(mode="after")
    def _reject_cleared_draw_settings(self) -> "TournamentUpdate":
        """Refuse an explicit null for the two settings that have no empty value.

        `course_id` and `max_players` are genuinely clearable, so the repository
        writes whatever `exclude_unset` lets through. These three are not: the
        columns are NOT NULL, and an event with no group size, no start style or
        no answer on handicaps describes nothing. Without this the null reaches `setattr` and surfaces
        as an integrity error — a 500 for what is a malformed request.
        """
        cleared = [
            field
            for field in ("group_size", "loop_style", "handicap_enabled")
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if cleared:
            raise ValueError(
                f"{', '.join(cleared)} cannot be cleared — every event has a group "
                "size and a start style. Omit the field to leave it unchanged."
            )
        return self


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
    max_players: int | None
    group_size: int
    loop_style: LoopStyle
    handicap_enabled: bool
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
