"""Tournament state machine and service — see CLAUDE.md ADR-003.

`ALLOWED_TRANSITIONS` and `can_transition` are deliberately free of database and
framework dependencies so the state machine can be tested on its own. The service
class below is the only part that touches persistence.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.models.tournament import Tournament, TournamentStatus
from app.repositories.player import PlayerRepository
from app.repositories.tournament import TournamentRepository
from app.schemas.tournament import TournamentCreate, TournamentUpdate

# The linear path from ADR-003, plus one loop: ROUND_COMPLETE back to
# ROUND_IN_PROGRESS, so a tournament can run more than one 3-hole round. There is
# deliberately no way to reopen registration and no cancelled state — both were
# considered and left out to keep the machine predictable.
ALLOWED_TRANSITIONS: dict[TournamentStatus, frozenset[TournamentStatus]] = {
    TournamentStatus.CREATED: frozenset({TournamentStatus.REGISTRATION_OPEN}),
    TournamentStatus.REGISTRATION_OPEN: frozenset({TournamentStatus.REGISTRATION_CLOSED}),
    TournamentStatus.REGISTRATION_CLOSED: frozenset({TournamentStatus.ROUND_IN_PROGRESS}),
    TournamentStatus.ROUND_IN_PROGRESS: frozenset({TournamentStatus.ROUND_COMPLETE}),
    TournamentStatus.ROUND_COMPLETE: frozenset(
        {TournamentStatus.ROUND_IN_PROGRESS, TournamentStatus.TOURNAMENT_COMPLETE}
    ),
    TournamentStatus.TOURNAMENT_COMPLETE: frozenset(),
}


def can_transition(current: TournamentStatus, target: TournamentStatus) -> bool:
    """Whether `current -> target` is a legal move. Staying put is not a move."""
    return target in ALLOWED_TRANSITIONS[current]


class TournamentError(Exception):
    """Base for tournament domain errors. Routers map these onto status codes."""


class OrganiserProfileMissing(TournamentError):
    """The authenticated user has a valid JWT but no `players` row yet."""


class RoundDrivenStatus(TournamentError):
    """This status is owned by the round endpoints, not set directly.

    Drawing a round and starting play are one action, as are finishing a round and
    ending it. Allowing the status to be set on its own would let a tournament sit
    in ROUND_IN_PROGRESS with no round drawn, or in ROUND_COMPLETE with a round
    still marked in progress — two sources of truth quietly disagreeing.
    """

    def __init__(self, target: TournamentStatus, endpoint: str) -> None:
        self.target = target
        super().__init__(
            f"{target.value} is set by playing the round, not directly. Use {endpoint}."
        )


class InvalidTransition(TournamentError):
    """The requested status change isn't legal from the tournament's current state."""

    def __init__(self, current: TournamentStatus, target: TournamentStatus) -> None:
        self.current = current
        self.target = target
        allowed = sorted(status.value for status in ALLOWED_TRANSITIONS[current])
        super().__init__(
            f"Cannot move a tournament from {current.value} to {target.value}. "
            f"Allowed from {current.value}: {allowed or ['(none — terminal state)']}"
        )


class TournamentService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = TournamentRepository(session)
        self._players = PlayerRepository(session)

    async def create(self, organiser: CurrentUser, payload: TournamentCreate) -> Tournament:
        """Create a tournament owned by `organiser`.

        Raises:
            OrganiserProfileMissing: If the user hasn't provisioned a profile.
                organiser_id is a foreign key to `players`, and the row is created
                lazily by POST /players, so this would otherwise surface as an
                integrity error from the database.
        """
        if await self._players.get_by_id(organiser.id) is None:
            raise OrganiserProfileMissing
        return await self._repository.create(organiser.id, payload)

    async def get_by_id(self, tournament_id: UUID) -> Tournament | None:
        return await self._repository.get_by_id(tournament_id)

    async def list_for_organiser(self, organiser_id: UUID) -> Sequence[Tournament]:
        return await self._repository.list_for_organiser(organiser_id)

    async def list_for_player(self, player_id: UUID) -> Sequence[Tournament]:
        """Tournaments the player is competing in, which they may not organise."""
        return await self._repository.list_for_player(player_id)

    async def update_details(self, tournament: Tournament, updates: TournamentUpdate) -> Tournament:
        return await self._repository.update(tournament, updates)

    async def transition(self, tournament: Tournament, target: TournamentStatus) -> Tournament:
        """Move a tournament to `target` on behalf of a direct status request.

        Raises:
            RoundDrivenStatus: If `target` belongs to the round endpoints.
            InvalidTransition: If the move isn't legal from the current state.
        """
        _reject_round_driven(target)
        if not can_transition(tournament.status, target):
            raise InvalidTransition(tournament.status, target)
        return await self._repository.set_status(tournament, target)


# Statuses that only the round endpoints may set, and where to go instead.
ROUND_DRIVEN_STATUSES: dict[TournamentStatus, str] = {
    TournamentStatus.ROUND_IN_PROGRESS: "POST /tournaments/{id}/rounds to draw the next round",
    TournamentStatus.ROUND_COMPLETE: "POST /rounds/{round_id}/complete to finish the round",
}


def _reject_round_driven(target: TournamentStatus) -> None:
    endpoint = ROUND_DRIVEN_STATUSES.get(target)
    if endpoint is not None:
        raise RoundDrivenStatus(target, endpoint)


# There was a readiness check here for "no course set" before starting a round.
# It moved into RoundService.draw_round, which is now the only way to reach
# ROUND_IN_PROGRESS — leaving it here would have been a rule that looked enforced
# but could never fire, since _reject_round_driven refuses that target first.
