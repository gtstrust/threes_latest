"""A player's own record — what they have played, and how it has gone.

Two questions, answered differently. The career figures are a single aggregate
over every hole the player has ever scored (`ScoreRepository.career_totals_for_player`).
The history is one row per event, and each row's finishing position comes from
**`LeaderboardService.for_tournament`** rather than from SQL.

That choice is the whole design decision here, and it costs a query per event.
Ranking in SQL — `RANK() OVER (PARTITION BY … ORDER BY points DESC, strokes ASC)` —
would be one query for the lot, but it would also be a second copy of
`rank_leaderboard`'s tie-break rule, living in a place no Python test reaches and
free to drift from the version that decides the board people actually play for.
ADR-010 rejects restating `require_can_view` in SQL for exactly this reason, and a
position is worth no less care than a permission: a player told they came third
here and second on the leaderboard has been lied to by one of them.

The count is bounded by `HISTORY_LIMIT` instead, which keeps the cost flat at any
scale a player's real history reaches.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tournament import Tournament, TournamentKind, TournamentStatus
from app.repositories.participant import ParticipantRepository
from app.repositories.score import ScoreRepository
from app.repositories.tournament import TournamentRepository
from app.services.leaderboard import LeaderboardService

# Enough that nobody reaches the end of their own history, small enough that the
# per-event ranking query stays a rounding error. Revisit if a player ever has
# more events than this — which would be a good problem.
HISTORY_LIMIT = 20


@dataclass(frozen=True)
class CareerTotals:
    """The headline numbers, over every hole this player has ever scored."""

    events_played: int
    holes_played: int
    holes_won: int
    total_strokes: int

    @property
    def win_rate(self) -> float:
        """Share of holes taken, 0-1. Zero holes is 0, not a division by zero."""
        return self.holes_won / self.holes_played if self.holes_played else 0.0

    @property
    def average_strokes(self) -> float:
        """Strokes per hole. The one number that moves as someone improves."""
        return self.total_strokes / self.holes_played if self.holes_played else 0.0


@dataclass(frozen=True)
class HistoryEntry:
    """One event this player took part in, and how they finished."""

    tournament_id: UUID
    name: str
    kind: TournamentKind
    status: TournamentStatus
    played_at: datetime
    # None until they have scored a hole: a drawn-but-unplayed event is listed,
    # because "I am in this" is part of a history, but it has no position yet.
    position: int | None
    points: int
    total_strokes: int
    holes_played: int


@dataclass(frozen=True)
class PlayerStats:
    career: CareerTotals
    history: list[HistoryEntry]


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._scores = ScoreRepository(session)
        self._tournaments = TournamentRepository(session)
        self._participants = ParticipantRepository(session)
        self._leaderboard = LeaderboardService(session)

    async def for_player(self, player_id: UUID) -> PlayerStats:
        """This player's career figures and recent events, newest first."""
        events = await self._played_events(player_id)
        recent = events[:HISTORY_LIMIT]

        totals = await self._scores.career_totals_for_player(player_id)
        career = CareerTotals(
            # Every event they entered, not just the ones in the history window —
            # a career count that shrank because a list was truncated would be
            # a lie about the same page's other number.
            events_played=len(events),
            holes_played=totals.holes_played,
            holes_won=totals.points,
            total_strokes=totals.strokes,
        )

        history = [await self._history_entry(event, player_id) for event in recent]
        return PlayerStats(career=career, history=history)

    async def _played_events(self, player_id: UUID) -> Sequence[Tournament]:
        """Everything this player is in, both kinds, newest first.

        Fun rounds count. They are the same table and the same scoring, and a
        player's record of what they have played is not improved by hiding half
        of it because one half was casual.
        """
        return await self._tournaments.list_all_for_player(player_id)

    async def _history_entry(self, event: Tournament, player_id: UUID) -> HistoryEntry:
        participant = await self._participants.get_for_player(event.id, player_id)
        board = await self._leaderboard.for_tournament(event)
        mine = next(
            (entry for entry in board if participant and entry.participant_id == participant.id),
            None,
        )

        return HistoryEntry(
            tournament_id=event.id,
            name=event.name,
            kind=event.kind,
            status=event.status,
            played_at=event.scheduled_at or event.created_at,
            # A board lists the whole field, including players on nothing, so a
            # position exists as soon as the event does. It is only meaningful
            # once they have actually scored — hence the holes_played gate.
            position=mine.position if mine and mine.holes_played else None,
            points=mine.points if mine else 0,
            total_strokes=mine.total_strokes if mine else 0,
            holes_played=mine.holes_played if mine else 0,
        )
