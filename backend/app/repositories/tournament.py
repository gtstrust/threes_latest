from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tournament import Tournament, TournamentStatus
from app.schemas.tournament import TournamentCreate, TournamentUpdate


class TournamentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, tournament_id: UUID) -> Tournament | None:
        return await self._session.get(Tournament, tournament_id)

    async def list_for_organiser(self, organiser_id: UUID) -> Sequence[Tournament]:
        result = await self._session.execute(
            select(Tournament)
            .where(Tournament.organiser_id == organiser_id)
            .order_by(Tournament.created_at.desc())
        )
        return result.scalars().all()

    async def create(self, organiser_id: UUID, payload: TournamentCreate) -> Tournament:
        tournament = Tournament(
            organiser_id=organiser_id,
            name=payload.name,
            format=payload.format,
            course_name=payload.course_name,
            scheduled_at=payload.scheduled_at,
            status=TournamentStatus.CREATED,
        )
        self._session.add(tournament)
        await self._session.flush()
        await self._session.refresh(tournament)
        return tournament

    async def update(self, tournament: Tournament, updates: TournamentUpdate) -> Tournament:
        # exclude_unset so an omitted field is left alone, while an explicit null
        # can still clear course_name or scheduled_at.
        for field, value in updates.model_dump(exclude_unset=True).items():
            setattr(tournament, field, value)
        await self._session.flush()
        await self._session.refresh(tournament)
        return tournament

    async def set_status(self, tournament: Tournament, status: TournamentStatus) -> Tournament:
        tournament.status = status
        await self._session.flush()
        await self._session.refresh(tournament)
        return tournament
