"""Standings — where the stored points from ADR-009 meet the ranking from ADR-007.

Almost nothing here is arithmetic. `rank_leaderboard` in `scoring` does the
ordering and `ScoreRepository` does the summing; what this module contributes is
knowing *who belongs on the board*, which neither of them can answer.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.participant import TournamentParticipant
from app.models.round import Round
from app.models.tournament import Tournament, TournamentFormat
from app.repositories.participant import ParticipantRepository
from app.repositories.round import RoundRepository
from app.repositories.score import ScoreRepository, ScoreTotals
from app.services.scoring import ParticipantTotals, rank_leaderboard


@dataclass(frozen=True)
class LeaderboardEntry:
    """One line of the board: a ranked participant, named."""

    position: int
    participant_id: UUID
    display_name: str
    points: int
    total_strokes: int
    holes_played: int
    #: How many rounds this player was alive for (ADR-012). **None on a round
    #: robin**, where nobody is knocked out and the figure would mean nothing —
    #: not 0, which would read as "went out immediately".
    rounds_survived: int | None = None


class LeaderboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._scores = ScoreRepository(session)
        self._participants = ParticipantRepository(session)
        self._rounds = RoundRepository(session)

    async def for_tournament(self, tournament: Tournament) -> list[LeaderboardEntry]:
        """Cumulative standings across every round played so far.

        A **knockout** is ranked by how far a player got first (ADR-012), then by
        the same points and strokes as ever. A champion can finish behind a
        beaten finalist on cumulative points — they played the same nine holes —
        and a board that put the finalist top would be reporting a different
        competition from the one that was run.
        """
        field = await self._participants.list_for_tournament(tournament.id)
        totals = await self._scores.totals_for_tournament(tournament.id)
        progress = (
            await self._survived(tournament.id)
            if tournament.format is TournamentFormat.KNOCKOUT
            else None
        )
        return _rank(field, totals, progress)

    async def _survived(self, tournament_id: UUID) -> dict[UUID, int]:
        """Rounds each player was still alive for.

        The last round they were drawn into, **plus one if they won it** — so the
        champion of a three-round bracket is on 4 and is alone at the top by
        construction, whatever the cumulative points say.
        """
        return {
            participant_id: progress.last_round + (1 if progress.advanced else 0)
            for participant_id, progress in (
                await self._rounds.progress_for_tournament(tournament_id)
            ).items()
        }

    async def for_round(self, round_: Round) -> list[LeaderboardEntry]:
        """Standings for a single round, over the players drawn into it.

        Today the draw always covers the whole field, so this matches
        `for_tournament`'s membership — but it is taken from the draw rather than
        assumed, because knockout progression (a stated long-term goal) would
        make a later round's field a subset, and reading the tournament's field
        instead would then quietly list eliminated players on nothing.

        Not taken from who has scored, either: a group yet to tee off still
        belongs on its round's board.
        """
        field = await self._participants.list_for_tournament(round_.tournament_id)
        drawn = await self._round_field(round_.id)
        totals = await self._scores.totals_for_round(round_.id)
        return _rank([player for player in field if player.id in drawn], totals)

    async def _round_field(self, round_id: UUID) -> set[UUID]:
        round_with_groups = await self._rounds.get_with_groups(round_id)
        if round_with_groups is None:
            return set()
        return {
            member.participant_id for group in round_with_groups.groups for member in group.members
        }


def _rank(
    field: Sequence[TournamentParticipant],
    totals: dict[UUID, ScoreTotals],
    progress: Mapping[UUID, int] | None = None,
) -> list[LeaderboardEntry]:
    """Zero-fill the field, rank it, and put the names back on.

    The aggregate only knows about participants who have scored a hole, which
    early in a day is almost nobody. A board missing half the field reads as a
    bug rather than as "they haven't finished a hole yet", so everyone drawn is
    listed, on nothing until they score.

    `field` arrives in registration order and is fed to `rank_leaderboard` in
    that order deliberately: its sort is stable, so players level on both points
    and strokes come out in input order. Ranking the aggregate's mapping order
    instead would leave genuinely-tied players shuffling between requests.
    """
    empty = ScoreTotals(points=0, strokes=0, holes_played=0)
    scored = {player.id: totals.get(player.id, empty) for player in field}
    names = {player.id: player.display_name for player in field}

    # `progress` is None for every board but a knockout's cumulative one. It then
    # feeds 0 into the sort key for everyone, which makes the leading term a
    # constant and the ordering exactly what it was before knockout existed.
    rows = rank_leaderboard(
        ParticipantTotals(
            participant_id=player.id,
            points=scored[player.id].points,
            total_strokes=scored[player.id].strokes,
            rounds_survived=progress.get(player.id, 0) if progress is not None else 0,
        )
        for player in field
    )

    return [
        LeaderboardEntry(
            position=row.position,
            participant_id=row.participant_id,
            display_name=names[row.participant_id],
            points=row.points,
            total_strokes=row.total_strokes,
            holes_played=scored[row.participant_id].holes_played,
            rounds_survived=row.rounds_survived if progress is not None else None,
        )
        for row in rows
    ]
