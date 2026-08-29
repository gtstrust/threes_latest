from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course, Hole
from app.models.participant import TournamentParticipant
from app.models.round import Group, Round
from app.models.score import HoleResult, HoleScore
from app.services.scoring import DecidedBy


@dataclass(frozen=True)
class HoleRecord:
    """One player's record on one hole of one course, over every time they played it."""

    course_id: UUID
    hole_number: int
    times_played: int
    holes_won: int
    best_strokes: int
    total_strokes: int


@dataclass(frozen=True)
class CourseRounds:
    """How many distinct rounds a player has played at a course, and its name."""

    course_id: UUID
    course_name: str
    rounds_played: int


@dataclass(frozen=True)
class ScoreTotals:
    """What one participant has accumulated over some set of holes."""

    points: int
    strokes: int
    holes_played: int


def _totals_query() -> Select[tuple[UUID, int, int, int]]:
    """SUM(points), SUM(strokes) and a hole count, per participant.

    ADR-009 stores points on the score row precisely so this is a plain
    aggregate rather than a walk over per-hole verdicts. `hole_scores` carries
    no tournament_id, so both callers reach one through `groups`.
    """
    return select(
        HoleScore.participant_id,
        func.sum(HoleScore.points),
        func.sum(HoleScore.strokes),
        func.count(HoleScore.id),
    ).group_by(HoleScore.participant_id)


class ScoreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _totals(self, query: Select[tuple[UUID, int, int, int]]) -> dict[UUID, ScoreTotals]:
        result = await self._session.execute(query)
        # SUM() comes back as Decimal; coerce here so nothing downstream has to.
        return {
            participant_id: ScoreTotals(
                points=int(points), strokes=int(strokes), holes_played=int(holes)
            )
            for participant_id, points, strokes, holes in result.all()
        }

    async def totals_for_tournament(self, tournament_id: UUID) -> dict[UUID, ScoreTotals]:
        """Every participant who has scored a hole anywhere in this tournament.

        Participants yet to score are absent rather than zero — filling the rest
        of the field in is the leaderboard service's job, since only it knows
        who the field is.
        """
        return await self._totals(
            _totals_query()
            .join(Group, Group.id == HoleScore.group_id)
            .join(Round, Round.id == Group.round_id)
            .where(Round.tournament_id == tournament_id)
        )

    async def career_totals_for_player(self, player_id: UUID) -> ScoreTotals:
        """Everything one player has ever scored, across every event.

        Keyed on the *player*, not a participant, so it reaches through
        `tournament_participants` — the indirection that exists so a Virtual
        Player can be scored like anyone else. A virtual player has no
        `player_id`, so they never appear here, which is correct: nobody owns
        those holes.

        **`SUM(points)` is holes won.** ADR-007 makes a hole worth 1 or 0 with no
        halves, so the same stored points that feed the leaderboard also answer
        "how many holes has this player taken" without a second pass.
        """
        result = await self._session.execute(
            select(
                func.coalesce(func.sum(HoleScore.points), 0),
                func.coalesce(func.sum(HoleScore.strokes), 0),
                func.count(HoleScore.id),
            )
            .join(
                TournamentParticipant,
                TournamentParticipant.id == HoleScore.participant_id,
            )
            .where(TournamentParticipant.player_id == player_id)
        )
        points, strokes, holes = result.one()
        return ScoreTotals(points=int(points), strokes=int(strokes), holes_played=int(holes))

    async def hole_records_for_player(self, player_id: UUID) -> list[HoleRecord]:
        """Per-hole aggregates across every course this player has played.

        One row per (course, hole number) rather than per hole *id*, because the
        question is "how do I play the 3rd at Royal Melbourne", and a course that
        had its holes re-entered would otherwise split one hole into two records.

        Grouped on the hole number for the same reason `career_totals_for_player`
        joins through `tournament_participants`: the identity that matters here is
        the player's, and a Virtual Player has no `player_id` to match.
        """
        result = await self._session.execute(
            select(
                Hole.course_id,
                Hole.hole_number,
                func.count(HoleScore.id),
                func.sum(HoleScore.points),
                func.min(HoleScore.strokes),
                func.sum(HoleScore.strokes),
            )
            .join(Hole, Hole.id == HoleScore.hole_id)
            .join(
                TournamentParticipant,
                TournamentParticipant.id == HoleScore.participant_id,
            )
            .where(TournamentParticipant.player_id == player_id)
            .group_by(Hole.course_id, Hole.hole_number)
            .order_by(Hole.course_id, Hole.hole_number)
        )
        return [
            HoleRecord(
                course_id=course_id,
                hole_number=hole_number,
                times_played=int(played),
                holes_won=int(won),
                best_strokes=int(best),
                total_strokes=int(total),
            )
            for course_id, hole_number, played, won, best, total in result.all()
        ]

    async def course_rounds_for_player(self, player_id: UUID) -> list[CourseRounds]:
        """How many distinct rounds this player has played at each course.

        A separate query from the per-hole one because "rounds" is a count of
        something two joins further out (`groups` → `rounds`), and folding it into
        an aggregate already grouped by hole would multiply the count by the
        number of holes played. Two clean queries beat one clever one.
        """
        result = await self._session.execute(
            select(
                Course.id,
                Course.name,
                func.count(func.distinct(Group.round_id)),
            )
            .join(Hole, Hole.id == HoleScore.hole_id)
            .join(Course, Course.id == Hole.course_id)
            .join(Group, Group.id == HoleScore.group_id)
            .join(
                TournamentParticipant,
                TournamentParticipant.id == HoleScore.participant_id,
            )
            .where(TournamentParticipant.player_id == player_id)
            .group_by(Course.id, Course.name)
            .order_by(Course.name)
        )
        return [
            CourseRounds(course_id=course_id, course_name=name, rounds_played=int(rounds))
            for course_id, name, rounds in result.all()
        ]

    async def totals_for_round(self, round_id: UUID) -> dict[UUID, ScoreTotals]:
        """The same, narrowed to one round — one join rather than two."""
        return await self._totals(
            _totals_query()
            .join(Group, Group.id == HoleScore.group_id)
            .where(Group.round_id == round_id)
        )

    async def list_scores_for_hole(self, group_id: UUID, hole_id: UUID) -> Sequence[HoleScore]:
        result = await self._session.execute(
            select(HoleScore).where(HoleScore.group_id == group_id, HoleScore.hole_id == hole_id)
        )
        return result.scalars().all()

    async def get_result(self, group_id: UUID, hole_id: UUID) -> HoleResult | None:
        result = await self._session.execute(
            select(HoleResult).where(HoleResult.group_id == group_id, HoleResult.hole_id == hole_id)
        )
        return result.scalar_one_or_none()

    async def list_results_for_group(self, group_id: UUID) -> Sequence[HoleResult]:
        result = await self._session.execute(
            select(HoleResult).where(HoleResult.group_id == group_id)
        )
        return result.scalars().all()

    async def list_scores_for_group(self, group_id: UUID) -> Sequence[HoleScore]:
        result = await self._session.execute(
            select(HoleScore).where(HoleScore.group_id == group_id)
        )
        return result.scalars().all()

    async def upsert_hole(
        self,
        *,
        group_id: UUID,
        hole_id: UUID,
        strokes: Mapping[UUID, int],
        points: Mapping[UUID, int],
        winner_participant_id: UUID | None,
        decided_by: DecidedBy,
        closest_to_pin: UUID | None,
        longest_drive: UUID | None,
    ) -> HoleResult:
        """Write (or rewrite) one hole's scores and its decided result.

        Re-submitting a hole is ordinary — a mis-keyed number, or the tie-break
        answer arriving after the strokes — so existing rows are updated in place
        rather than rejected as duplicates.
        """
        existing = {
            score.participant_id: score
            for score in await self.list_scores_for_hole(group_id, hole_id)
        }

        for participant_id, stroke_count in strokes.items():
            score = existing.get(participant_id)
            if score is None:
                self._session.add(
                    HoleScore(
                        group_id=group_id,
                        hole_id=hole_id,
                        participant_id=participant_id,
                        strokes=stroke_count,
                        points=points[participant_id],
                    )
                )
            else:
                score.strokes = stroke_count
                score.points = points[participant_id]

        # A player dropped from a re-submission would otherwise keep the points
        # from the earlier one.
        for participant_id, score in existing.items():
            if participant_id not in strokes:
                await self._session.delete(score)

        result = await self.get_result(group_id, hole_id)
        if result is None:
            result = HoleResult(group_id=group_id, hole_id=hole_id, decided_by=decided_by)
            self._session.add(result)
        result.winner_participant_id = winner_participant_id
        result.decided_by = decided_by
        result.closest_to_pin_participant_id = closest_to_pin
        result.longest_drive_participant_id = longest_drive

        await self._session.flush()
        await self._session.refresh(result)
        return result
