"""Score entry — the orchestration around the pure scoring engine (ADR-007).

Named `score_entry` rather than `score` so it doesn't sit one letter away from
`scoring`, the pure module it calls. The split is the point: `scoring.py` decides
who won a hole and knows nothing about groups, sessions or HTTP; everything here
is about *which* strokes are allowed to reach it and what happens to the answer.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.round import Group, GroupHole, Round, RoundStatus
from app.models.score import HoleResult, HoleScore
from app.repositories.round import RoundRepository
from app.repositories.score import ScoreRepository
from app.services.scoring import DecidedBy, score_hole


class ScoreError(Exception):
    """Base for score domain errors. Routers map these onto status codes."""


class HoleNotInLoop(ScoreError):
    """The hole isn't one of the three this group was drawn to play."""


class IncompleteCard(ScoreError):
    """The submitted strokes don't cover exactly this group's members.

    A hole can't be scored from a partial card: ADR-007 decides the winner by
    comparing the group against each other, so a missing player could change who
    won. Naming somebody outside the group is a data error rather than an extra.
    """


class ScoringClosed(ScoreError):
    """Scores were submitted for a round that isn't being played."""


class InvalidScores(ScoreError):
    """The scoring engine rejected these strokes or tie-break answers."""


@dataclass(frozen=True)
class ScoredHole:
    """A persisted hole result plus the strokes behind it, ready to serialise."""

    result: HoleResult
    scores: Sequence[HoleScore]
    tied_participants: Sequence[UUID]


def _tied_on_strokes(strokes: Mapping[UUID, int]) -> list[UUID]:
    """Players sharing the fewest strokes — empty when one player is outright."""
    if not strokes:
        return []
    fewest = min(strokes.values())
    tied = [pid for pid, count in strokes.items() if count == fewest]
    return tied if len(tied) > 1 else []


class ScoreEntryService:
    def __init__(self, session: AsyncSession) -> None:
        self._scores = ScoreRepository(session)
        self._rounds = RoundRepository(session)

    async def submit_hole(
        self,
        *,
        group: Group,
        round_: Round,
        hole_id: UUID,
        strokes: Mapping[UUID, int],
        closest_to_pin: UUID | None = None,
        longest_drive: UUID | None = None,
    ) -> ScoredHole:
        """Score one hole for a group and persist both the strokes and the result.

        Re-submitting a hole overwrites it. That is how a mis-entry gets corrected
        and how a tie-break answer arrives: strokes go in first, and if they tie,
        the group is asked and posts the same hole again with an answer.

        Raises:
            ScoringClosed: If the round isn't in progress.
            HoleNotInLoop: If the hole isn't part of this group's loop.
            IncompleteCard: If the strokes don't cover exactly the group's members.
            InvalidScores: If the engine rejects the strokes or a tie-break answer.
        """
        if round_.status is not RoundStatus.IN_PROGRESS:
            raise ScoringClosed(
                f"Round {round_.round_number} is {round_.status.value}, so its scores are closed."
            )

        self._require_hole_in_loop(group, hole_id)
        self._require_complete_card(group, strokes)

        try:
            outcome = score_hole(
                strokes,
                closest_to_pin=closest_to_pin,
                longest_drive=longest_drive,
            )
        except ValueError as exc:
            raise InvalidScores(str(exc)) from exc

        # ADR-007: record a tie-break only where it actually decided the hole, so
        # an answer given for a hole that turned out not to need one is dropped.
        result = await self._scores.upsert_hole(
            group_id=group.id,
            hole_id=hole_id,
            strokes=strokes,
            points=outcome.points,
            winner_participant_id=outcome.winner,
            decided_by=outcome.decided_by,
            closest_to_pin=(
                closest_to_pin if outcome.decided_by is DecidedBy.CLOSEST_TO_PIN else None
            ),
            longest_drive=(
                longest_drive if outcome.decided_by is DecidedBy.LONGEST_DRIVE else None
            ),
        )

        return ScoredHole(
            result=result,
            scores=await self._scores.list_scores_for_hole(group.id, hole_id),
            tied_participants=_tied_on_strokes(strokes) if outcome.winner is None else [],
        )

    async def get_card(self, group: Group) -> list[ScoredHole]:
        """Every hole of this group's loop that has been scored, in playing order."""
        results = {
            result.hole_id: result for result in await self._scores.list_results_for_group(group.id)
        }
        scores_by_hole: dict[UUID, list[HoleScore]] = {}
        for score in await self._scores.list_scores_for_group(group.id):
            scores_by_hole.setdefault(score.hole_id, []).append(score)

        card: list[ScoredHole] = []
        for group_hole in sorted(group.holes, key=lambda hole: hole.sequence):
            result = results.get(group_hole.hole_id)
            if result is None:
                continue
            hole_scores = scores_by_hole.get(group_hole.hole_id, [])
            card.append(
                ScoredHole(
                    result=result,
                    scores=hole_scores,
                    tied_participants=(
                        _tied_on_strokes({s.participant_id: s.strokes for s in hole_scores})
                        if result.winner_participant_id is None
                        else []
                    ),
                )
            )
        return card

    @staticmethod
    def _require_hole_in_loop(group: Group, hole_id: UUID) -> None:
        loop: list[GroupHole] = list(group.holes)
        if hole_id not in {group_hole.hole_id for group_hole in loop}:
            raise HoleNotInLoop(
                f"Hole {hole_id} is not part of this group's loop. It plays "
                f"{sorted(str(group_hole.hole_id) for group_hole in loop)}."
            )

    @staticmethod
    def _require_complete_card(group: Group, strokes: Mapping[UUID, int]) -> None:
        members: set[UUID] = {member.participant_id for member in group.members}
        submitted = set(strokes)

        missing = members - submitted
        if missing:
            raise IncompleteCard(
                "Every player in the group needs a score for the hole. Missing: "
                f"{sorted(str(pid) for pid in missing)}."
            )

        strangers = submitted - members
        if strangers:
            raise IncompleteCard(
                "These players are not in this group: " f"{sorted(str(pid) for pid in strangers)}."
            )
