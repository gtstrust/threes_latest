from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.participant import TournamentParticipant


class ParticipantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, participant_id: UUID) -> TournamentParticipant | None:
        return await self._session.get(TournamentParticipant, participant_id)

    async def list_for_tournament(self, tournament_id: UUID) -> Sequence[TournamentParticipant]:
        result = await self._session.execute(
            select(TournamentParticipant)
            .where(TournamentParticipant.tournament_id == tournament_id)
            .order_by(TournamentParticipant.created_at)
        )
        return result.scalars().all()

    async def get_for_player(
        self, tournament_id: UUID, player_id: UUID
    ) -> TournamentParticipant | None:
        result = await self._session.execute(
            select(TournamentParticipant).where(
                TournamentParticipant.tournament_id == tournament_id,
                TournamentParticipant.player_id == player_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self, tournament_id: UUID, display_name: str, player_id: UUID | None
    ) -> TournamentParticipant:
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            player_id=player_id,
            display_name=display_name.strip(),
        )
        self._session.add(participant)
        await self._session.flush()
        await self._session.refresh(participant)
        return participant

    async def delete(self, participant: TournamentParticipant) -> None:
        await self._session.delete(participant)
        await self._session.flush()

    async def count_for_tournament(self, tournament_id: UUID) -> int:
        participants = await self.list_for_tournament(tournament_id)
        return len(participants)
