from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player
from app.schemas.player import PlayerCreate, PlayerUpdate


class PlayerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, player_id: UUID) -> Player | None:
        return await self._session.get(Player, player_id)

    async def get_by_email(self, email: str) -> Player | None:
        result = await self._session.execute(select(Player).where(Player.email == email))
        return result.scalar_one_or_none()

    async def create(self, player_create: PlayerCreate) -> Player:
        player = Player(
            id=player_create.id,
            email=player_create.email,
            display_name=player_create.display_name,
        )
        self._session.add(player)
        await self._session.flush()
        await self._session.refresh(player)
        return player

    async def update(self, player: Player, updates: PlayerUpdate) -> Player:
        if updates.display_name is not None:
            player.display_name = updates.display_name
        await self._session.flush()
        await self._session.refresh(player)
        return player
