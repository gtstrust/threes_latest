"""Round drawing and lifecycle.

This is where the pieces built separately finally meet: the field from M3, the
course's holes from M5, and the pure draw functions from M4. Everything about
*ordering* players lives here rather than in `grouping`, which stays deterministic
so it can be tested exhaustively without fixtures.
"""

import random
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.round import Group, Round, RoundStatus
from app.models.tournament import Tournament, TournamentStatus
from app.repositories.course import CourseRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.round import RoundRepository
from app.repositories.tournament import TournamentRepository
from app.services.grouping import allocate_loops, build_groups, build_loops

FIRST_ROUND = 1

# A round may only be drawn from these states: the first once registration has
# closed, and any later one once the previous round is finished.
DRAWABLE_FROM = frozenset({TournamentStatus.REGISTRATION_CLOSED, TournamentStatus.ROUND_COMPLETE})


class RoundError(Exception):
    """Base for round domain errors. Routers map these onto status codes."""


class RoundNotDrawable(RoundError):
    """The tournament isn't in a state where a new round can be drawn."""


class DrawNotPossible(RoundError):
    """The tournament lacks what a draw needs — a course, holes, or players."""


class RoundNotInProgress(RoundError):
    """Tried to complete a round that isn't currently being played."""


class RoundService:
    def __init__(self, session: AsyncSession) -> None:
        self._rounds = RoundRepository(session)
        self._participants = ParticipantRepository(session)
        self._courses = CourseRepository(session)
        self._tournaments = TournamentRepository(session)

    async def get_by_id(self, round_id: UUID) -> Round | None:
        return await self._rounds.get_by_id(round_id)

    async def get_with_groups(self, round_id: UUID) -> Round | None:
        return await self._rounds.get_with_groups(round_id)

    async def get_group(self, group_id: UUID) -> Group | None:
        return await self._rounds.get_group(group_id)

    async def list_for_tournament(self, tournament_id: UUID) -> Sequence[Round]:
        return await self._rounds.list_for_tournament(tournament_id)

    async def draw_round(self, tournament: Tournament) -> Round:
        """Draw the next round: split the field into groups and give each a loop.

        Round 1 is drawn in registration order, so people play with the mates they
        signed up alongside. Later rounds shuffle first, to mix the field up.

        Raises:
            RoundNotDrawable: If the tournament isn't ready for a new round.
            DrawNotPossible: If it has no course, too few holes, or too few players.
        """
        if tournament.status not in DRAWABLE_FROM:
            raise RoundNotDrawable(
                f"A round can't be drawn while the tournament is "
                f"{tournament.status.value}. Close registration first, or finish "
                "the round in progress."
            )

        if tournament.course_id is None:
            raise DrawNotPossible(
                "This tournament has no course set, so there are no holes to play."
            )

        holes = await self._courses.list_holes(tournament.course_id)
        participants = await self._participants.list_for_tournament(tournament.id)

        round_number = await self._rounds.next_round_number(tournament.id)

        # Registration order for round 1; shuffled thereafter. list_for_tournament
        # already sorts by created_at, so round 1 needs no work at all.
        participant_ids = [participant.id for participant in participants]
        if round_number != FIRST_ROUND:
            random.shuffle(participant_ids)

        try:
            groups = build_groups(participant_ids)
            loops = build_loops([hole.id for hole in holes])
        except ValueError as exc:
            raise DrawNotPossible(str(exc)) from exc

        loop_for_group = allocate_loops(len(groups), len(loops))
        draw = [
            (members, loops[loop_index])
            for members, loop_index in zip(groups, loop_for_group, strict=True)
        ]

        round_ = await self._rounds.create_round_with_groups(
            tournament_id=tournament.id, round_number=round_number, draw=draw
        )
        await self._tournaments.set_status(tournament, TournamentStatus.ROUND_IN_PROGRESS)
        return round_

    async def complete_round(self, tournament: Tournament, round_: Round) -> Round:
        """Finish a round, moving both it and its tournament.

        Raises:
            RoundNotInProgress: If this round isn't the one being played.
        """
        if round_.status is not RoundStatus.IN_PROGRESS:
            raise RoundNotInProgress(
                f"Round {round_.round_number} is {round_.status.value}, not in progress."
            )

        completed = await self._rounds.set_status(round_, RoundStatus.COMPLETE)
        await self._tournaments.set_status(tournament, TournamentStatus.ROUND_COMPLETE)
        return completed
