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
from app.repositories.course import CourseRepository
from app.schemas.fun_round import FunRoundCreate
from app.schemas.tournament import TournamentCreate
from app.services.grouping import HOLES_PER_LOOP, MAX_GROUP_SIZE, MIN_GROUP_SIZE
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


class FunRoundHolesUnavailable(FunRoundError):
    """The chosen holes aren't on the chosen course."""


class FunRoundService:
    """Drives a Fun Round through the existing tournament/round/participant services."""

    def __init__(self, session: AsyncSession) -> None:
        self._tournaments = TournamentService(session)
        self._participants = ParticipantService(session)
        self._rounds = RoundService(session)
        self._courses = CourseRepository(session)

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

        The hole selection is checked against the course *now*, while the host is
        still on the setup form and can pick differently. Deferring it to the draw
        would surface it at the first tee, with the group already assembled — which
        is exactly the failure this ordering exists to avoid.

        Raises:
            OrganiserProfileMissing: If the host hasn't provisioned a profile.
            FunRoundHolesUnavailable: If the chosen holes aren't on the course.
        """
        if payload.course_id is not None and payload.hole_numbers is not None:
            await self._require_holes_exist(payload.course_id, payload.hole_numbers)

        fun_round = await self._tournaments.create(
            host,
            TournamentCreate(name=payload.name, course_id=payload.course_id),
            kind=TournamentKind.FUN_ROUND,
            hole_numbers=payload.hole_numbers,
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
        if existing is None and await self.is_full(fun_round):
            raise self._full_error()
        return await self._participants.self_register(fun_round, current_user, display_name)

    async def add_virtual(self, fun_round: Tournament, display_name: str) -> TournamentParticipant:
        """Add a mate with no account, whose scores the host enters.

        Raises:
            FunRoundFull: If the group is already at MAX_GROUP_SIZE.
            FieldLocked: If play has already started.
        """
        if await self.is_full(fun_round):
            raise self._full_error()
        return await self._participants.add_virtual_player(fun_round, display_name)

    async def start(self, fun_round: Tournament, hole_numbers: Sequence[int] | None) -> Round:
        """Close joining and draw the single group over its 3-hole loop.

        The loop is whatever the host chose at setup, unless this call names one —
        an override for the group that reached the tee and found it occupied.

        Raises:
            FunRoundNotStartable: If the field is smaller than MIN_GROUP_SIZE, or
                the course doesn't hold a full loop.
            RoundNotDrawable / DrawNotPossible: from the underlying draw (e.g. no
                course set, or the round already drawn).
        """
        field = await self._participants.list_for_tournament(fun_round.id)
        if len(field) < MIN_GROUP_SIZE:
            raise FunRoundNotStartable(
                f"A fun round needs at least {MIN_GROUP_SIZE} players to start; "
                f"this one has {len(field)}."
            )

        selection = list(hole_numbers) if hole_numbers is not None else fun_round.hole_numbers
        await self._require_playable_course(fun_round, selection)

        await self._tournaments.transition(fun_round, TournamentStatus.REGISTRATION_CLOSED)
        return await self._rounds.draw_round(fun_round, selection)

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

    async def is_full(self, fun_round: Tournament) -> bool:
        """Whether the single group has no room left. Public so the preview can say so."""
        field = await self._participants.list_for_tournament(fun_round.id)
        return len(field) >= MAX_GROUP_SIZE

    async def _require_holes_exist(self, course_id: UUID, wanted: Sequence[int]) -> None:
        """Check every chosen hole is actually on the course.

        Raises:
            FunRoundHolesUnavailable: naming what's missing and what's there, so the
                host can correct the selection without going to look it up.
        """
        entered = sorted(hole.hole_number for hole in await self._courses.list_holes(course_id))
        missing = sorted({n for n in wanted if n not in set(entered)})
        if missing:
            raise FunRoundHolesUnavailable(
                f"This course has no hole {missing} entered. It has "
                f"{entered or 'no holes'}. Add the holes to the course first, or "
                "pick from the ones it has."
            )

    async def _require_playable_course(
        self, fun_round: Tournament, selection: Sequence[int] | None
    ) -> None:
        """Check there are holes to play before closing registration.

        Without this the draw refuses instead, but only after the state machine has
        already moved — and it answers in the pure engine's vocabulary ("a loop needs
        3 holes") rather than telling the host what to do about it.

        Raises:
            FunRoundNotStartable: If the course is unset or holds less than a loop.
            FunRoundHolesUnavailable: If the selection names holes it doesn't have.
        """
        if fun_round.course_id is None:
            raise FunRoundNotStartable("This round has no course, so there are no holes to play.")

        if selection is not None:
            await self._require_holes_exist(fun_round.course_id, selection)
            return

        entered = len(await self._courses.list_holes(fun_round.course_id))
        if entered < HOLES_PER_LOOP:
            raise FunRoundNotStartable(
                f"A loop is {HOLES_PER_LOOP} holes and this course has "
                f"{entered} entered. Add its holes, then start the round."
            )

    @staticmethod
    def _full_error() -> FunRoundFull:
        return FunRoundFull(
            f"A fun round is one group of up to {MAX_GROUP_SIZE} players, and this " "one is full."
        )
