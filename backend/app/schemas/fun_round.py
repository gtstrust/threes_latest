from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.course import MAX_HOLE_NUMBER, MIN_HOLE_NUMBER
from app.models.tournament import Tournament, TournamentStatus
from app.schemas.participant import ParticipantRead
from app.schemas.round import RoundWithGroups
from app.services.grouping import HOLES_PER_LOOP


class FunRoundStatus(str, Enum):
    """The three states a fun round shows the client.

    A fun round runs on the full ADR-003 tournament state machine underneath, but a
    casual player has no use for that vocabulary — they see a lobby they're filling,
    a round they're playing, or a finished card. This collapses the six internal
    states onto those three.
    """

    LOBBY = "lobby"
    PLAYING = "playing"
    FINISHED = "finished"


def _to_fun_round_status(status: TournamentStatus) -> FunRoundStatus:
    if status is TournamentStatus.ROUND_IN_PROGRESS:
        return FunRoundStatus.PLAYING
    if status in (TournamentStatus.ROUND_COMPLETE, TournamentStatus.TOURNAMENT_COMPLETE):
        return FunRoundStatus.FINISHED
    return FunRoundStatus.LOBBY


def validate_one_loop(holes: list[int] | None) -> list[int] | None:
    """Check a hole selection is exactly one playable loop.

    Shared by the two places a fun round can be given its holes — at setup, with
    the course, and as an override at start — so the two can never disagree about
    what a valid selection is.
    """
    if holes is None:
        return None

    out_of_range = sorted({n for n in holes if not MIN_HOLE_NUMBER <= n <= MAX_HOLE_NUMBER})
    if out_of_range:
        raise ValueError(
            f"Hole numbers must be between {MIN_HOLE_NUMBER} and "
            f"{MAX_HOLE_NUMBER}; got {out_of_range}"
        )

    duplicates = sorted({n for n in holes if holes.count(n) > 1})
    if duplicates:
        raise ValueError(f"Duplicate hole numbers in selection: {duplicates}")

    if len(holes) != HOLES_PER_LOOP:
        raise ValueError(
            f"A fun round is one {HOLES_PER_LOOP}-hole loop, so pick exactly "
            f"{HOLES_PER_LOOP} holes; got {len(holes)}."
        )
    return holes


class FunRoundCreate(BaseModel):
    """Start a fun round. The course can be chosen now or left for later."""

    name: str = Field(min_length=1, max_length=200)
    course_id: UUID | None = None
    # Which three holes the group will play, chosen here rather than at start:
    # the loop is part of deciding where you're playing, and leaving it until the
    # tee means the host discovers a course has no usable holes with everyone
    # already standing on it. Verified against the course now, drawn later.
    hole_numbers: list[int] | None = Field(
        default=None,
        description="Exactly three holes, e.g. [7, 8, 9]. Omit to use the whole course.",
    )
    # The host's name in this round, falling back to their profile name then email,
    # so a fun round can be started with just a name.
    display_name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("hole_numbers")
    @classmethod
    def _one_loop(cls, holes: list[int] | None) -> list[int] | None:
        return validate_one_loop(holes)


class FunRoundStart(BaseModel):
    """Override the holes chosen at setup. Optional — omit to play what was chosen."""

    hole_numbers: list[int] | None = Field(
        default=None,
        description=(
            "Exactly three holes, e.g. [7, 8, 9]. Omit to use the selection made "
            "when the round was set up, or the whole course if none was made."
        ),
    )

    @field_validator("hole_numbers")
    @classmethod
    def _one_loop(cls, holes: list[int] | None) -> list[int] | None:
        return validate_one_loop(holes)


class FunRoundRead(BaseModel):
    id: UUID
    name: str
    host_id: UUID
    course_id: UUID | None
    # The loop chosen at setup, so the lobby can say which holes are being played
    # instead of leaving the host to find out at the first tee. None means none was
    # chosen and the draw will take the first loop of the course.
    hole_numbers: list[int] | None
    status: FunRoundStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, fun_round: Tournament) -> "FunRoundRead":
        """Build from a `tournaments` row, renaming organiser→host and collapsing status."""
        return cls(
            id=fun_round.id,
            name=fun_round.name,
            host_id=fun_round.organiser_id,
            course_id=fun_round.course_id,
            hole_numbers=fun_round.hole_numbers,
            status=_to_fun_round_status(fun_round.status),
            created_at=fun_round.created_at,
            updated_at=fun_round.updated_at,
        )


class FunRoundDetail(FunRoundRead):
    """A fun round with its field and — once started — its drawn group and loop."""

    model_config = ConfigDict(from_attributes=True)

    participants: list[ParticipantRead]
    round: RoundWithGroups | None

    @classmethod
    def build(
        cls,
        fun_round: Tournament,
        participants: list[ParticipantRead],
        round_: RoundWithGroups | None,
    ) -> "FunRoundDetail":
        base = FunRoundRead.from_model(fun_round)
        return cls(**base.model_dump(), participants=participants, round=round_)


class FunRoundPreview(BaseModel):
    """What someone who was sent the link sees before they join.

    A fun round is invited by sharing its URL, so the round has to be legible to
    someone who is not yet in the field — otherwise the invite refuses the very
    people it was sent to. What it deliberately does *not* carry is the field
    itself or the draw: enough to recognise the round you were invited to and
    decide to join, and nothing about who else is playing, which stays behind
    `require_can_view` on the full read.
    """

    id: UUID
    name: str
    host_name: str
    player_count: int
    is_full: bool
    status: FunRoundStatus

    @classmethod
    def build(
        cls,
        fun_round: Tournament,
        host_name: str,
        player_count: int,
        is_full: bool,
    ) -> "FunRoundPreview":
        return cls(
            id=fun_round.id,
            name=fun_round.name,
            host_name=host_name,
            player_count=player_count,
            is_full=is_full,
            status=_to_fun_round_status(fun_round.status),
        )
