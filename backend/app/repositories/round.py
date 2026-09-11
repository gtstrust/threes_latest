from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.round import Group, GroupHole, GroupMember, Round, RoundStatus
from app.services.scoring import AdvancedBy


@dataclass(frozen=True)
class RoundProgress:
    """The last round a participant was drawn into, and whether they won it."""

    last_round: int
    advanced: bool


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

    async def latest_for_tournament(self, tournament_id: UUID) -> Round | None:
        """The highest-numbered round — under `DRAWABLE_FROM`, the one just finished."""
        result = await self._session.execute(
            select(Round)
            .where(Round.tournament_id == tournament_id)
            .order_by(Round.round_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def set_advancement(
        self, group: Group, participant_id: UUID | None, advanced_by: AdvancedBy | None
    ) -> Group:
        """Record who goes through from a group, and the level that named them."""
        group.advancing_participant_id = participant_id
        group.advanced_by = advanced_by
        await self._session.flush()
        await self._session.refresh(group)
        return group

    async def advancement_for_round(self, round_id: UUID) -> list[tuple[int, UUID | None]]:
        """`(group_number, advancing_participant_id)` per group, in group order.

        Pairs rather than just the ids, because one read has to answer both
        questions the next draw asks: who is still in, and — when a group has not
        said — which group numbers to name in its refusal.
        """
        result = await self._session.execute(
            select(Group.group_number, Group.advancing_participant_id)
            .where(Group.round_id == round_id)
            .order_by(Group.group_number)
        )
        return [(number, participant_id) for number, participant_id in result.all()]

    async def progress_for_tournament(self, tournament_id: UUID) -> dict[UUID, RoundProgress]:
        """How far every participant got, in one aggregate.

        Deliberately *not* `LeaderboardService._round_field` in a loop.
        `_round_field` answers "who is in this round" — a membership set, used to
        keep eliminated players off a round's board, and it stays as it is. This
        answers a different question across every round at once, and a per-round
        loop would be one query per round for a figure SQL can group in a single
        pass.

        A player only ever advances from a round they were in, so the highest
        round they won equals their last round exactly when they advanced from
        it. The `+1` that makes a champion outrank the field is a rule, not a
        read, and lives in the leaderboard service.
        """
        won = case(
            (Group.advancing_participant_id == GroupMember.participant_id, Round.round_number),
            else_=0,
        )
        result = await self._session.execute(
            select(
                GroupMember.participant_id,
                func.max(Round.round_number),
                func.max(won),
            )
            .join(Group, Group.id == GroupMember.group_id)
            .join(Round, Round.id == Group.round_id)
            .where(Round.tournament_id == tournament_id)
            .group_by(GroupMember.participant_id)
        )
        return {
            participant_id: RoundProgress(
                last_round=int(last_round), advanced=int(last_won) == int(last_round)
            )
            for participant_id, last_round, last_won in result.all()
        }

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
