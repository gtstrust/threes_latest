from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.score import HoleResult, HoleScore
from app.services.scoring import DecidedBy


class ScoreRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
