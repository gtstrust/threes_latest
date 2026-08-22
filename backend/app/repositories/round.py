from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.round import Group, GroupHole, GroupMember, Round, RoundStatus


class RoundRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, round_id: UUID) -> Round | None:
        return await self._session.get(Round, round_id)

    async def get_with_groups(self, round_id: UUID) -> Round | None:
        result = await self._session.execute(
            select(Round)
            .where(Round.id == round_id)
            .options(
                selectinload(Round.groups).selectinload(Group.members),
                selectinload(Round.groups).selectinload(Group.holes),
            )
        )
        return result.scalar_one_or_none()

    async def get_group(self, group_id: UUID) -> Group | None:
        result = await self._session.execute(
            select(Group)
            .where(Group.id == group_id)
            .options(selectinload(Group.members), selectinload(Group.holes))
        )
        return result.scalar_one_or_none()

    async def list_for_tournament(self, tournament_id: UUID) -> Sequence[Round]:
        result = await self._session.execute(
            select(Round).where(Round.tournament_id == tournament_id).order_by(Round.round_number)
        )
        return result.scalars().all()

    async def next_round_number(self, tournament_id: UUID) -> int:
        result = await self._session.execute(
            select(func.max(Round.round_number)).where(Round.tournament_id == tournament_id)
        )
        return (result.scalar_one() or 0) + 1

    async def create_round_with_groups(
        self,
        tournament_id: UUID,
        round_number: int,
        draw: Sequence[tuple[Sequence[UUID], Sequence[UUID]]],
    ) -> Round:
        """Persist a round and its whole draw in one flush.

        `draw` is one entry per group, each a (participant_ids, hole_ids) pair
        with holes already in playing order.
        """
        round_ = Round(
            tournament_id=tournament_id,
            round_number=round_number,
            status=RoundStatus.IN_PROGRESS,
        )
        self._session.add(round_)
        await self._session.flush()

        for group_index, (participant_ids, hole_ids) in enumerate(draw, start=1):
            group = Group(round_id=round_.id, group_number=group_index)
            self._session.add(group)
            await self._session.flush()

            for participant_id in participant_ids:
                self._session.add(GroupMember(group_id=group.id, participant_id=participant_id))
            for sequence, hole_id in enumerate(hole_ids, start=1):
                self._session.add(GroupHole(group_id=group.id, hole_id=hole_id, sequence=sequence))

        await self._session.flush()
        loaded = await self.get_with_groups(round_.id)
        assert loaded is not None  # just written in this transaction
        return loaded

    async def set_status(self, round_: Round, status: RoundStatus) -> Round:
        round_.status = status
        await self._session.flush()
        await self._session.refresh(round_)
        return round_
