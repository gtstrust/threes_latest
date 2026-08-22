from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    ParticipantServiceDep,
    RoundServiceDep,
    ScoreEntryServiceDep,
    require_can_view,
    require_group_member,
)
from app.models.round import Group, Round
from app.models.tournament import Tournament
from app.schemas.score import GroupCardRead, HoleResultRead, HoleScoreRead, HoleScoreSubmit
from app.services.score_entry import (
    HoleNotInLoop,
    IncompleteCard,
    InvalidScores,
    ScoredHole,
    ScoringClosed,
)

router = APIRouter(tags=["scores"])


async def _group_context(
    group_id: UUID, rounds: RoundServiceDep
) -> tuple[Group, Round, Tournament]:
    context = await rounds.get_group_context(group_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return context


def _to_read(scored: ScoredHole) -> HoleResultRead:
    return HoleResultRead(
        hole_id=scored.result.hole_id,
        winner_participant_id=scored.result.winner_participant_id,
        decided_by=scored.result.decided_by,
        closest_to_pin_participant_id=scored.result.closest_to_pin_participant_id,
        longest_drive_participant_id=scored.result.longest_drive_participant_id,
        scores=[HoleScoreRead.model_validate(score) for score in scored.scores],
        tied_participants=list(scored.tied_participants),
        created_at=scored.result.created_at,
        updated_at=scored.result.updated_at,
    )


@router.post("/groups/{group_id}/holes/{hole_id}/scores", response_model=HoleResultRead)
async def submit_hole_scores(
    group_id: UUID,
    hole_id: UUID,
    payload: HoleScoreSubmit,
    current_user: CurrentUserDep,
    rounds: RoundServiceDep,
    participants: ParticipantServiceDep,
    scores: ScoreEntryServiceDep,
) -> HoleResultRead:
    """Enter the group's strokes for one hole, and get back who won it.

    Submitting the same hole again replaces what was there — that is both how a
    mis-keyed number is fixed and how a tie-break answer arrives. If the strokes
    tie and nothing separates the players yet, the response names them in
    `tied_participants`: ask those players who was closest to the pin, then who
    hit the longest drive on the fairway, and post the hole again with the answer.
    """
    group, round_, tournament = await _group_context(group_id, rounds)
    await require_group_member(group, tournament, current_user, participants)

    try:
        scored = await scores.submit_hole(
            group=group,
            round_=round_,
            hole_id=hole_id,
            strokes=payload.strokes,
            closest_to_pin=payload.closest_to_pin,
            longest_drive=payload.longest_drive,
        )
    except HoleNotInLoop as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ScoringClosed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (IncompleteCard, InvalidScores) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return _to_read(scored)


@router.get("/groups/{group_id}/scores", response_model=GroupCardRead)
async def read_group_card(
    group_id: UUID,
    current_user: CurrentUserDep,
    rounds: RoundServiceDep,
    participants: ParticipantServiceDep,
    scores: ScoreEntryServiceDep,
) -> GroupCardRead:
    """The group's card: every hole of its loop that has been scored so far."""
    group, _round, tournament = await _group_context(group_id, rounds)
    await require_can_view(tournament, current_user, participants)

    card = await scores.get_card(group)
    return GroupCardRead(group_id=group.id, holes=[_to_read(scored) for scored in card])
