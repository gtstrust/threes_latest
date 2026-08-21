from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.models.player import Player
from app.repositories.player import PlayerRepository
from app.schemas.player import PlayerCreate, PlayerUpdate


class PlayerService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = PlayerRepository(session)

    async def get_or_create_profile(self, current_user: CurrentUser) -> Player:
        existing = await self._repository.get_by_id(current_user.id)
        if existing is not None:
            return existing
        return await self._repository.create(
            PlayerCreate(id=current_user.id, email=current_user.email or "")
        )

    async def get_by_id(self, player_id: UUID) -> Player | None:
        return await self._repository.get_by_id(player_id)

    async def update_profile(self, player: Player, updates: PlayerUpdate) -> Player:
        return await self._repository.update(player, updates)
