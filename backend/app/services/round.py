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

from app.models.course import Hole
from app.models.round import Group, Round, RoundStatus
from app.models.tournament import Tournament, TournamentFormat, TournamentStatus
from app.repositories.course import CourseRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.round import RoundRepository
from app.repositories.tournament import TournamentRepository
from app.services.advancement import AdvancementService
from app.services.grouping import (
    HOLES_PER_LOOP,
    LoopStyle,
    allocate_loops,
    build_groups,
    plan_loops,
)

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


class AwaitingAdjudication(DrawNotPossible):
    """A group of the previous knockout round has no advancing player yet.

    A subclass so the router's existing handler answers 409 with no change, while
    still being a type tests and any future routing can name.
    """


class KnockoutComplete(DrawNotPossible):
    """One player is left. The bracket is over; there is nothing left to draw."""


def _select_holes(holes: Sequence[Hole], wanted: Sequence[int]) -> list[Hole]:
    """Narrow a course's holes to the ones asked for, in playing order.

    Sorted by hole number rather than kept in the order given: both loop builders
    document their input as being in playing order, and a group that asked for
    7, 8, 9 plays them in that order whatever sequence they typed.

    That sort is not a limitation on a wrapping loop — it is the **precondition**
    for one. A shotgun draw (ADR-011) generates 17, 18, 1 itself, by counting
    modulo the holes in play, so what it needs from here is the selection in
    course order. The order the organiser happened to type carries nothing the
    draw can use.

    Raises:
        DrawNotPossible: If the course has no hole with one of these numbers.
    """
    by_number = {hole.hole_number: hole for hole in holes}
    missing = sorted(number for number in wanted if number not in by_number)
    if missing:
        entered = sorted(by_number)
        raise DrawNotPossible(
            f"This course has no hole {missing} entered. It has {entered or 'no holes'}. "
            "Add the holes to the course first, or pick from the ones it has."
        )
    return [by_number[number] for number in sorted(set(wanted))]


def _require_stroke_indexes(holes: Sequence[Hole]) -> None:
    """Refuse a handicap draw over holes that cannot be ranked for difficulty.

    Shots are dealt hardest-first (ADR-013), so a hole with no stroke index has no
    place in the order. `stroke_index` stays nullable because a scratch event
    never needs one — this is the one event that does, and it says so loudly.

    Named by hole number rather than id, because that is the only name the
    organiser fixing it will recognise.
    """
    missing = sorted(hole.hole_number for hole in holes if hole.stroke_index is None)
    if missing:
        raise DrawNotPossible(
            "Handicaps need a stroke index on every hole being played, and "
            f"{'hole' if len(missing) == 1 else 'holes'} "
            f"{', '.join(str(number) for number in missing)} "
            f"{'has' if len(missing) == 1 else 'have'} none. Add them to the "
            "course, or turn handicaps off for this event."
        )


def _check_selection(hole_count: int, style: LoopStyle) -> None:
    """Refuse a selection this event's start style cannot cut into whole loops.

    Style-dependent, so it cannot live on `RoundDraw` the way the range and
    duplicate checks do: the style is a property of the tournament and the
    request body cannot see it. A shotgun over holes 1-10 is ten loops and
    perfectly valid, and a schema enforcing "a multiple of three" would 422 it.

    So it sits here instead, beside the other thing only the service knows —
    whether the course actually has those holes — and answers with the same
    `DrawNotPossible`, i.e. a 409 rather than a 422.

    Raises:
        DrawNotPossible: If BLOCKS was asked for a selection that isn't whole loops.
    """
    if style is LoopStyle.SHOTGUN:
        return
    if hole_count % HOLES_PER_LOOP:
        raise DrawNotPossible(
            f"A loop is {HOLES_PER_LOOP} holes, so a blocks draw needs a multiple "
            f"of {HOLES_PER_LOOP}; got {hole_count}. Or draw this round as a "
            "shotgun, where every hole is a starting tee."
        )


class RoundService:
    def __init__(self, session: AsyncSession) -> None:
        self._rounds = RoundRepository(session)
        self._participants = ParticipantRepository(session)
        self._courses = CourseRepository(session)
        self._tournaments = TournamentRepository(session)
        self._advancement = AdvancementService(session)

    async def get_by_id(self, round_id: UUID) -> Round | None:
        return await self._rounds.get_by_id(round_id)

    async def get_with_groups(self, round_id: UUID) -> Round | None:
        return await self._rounds.get_with_groups(round_id)

    async def get_group(self, group_id: UUID) -> Group | None:
        return await self._rounds.get_group(group_id)

    async def get_group_context(self, group_id: UUID) -> tuple[Group, Round, Tournament] | None:
        """A group with the round and tournament it belongs to, or None.

        Every group-scoped endpoint needs all three — the group to act on, the
        round for its status, and the tournament to authorise against — and the
        chain is three sequential lookups. Returning None for any missing link
        lets callers answer with a single 404 rather than leaking which step of
        the chain broke.
        """
        group = await self._rounds.get_group(group_id)
        if group is None:
            return None

        round_ = await self._rounds.get_by_id(group.round_id)
        if round_ is None:
            return None

        tournament = await self._tournaments.get_by_id(round_.tournament_id)
        if tournament is None:
            return None

        return group, round_, tournament

    async def list_for_tournament(self, tournament_id: UUID) -> Sequence[Round]:
        return await self._rounds.list_for_tournament(tournament_id)

    async def _field_for_draw(self, tournament: Tournament, round_number: int) -> list[UUID]:
        """Who is playing this round, in the order `build_groups` will cut.

        Round one is the whole field in registration order whatever the format —
        a knockout's first round *is* the field — and so is every later round of
        a round robin, shuffled. Only a knockout from round two narrows, to the
        players who won their group (ADR-012).

        Shuffling the survivors rather than carrying group order forward is
        deliberate. `build_groups` is order-preserving, so keeping the order would
        put group 1's winner against group 2's winner every time — a fixed bracket
        whose shape came from nothing but registration order surviving round one.
        Nothing here seeds, so that structure would carry no meaning while looking
        like it did.

        Raises:
            AwaitingAdjudication: If a group of the previous round never said who
                went through.
            KnockoutComplete: If one player is left — there is no round to draw.
        """
        if tournament.format is not TournamentFormat.KNOCKOUT or round_number == FIRST_ROUND:
            participants = await self._participants.list_for_tournament(tournament.id)
            # Registration order for round 1; shuffled thereafter.
            # list_for_tournament already sorts by created_at, so round 1 needs
            # no work at all.
            participant_ids = [participant.id for participant in participants]
            if round_number != FIRST_ROUND:
                random.shuffle(participant_ids)
            return participant_ids

        previous = await self._rounds.latest_for_tournament(tournament.id)
        if previous is None:  # pragma: no cover — DRAWABLE_FROM means one has finished
            raise DrawNotPossible("There is no previous round to take the winners from.")

        field = await self._advancement.field_for_next_round(previous)
        if field.undecided:
            groups = ", ".join(str(number) for number in field.undecided)
            raise AwaitingAdjudication(
                f"Round {previous.round_number} "
                f"group{'s' if len(field.undecided) > 1 else ''} {groups} had nothing to "
                "separate the players — level on points and strokes, and no hole won "
                "later. Say who goes through with POST /groups/{group_id}/advancement, "
                "then draw again."
            )
        if len(field.advancing) == 1:
            raise KnockoutComplete(await self._champion_message(field.advancing[0]))

        survivors = list(field.advancing)
        random.shuffle(survivors)
        return survivors

    async def _champion_message(self, participant_id: UUID) -> str:
        """The refusal that ends a bracket, naming the winner.

        Worth one extra read on the single request per event that reaches it:
        without it the draw falls through to `group_sizes(1)` and answers
        "Cannot form a group from a single player", which is technically correct
        and completely unreadable as "you have a champion".
        """
        champion = await self._participants.get_by_id(participant_id)
        name = champion.display_name if champion else "One player"
        return (
            f"{name} has won — everyone else is out, so there is no round left to draw. "
            'Finish the event with POST /tournaments/{id}/status {"status": '
            '"TOURNAMENT_COMPLETE"}.'
        )

    async def draw_round(
        self, tournament: Tournament, hole_numbers: Sequence[int] | None = None
    ) -> Round:
        """Draw the next round: split the field into groups and give each a loop.

        Round 1 is drawn in registration order, so people play with the mates they
        signed up alongside. Later rounds shuffle first, to mix the field up.

        `hole_numbers` narrows the draw to part of the course — holes 7, 8 and 9
        of a normal round, say. The tournament still points at the real course
        record; which holes were actually played is recorded per group in
        `group_holes`, so nothing has to invent a duplicate course to say "we
        played the back three". Omitted means the whole course, as before.

        The **shape** of the draw — how many to a group, and how the holes become
        loops — comes off the tournament row rather than this call, so every round
        of an event is drawn the same way without the organiser restating it. A
        shotgun (ADR-011) makes every hole in play a starting tee, so sixteen
        fourballs take tees 1-16 and the whole field tees off at once.

        On a **handicap** event two more things have to be true before a ball is
        struck, and both are checked here rather than at score entry (ADR-013):
        every hole in play needs a stroke index to deal shots by, and every player
        needs an allowance. Refusing at the draw is what keeps ADR-013's answer to
        ADR-007 honest — the failure lands while the organiser is still at a desk,
        not on the first tee with the field assembled.

        Raises:
            RoundNotDrawable: If the tournament isn't ready for a new round.
            DrawNotPossible: If it has no course, too few holes, too few players,
                or — on a handicap event — a hole with no stroke index or a player
                with no handicap.
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
        if hole_numbers is not None:
            holes = _select_holes(holes, hole_numbers)
            _check_selection(len(holes), tournament.loop_style)

        round_number = await self._rounds.next_round_number(tournament.id)
        participant_ids = await self._field_for_draw(tournament, round_number)

        if tournament.handicap_enabled:
            _require_stroke_indexes(holes)
            await self._require_handicaps(tournament, participant_ids)

        try:
            groups = build_groups(participant_ids, target=tournament.group_size)
            loops = plan_loops([hole.id for hole in holes], style=tournament.loop_style)
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

    async def _require_handicaps(
        self, tournament: Tournament, participant_ids: Sequence[UUID]
    ) -> None:
        """Refuse a handicap draw while anybody in the field has no allowance.

        **Not defaulted to zero.** A missing number almost always means "not
        entered yet", and zero is the hardest handicap there is — so guessing
        would silently penalise exactly the player nobody remembered to ask, and
        would do it invisibly, on a board that looked complete.
        """
        field = await self._participants.list_for_tournament(tournament.id)
        drawn = set(participant_ids)
        missing = sorted(
            player.display_name
            for player in field
            if player.id in drawn and player.playing_handicap is None
        )
        if missing:
            raise DrawNotPossible(
                "Handicaps are on for this event, so every player needs one. "
                f"{', '.join(missing)} {'has' if len(missing) == 1 else 'have'} "
                "none yet."
            )

    async def complete_round(self, tournament: Tournament, round_: Round) -> Round:
        """Finish a round, moving both it and its tournament.

        Raises:
            RoundNotInProgress: If this round isn't the one being played.
        """
        if round_.status is not RoundStatus.IN_PROGRESS:
            raise RoundNotInProgress(
                f"Round {round_.round_number} is {round_.status.value}, not in progress."
            )

        # Decide before closing, not lazily at the next draw: this is the moment
        # the round's scores stop changing, so the verdict records what the field
        # was told rather than what the code thinks later (ADR-012). A no-op on a
        # round robin. A group nothing could separate is left undecided on
        # purpose — the organiser has to be able to close the round while the
        # field walks in, and the refusal belongs at the next draw, where it
        # actually blocks something.
        await self._advancement.decide_round(tournament, round_)

        completed = await self._rounds.set_status(round_, RoundStatus.COMPLETE)
        await self._tournaments.set_status(tournament, TournamentStatus.ROUND_COMPLETE)
        return completed
