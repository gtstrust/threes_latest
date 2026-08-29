from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.models.player import Player
from app.repositories.player import PlayerRepository
from app.schemas.player import PlayerCreate, PlayerUpdate
from app.services.join_code import generate_referral_code, normalise_code

# Same reasoning as the join code's retry: a collision in a 24-million space is
# a retry, not a strategy, and the unique constraint is the check.
REFERRAL_CODE_ATTEMPTS = 5


class PlayerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = PlayerRepository(session)

    async def get_or_create_profile(
        self, current_user: CurrentUser, referral_code: str | None = None
    ) -> Player:
        """Ensure a profile exists, recording who referred them if this is the first time.

        **Attribution happens only at creation.** Someone is referred once, at the
        moment they arrive, or not at all: this endpoint is called on every login,
        so honouring a code on an existing profile would let the last person to
        send a link claim a player who has been here for months.

        An unknown code is ignored rather than refused. It arrives from a URL that
        has survived an email round trip, and failing a login over a mistyped
        query parameter would trade a real sign-in for a piece of analytics.
        """
        existing = await self._repository.get_by_id(current_user.id)
        if existing is not None:
            return existing

        referrer = await self._resolve_referrer(referral_code, current_user.id)
        return await self._create_with_code(
            PlayerCreate(id=current_user.id, email=current_user.email or ""), referrer
        )

    async def count_referred(self, player_id: UUID) -> int:
        """How many players arrived through this one's code."""
        return await self._repository.count_referred_by(player_id)

    async def _resolve_referrer(self, code: str | None, new_player_id: UUID) -> UUID | None:
        if not code:
            return None
        referrer = await self._repository.get_by_referral_code(normalise_code(code))
        if referrer is None:
            return None
        # Nobody refers themselves. The profile doesn't exist yet so this cannot
        # happen through the normal flow, but a code pasted into a fresh session
        # is a cheap thing to guard against a loop in the graph.
        if referrer.id == new_player_id:
            return None
        return referrer.id

    async def _create_with_code(self, payload: PlayerCreate, referred_by: UUID | None) -> Player:
        """Create the profile, retrying if its generated code is already taken."""
        for attempt in range(REFERRAL_CODE_ATTEMPTS):
            try:
                async with self._session.begin_nested():
                    return await self._repository.create(
                        payload, generate_referral_code(), referred_by
                    )
            except IntegrityError:
                if attempt == REFERRAL_CODE_ATTEMPTS - 1:
                    raise
        raise AssertionError("unreachable: the loop either returns or raises")

    async def get_by_id(self, player_id: UUID) -> Player | None:
        return await self._repository.get_by_id(player_id)

    async def update_profile(self, player: Player, updates: PlayerUpdate) -> Player:
        return await self._repository.update(player, updates)
