"""Knockout advancement — who goes through from each group (ADR-012).

Named to sit a clear distance from `scoring.py`, the pure module it calls, in the
same way `score_entry.py` does. `decide_advancement` decides who won a group;
this decides which groups to ask about, records the answer, and reports who is
left. Anything needing a database belongs here rather than there.

This module never imports `round.py`. `field_for_next_round` returns plain data
and lets the round service own what a draw refuses and how it is worded, which is
what keeps the two free of a cycle.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.round import Group, Round, RoundStatus
from app.models.score import HoleResult
from app.models.tournament import Tournament, TournamentFormat
from app.repositories.round import RoundRepository
from app.repositories.score import ScoreRepository, ScoreTotals
from app.services.scoring import (
    Advancement,
    AdvancedBy,
    GroupStanding,
    decide_advancement,
)

NO_SCORE = ScoreTotals(points=0, strokes=0, holes_played=0)


class AdvancementError(Exception):
    """Base for advancement domain errors. Routers map these onto status codes."""


class NotAKnockout(AdvancementError):
    """Nobody advances from a round robin — there is nothing to adjudicate."""


class AdvancementNotOpen(AdvancementError):
    """The round is still being played, so its groups have no verdict yet."""


class AlreadyAdvanced(AdvancementError):
    """This group already has a verdict, and a stored verdict is not editable."""


class NotInGroup(AdvancementError):
    """Named a player who did not play in this group."""


@dataclass(frozen=True)
class GroupVerdict:
    """What one group decided, ready to be shown or stored."""

    group_id: UUID
    group_number: int
    advancement: Advancement


@dataclass(frozen=True)
class KnockoutField:
    """Who is still in after a round, and which groups have not said.

    Plain data rather than an exception so the round service goes on owning what
    a draw refuses — see this module's docstring.
    """

    #: The advancing players, in group order.
    advancing: tuple[UUID, ...]
    #: Group numbers whose verdict the cascade could not reach.
    undecided: tuple[int, ...]


class AdvancementService:
    def __init__(self, session: AsyncSession) -> None:
        self._rounds = RoundRepository(session)
        self._scores = ScoreRepository(session)

    async def decide_round(self, tournament: Tournament, round_: Round) -> list[GroupVerdict]:
        """Record who goes through from each group of a round that just finished.

        A no-op returning `[]` unless the tournament is a knockout — nothing is
        read and nothing is written — which is what makes a round robin's
        behaviour provably unchanged.

        Called from `RoundService.complete_round`, the moment a round's scores
        stop changing: `submit_hole` refuses a round that is not `IN_PROGRESS`
        and there is no route back, so a verdict can never fall out of step with
        the scores behind it (ADR-012).
        """
        if tournament.format is not TournamentFormat.KNOCKOUT:
            return []

        loaded = await self._rounds.get_with_groups(round_.id)
        if loaded is None:
            return []

        totals = await self._scores.totals_by_group_for_round(round_.id)
        winners = self._hole_winners_by_group(await self._scores.list_results_for_round(round_.id))

        verdicts: list[GroupVerdict] = []
        for group in loaded.groups:
            advancement = decide_advancement(
                self._standings(group, totals.get(group.id, {})),
                [winners.get(group.id, {}).get(hole.hole_id) for hole in group.holes],
            )
            await self._rounds.set_advancement(group, advancement.winner, advancement.decided_by)
            verdicts.append(GroupVerdict(group.id, group.group_number, advancement))
        return verdicts

    @staticmethod
    def _hole_winners_by_group(
        results: Sequence[HoleResult],
    ) -> dict[UUID, dict[UUID, UUID | None]]:
        """Bucket a round's hole results into `{group: {hole: winner}}`.

        A halved hole is kept, with a winner of None: countback has to skip it by
        position rather than never see it, or the loop's holes would shift and
        "the latest hole" would name the wrong one.
        """
        by_group: dict[UUID, dict[UUID, UUID | None]] = {}
        for result in results:
            by_group.setdefault(result.group_id, {})[result.hole_id] = result.winner_participant_id
        return by_group

    @staticmethod
    def _standings(group: Group, totals: dict[UUID, ScoreTotals]) -> list[GroupStanding]:
        """Every member's card, zero-filled, in a stable order.

        `Group.members` carries no `order_by`, so the order is imposed here.
        Without it `Advancement.tied` — which the organiser's screen renders as a
        list to choose from — would reorder between requests for no reason.

        A member who never scored is zero-filled rather than dropped, the same
        way the leaderboard fills its field: somebody who walked in without
        finishing is still in the group and still cannot win it.
        """
        members = sorted(group.members, key=lambda member: str(member.participant_id))
        return [
            GroupStanding(
                participant_id=member.participant_id,
                points=totals.get(member.participant_id, NO_SCORE).points,
                total_strokes=totals.get(member.participant_id, NO_SCORE).strokes,
            )
            for member in members
        ]

    async def field_for_next_round(self, previous: Round) -> KnockoutField:
        """Who won their group in `previous`, and which groups never said."""
        advancement = await self._rounds.advancement_for_round(previous.id)
        return KnockoutField(
            advancing=tuple(
                participant_id for _, participant_id in advancement if participant_id is not None
            ),
            undecided=tuple(
                number for number, participant_id in advancement if participant_id is None
            ),
        )

    async def adjudicate(
        self,
        *,
        tournament: Tournament,
        round_: Round,
        group: Group,
        participant_id: UUID,
    ) -> Group:
        """Send a player through from a group the cascade could not settle.

        The organiser is the backstop for "nothing separated them", not an editor
        of results — a group that already has a verdict is refused rather than
        overwritten. The stored verdict is the record of what the field was told
        on the day (ADR-009), and there is no correction to serve either, since a
        completed round's scores are closed.

        Raises:
            NotAKnockout: If this is a round robin, where nobody advances.
            AdvancementNotOpen: If the round is still being played.
            AlreadyAdvanced: If this group has already decided.
            NotInGroup: If `participant_id` did not play in this group.
        """
        if tournament.format is not TournamentFormat.KNOCKOUT:
            raise NotAKnockout(
                "This is a round robin — every player goes through to the next round, "
                "so there is nothing to adjudicate."
            )
        if round_.status is not RoundStatus.COMPLETE:
            raise AdvancementNotOpen(
                f"Round {round_.round_number} is {round_.status.value}. Finish it first — "
                "who goes through is decided from the round's final scores."
            )
        if group.advancing_participant_id is not None:
            raise AlreadyAdvanced(
                f"Group {group.group_number} has already decided. A verdict is the record "
                "of what the group was told on the day, so it cannot be changed."
            )
        if participant_id not in {member.participant_id for member in group.members}:
            raise NotInGroup(
                f"That player did not play in group {group.group_number}, so they cannot "
                "go through from it."
            )

        return await self._rounds.set_advancement(group, participant_id, AdvancedBy.ORGANISER)
