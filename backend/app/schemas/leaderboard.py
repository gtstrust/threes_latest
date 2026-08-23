from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LeaderboardEntryRead(BaseModel):
    """One ranked participant.

    `position` repeats for players who are genuinely level and the next position
    skips (1, 2, 2, 4), as is conventional in golf — see ADR-007. `holes_played`
    counts holes actually scored, not the three in the loop, so a group still out
    on the course is visible as such.
    """

    model_config = ConfigDict(from_attributes=True)

    position: int
    participant_id: UUID
    display_name: str
    points: int
    total_strokes: int
    holes_played: int


class LeaderboardRead(BaseModel):
    """A board. `round_id` is null on the cumulative tournament standings."""

    tournament_id: UUID
    round_id: UUID | None
    entries: list[LeaderboardEntryRead]
