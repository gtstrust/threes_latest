from uuid import UUID

from sqlalchemy import func, select
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

    async def get_by_referral_code(self, code: str) -> Player | None:
        """Whoever owns this code. `code` must already be in its stored (upper) form."""
        result = await self._session.execute(select(Player).where(Player.referral_code == code))
        return result.scalar_one_or_none()

    async def count_referred_by(self, player_id: UUID) -> int:
        """How many players arrived through this one's code."""
        result = await self._session.execute(
            select(func.count(Player.id)).where(Player.referred_by == player_id)
        )
        return int(result.scalar_one())

    async def create(
        self,
        player_create: PlayerCreate,
        referral_code: str,
        referred_by: UUID | None = None,
    ) -> Player:
        player = Player(
            id=player_create.id,
            email=player_create.email,
            display_name=player_create.display_name,
            referral_code=referral_code,
            referred_by=referred_by,
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
