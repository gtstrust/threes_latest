from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.participant import TournamentParticipant
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

    async def list_for_player(self, player_id: UUID) -> Sequence[Tournament]:
        """Tournaments this player is in the field of, newest first.

        A join rather than a second column: the field is the participants table,
        and a tournament reached this way is one the caller may view even though
        somebody else organises it.

        Virtual players cannot match. Their `player_id` is NULL, and NULL never
        equals anything — which is the same property that lets any number of them
        share a tournament under `uq_participants_tournament_player`.
        """
        result = await self._session.execute(
            select(Tournament)
            .join(TournamentParticipant, TournamentParticipant.tournament_id == Tournament.id)
            .where(TournamentParticipant.player_id == player_id)
            .order_by(Tournament.created_at.desc())
        )
        return result.scalars().all()

    async def create(self, organiser_id: UUID, payload: TournamentCreate) -> Tournament:
        tournament = Tournament(
            organiser_id=organiser_id,
            name=payload.name,
            format=payload.format,
            course_id=payload.course_id,
            scheduled_at=payload.scheduled_at,
            status=TournamentStatus.CREATED,
        )
        self._session.add(tournament)
        await self._session.flush()
        await self._session.refresh(tournament)
        return tournament

    async def update(self, tournament: Tournament, updates: TournamentUpdate) -> Tournament:
        # exclude_unset so an omitted field is left alone, while an explicit null
        # can still clear course_id or scheduled_at.
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
