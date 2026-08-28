"""Fun Round orchestration (Phase 2).

A Fun Round is a casual, self-run round: a golfer starts one, a few mates join by
link (or are added as virtual players), they score a single 3-hole loop and watch a
live leaderboard — no organiser ceremony. It reuses the entire tournament engine
rather than duplicating it: a fun round *is* a `tournaments` row with
`kind=FUN_ROUND` (see ADR-009/ADR-010's aversion to second copies), and this service
is the thin layer that drives the existing services through the casual flow so the
ADR-003 state machine advances automatically instead of by organiser button-presses.

Everything hard — the draw, score entry, the leaderboard, realtime, and the auth
guards (the host simply *is* the organiser) — is the existing code, unchanged. The
only rule this service adds is the field cap: a fun round is a single group, so the
field is capped at `MAX_GROUP_SIZE` and needs at least `MIN_GROUP_SIZE` to start.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.models.participant import TournamentParticipant
from app.models.round import Round
from app.models.tournament import Tournament, TournamentKind, TournamentStatus
from app.schemas.fun_round import FunRoundCreate
from app.schemas.tournament import TournamentCreate
from app.services.grouping import MAX_GROUP_SIZE, MIN_GROUP_SIZE
from app.services.participant import ParticipantService
from app.services.round import RoundService
from app.services.tournament import TournamentService


class FunRoundError(Exception):
    """Base for fun-round domain errors. Routers map these onto status codes."""


class FunRoundFull(FunRoundError):
    """A fun round is a single group, so its field is capped at MAX_GROUP_SIZE."""


class FunRoundNotStartable(FunRoundError):
    """Too few players to draw the group."""


class FunRoundNotStarted(FunRoundError):
    """An action needs the round to have been drawn, and it hasn't been."""


class FunRoundService:
    """Drives a Fun Round through the existing tournament/round/participant services."""

    def __init__(self, session: AsyncSession) -> None:
        self._tournaments = TournamentService(session)
        self._participants = ParticipantService(session)
        self._rounds = RoundService(session)

    async def get_by_id(self, fun_round_id: UUID) -> Tournament | None:
        """The fun round, or None — a real tournament's id is *not* a fun round here."""
        tournament = await self._tournaments.get_by_id(fun_round_id)
        if tournament is None or tournament.kind is not TournamentKind.FUN_ROUND:
            return None
        return tournament

    async def list_for_player(self, player_id: UUID) -> Sequence[Tournament]:
        return await self._tournaments.list_fun_rounds_for_player(player_id)

    async def list_field(self, fun_round: Tournament) -> Sequence[TournamentParticipant]:
        return await self._participants.list_for_tournament(fun_round.id)

    async def get_round(self, fun_round: Tournament) -> Round | None:
        """The fun round's single round, with its group, or None if not started."""
        rounds = await self._rounds.list_for_tournament(fun_round.id)
        if not rounds:
            return None
        return await self._rounds.get_with_groups(rounds[-1].id)

    async def create(self, host: CurrentUser, payload: FunRoundCreate) -> Tournament:
        """Create a fun round, open it for joining, and put the host in the field.

        Registration is opened immediately so mates can join by link, and the host
        is self-registered as the first player — a fun round the host doesn't play
        would be a tournament.

        Raises:
            OrganiserProfileMissing: If the host hasn't provisioned a profile.
        """
        fun_round = await self._tournaments.create(
            host,
            TournamentCreate(name=payload.name, course_id=payload.course_id),
            kind=TournamentKind.FUN_ROUND,
        )
        fun_round = await self._tournaments.transition(
            fun_round, TournamentStatus.REGISTRATION_OPEN
        )
        await self._participants.self_register(fun_round, host, payload.display_name)
        return fun_round

    async def join(
        self, fun_round: Tournament, current_user: CurrentUser, display_name: str | None
    ) -> TournamentParticipant:
        """Add the caller to a fun round they opened the link to.

        Raises:
            FunRoundFull: If the group already has MAX_GROUP_SIZE players.
            RegistrationClosed / AlreadyRegistered / PlayerProfileMissing: from
                the underlying self-registration.
        """
        existing = await self._participants.get_for_player(fun_round.id, current_user.id)
        if existing is None and await self._is_full(fun_round):
            raise self._full_error()
        return await self._participants.self_register(fun_round, current_user, display_name)

    async def add_virtual(self, fun_round: Tournament, display_name: str) -> TournamentParticipant:
        """Add a mate with no account, whose scores the host enters.

        Raises:
            FunRoundFull: If the group is already at MAX_GROUP_SIZE.
            FieldLocked: If play has already started.
        """
        if await self._is_full(fun_round):
            raise self._full_error()
        return await self._participants.add_virtual_player(fun_round, display_name)

    async def start(self, fun_round: Tournament, hole_numbers: Sequence[int] | None) -> Round:
        """Close joining and draw the single group over its 3-hole loop.

        Raises:
            FunRoundNotStartable: If the field is smaller than MIN_GROUP_SIZE.
            RoundNotDrawable / DrawNotPossible: from the underlying draw (e.g. no
                course set, or the round already drawn).
        """
        field = await self._participants.list_for_tournament(fun_round.id)
        if len(field) < MIN_GROUP_SIZE:
            raise FunRoundNotStartable(
                f"A fun round needs at least {MIN_GROUP_SIZE} players to start; "
                f"this one has {len(field)}."
            )
        await self._tournaments.transition(fun_round, TournamentStatus.REGISTRATION_CLOSED)
        return await self._rounds.draw_round(fun_round, hole_numbers)

    async def finish(self, fun_round: Tournament) -> Round:
        """End the round and mark the fun round complete.

        Raises:
            FunRoundNotStarted: If the round was never drawn.
            RoundNotInProgress: If it isn't currently being played.
        """
        rounds = await self._rounds.list_for_tournament(fun_round.id)
        if not rounds:
            raise FunRoundNotStarted("This fun round hasn't started yet.")
        completed = await self._rounds.complete_round(fun_round, rounds[-1])
        await self._tournaments.transition(fun_round, TournamentStatus.TOURNAMENT_COMPLETE)
        return completed

    async def _is_full(self, fun_round: Tournament) -> bool:
        field = await self._participants.list_for_tournament(fun_round.id)
        return len(field) >= MAX_GROUP_SIZE

    @staticmethod
    def _full_error() -> FunRoundFull:
        return FunRoundFull(
            f"A fun round is one group of up to {MAX_GROUP_SIZE} players, and this " "one is full."
        )
