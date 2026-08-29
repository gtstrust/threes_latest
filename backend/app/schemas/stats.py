"""A player's own record, as the client reads it.

Derived figures — win rate, strokes per hole — are computed server-side and sent
as numbers rather than left for the client to divide. Two clients dividing the
same pair of integers differently is a small bug with a long life, and ADR-002's
reasoning about scores applies just as well to the arithmetic about them.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.tournament import TournamentKind, TournamentStatus
from app.services.stats import CareerTotals, CourseFigures, HistoryEntry, PlayerStats


class CareerRead(BaseModel):
    """The headline numbers.

    `holes_won` is `SUM(points)` — ADR-007 makes a hole worth 1 or 0 with no
    halves, so points and holes taken are the same count seen twice.
    """

    events_played: int
    holes_played: int
    holes_won: int
    total_strokes: int
    win_rate: float
    average_strokes: float

    @classmethod
    def from_totals(cls, totals: CareerTotals) -> "CareerRead":
        return cls(
            events_played=totals.events_played,
            holes_played=totals.holes_played,
            holes_won=totals.holes_won,
            total_strokes=totals.total_strokes,
            win_rate=round(totals.win_rate, 3),
            average_strokes=round(totals.average_strokes, 2),
        )


class HistoryEntryRead(BaseModel):
    """One event, and how it went."""

    tournament_id: UUID
    name: str
    kind: TournamentKind
    status: TournamentStatus
    played_at: datetime
    # Null until they have scored a hole — an event they are in but have not
    # played yet belongs in a history, without a placing it hasn't earned.
    position: int | None
    points: int
    total_strokes: int
    holes_played: int

    @classmethod
    def from_entry(cls, entry: HistoryEntry) -> "HistoryEntryRead":
        return cls(
            tournament_id=entry.tournament_id,
            name=entry.name,
            kind=entry.kind,
            status=entry.status,
            played_at=entry.played_at,
            position=entry.position,
            points=entry.points,
            total_strokes=entry.total_strokes,
            holes_played=entry.holes_played,
        )


class PlayerStatsRead(BaseModel):
    career: CareerRead
    history: list[HistoryEntryRead]

    @classmethod
    def from_stats(cls, stats: PlayerStats) -> "PlayerStatsRead":
        return cls(
            career=CareerRead.from_totals(stats.career),
            history=[HistoryEntryRead.from_entry(entry) for entry in stats.history],
        )


class HoleRecordRead(BaseModel):
    """One hole of one course, over every time this player has played it.

    `best_strokes` is the interesting number on a short course: over three holes
    an average moves slowly, but a personal best is a thing somebody remembers.
    """

    hole_number: int
    times_played: int
    holes_won: int
    best_strokes: int
    average_strokes: float


class CourseRecordRead(BaseModel):
    """A player's record at one course, and hole by hole within it."""

    course_id: UUID
    course_name: str
    rounds_played: int
    holes_played: int
    holes_won: int
    average_strokes: float
    holes: list[HoleRecordRead]

    @classmethod
    def from_figures(cls, figures: CourseFigures) -> "CourseRecordRead":
        return cls(
            course_id=figures.course_id,
            course_name=figures.course_name,
            rounds_played=figures.rounds_played,
            holes_played=figures.holes_played,
            holes_won=figures.holes_won,
            average_strokes=round(figures.average_strokes, 2),
            holes=[
                HoleRecordRead(
                    hole_number=hole.hole_number,
                    times_played=hole.times_played,
                    holes_won=hole.holes_won,
                    best_strokes=hole.best_strokes,
                    average_strokes=round(hole.average_strokes, 2),
                )
                for hole in figures.holes
            ],
        )
