"""Tournament participant business logic.

The rules here are mostly about *when* the field can change. The state machine has
no route back to REGISTRATION_OPEN (ADR-003), so if only that state allowed
changes, a no-show would be stuck in the field with no way to remove them. The
organiser therefore keeps an override right up until play starts, while players
can only add themselves during registration.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.models.participant import TournamentParticipant
from app.models.tournament import Tournament, TournamentStatus
from app.repositories.participant import ParticipantRepository
from app.repositories.player import PlayerRepository

# The organiser may still adjust the field in these states. Once a round is in
# progress, groups exist and scores are being recorded, so the field is fixed.
ORGANISER_EDITABLE_STATES = frozenset(
    {
        TournamentStatus.CREATED,
        TournamentStatus.REGISTRATION_OPEN,
        TournamentStatus.REGISTRATION_CLOSED,
    }
)


class ParticipantError(Exception):
    """Base for participant domain errors. Routers map these onto status codes."""


class PlayerProfileMissing(ParticipantError):
    """The caller holds a valid JWT but has no `players` row yet."""


class RegistrationClosed(ParticipantError):
    """Self-registration was attempted outside REGISTRATION_OPEN."""


class FieldLocked(ParticipantError):
    """The organiser tried to change the field once play had started."""


class AlreadyRegistered(ParticipantError):
    """This player already has a place in this tournament."""


class ParticipantService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = ParticipantRepository(session)
        self._players = PlayerRepository(session)

    async def list_for_tournament(self, tournament_id: UUID) -> Sequence[TournamentParticipant]:
        return await self._repository.list_for_tournament(tournament_id)

    async def get_by_id(self, participant_id: UUID) -> TournamentParticipant | None:
        return await self._repository.get_by_id(participant_id)

    async def get_for_player(
        self, tournament_id: UUID, player_id: UUID
    ) -> TournamentParticipant | None:
        return await self._repository.get_for_player(tournament_id, player_id)

    async def self_register(
        self, tournament: Tournament, current_user: CurrentUser, display_name: str | None
    ) -> TournamentParticipant:
        """Add the caller to a tournament's field.

        Raises:
            RegistrationClosed: If the tournament isn't accepting registrations.
            PlayerProfileMissing: If the caller hasn't provisioned a profile.
            AlreadyRegistered: If they already have a place.
        """
        if tournament.status is not TournamentStatus.REGISTRATION_OPEN:
            raise RegistrationClosed(
                f"Registration for this tournament is not open (status "
                f"{tournament.status.value}). Ask the organiser to add you."
            )

        player = await self._players.get_by_id(current_user.id)
        if player is None:
            raise PlayerProfileMissing

        existing = await self._repository.get_for_player(tournament.id, current_user.id)
        if existing is not None:
            raise AlreadyRegistered(f"You are already registered as {existing.display_name!r}")

        # Resolve once and store it: profile names can change later, and a
        # leaderboard shouldn't retroactively rename people mid-event.
        resolved = display_name or player.display_name or player.email

        return await self._repository.create(
            tournament_id=tournament.id, display_name=resolved, player_id=current_user.id
        )

    async def add_virtual_player(
        self, tournament: Tournament, display_name: str
    ) -> TournamentParticipant:
        """Add someone with no account, whose scores a groupmate will enter.

        Names are deliberately not unique — two players really can both be called
        John Smith, and refusing that would be worse than the ambiguity.

        Raises:
            FieldLocked: If play has already started.
        """
        self._require_field_unlocked(tournament)
        return await self._repository.create(
            tournament_id=tournament.id, display_name=display_name, player_id=None
        )

    async def remove(self, tournament: Tournament, participant: TournamentParticipant) -> None:
        """Remove someone from the field.

        Raises:
            FieldLocked: If play has already started.
        """
        self._require_field_unlocked(tournament)
        await self._repository.delete(participant)

    @staticmethod
    def _require_field_unlocked(tournament: Tournament) -> None:
        if tournament.status not in ORGANISER_EDITABLE_STATES:
            raise FieldLocked(
                f"The field is fixed once play starts (status "
                f"{tournament.status.value}); groups have already been drawn."
            )
