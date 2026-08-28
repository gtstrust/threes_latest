"""What an invitation looks like before you accept it.

One shape for both kinds of event, because an invitation is one idea: somebody
sent you a link and you need to know what it is before you tap the button. The
`kind` field is what tells the client where to land afterwards — a tournament and
a fun round are different screens even though they are the same table.

Modelled on `FunRoundPreview`, which established the rule this follows: enough to
recognise what you were invited to, and nothing about who else is playing. The
field stays behind `require_can_view`; you learn who is in it by being in it.
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel

from app.models.tournament import Tournament, TournamentKind, TournamentStatus


class JoinKind(str, Enum):
    """Which screen an accepted invitation leads to."""

    TOURNAMENT = "tournament"
    FUN_ROUND = "fun_round"


class JoinPreview(BaseModel):
    """An invitation, resolved from its code."""

    kind: JoinKind
    id: UUID
    name: str
    host_name: str
    player_count: int
    # Whether tapping the button would work, so the client can say why not rather
    # than offering an action that answers 409. False once registration closes,
    # and for a fun round whose single group is already full.
    can_join: bool
    # Present so a client can explain a closed invitation in the event's own
    # terms; the tournament vocabulary is ADR-003's, which a casual player never
    # sees because a fun round is read through /fun-rounds instead.
    status: TournamentStatus

    @classmethod
    def build(
        cls,
        tournament: Tournament,
        host_name: str,
        player_count: int,
        can_join: bool,
    ) -> "JoinPreview":
        return cls(
            kind=(
                JoinKind.FUN_ROUND
                if tournament.kind is TournamentKind.FUN_ROUND
                else JoinKind.TOURNAMENT
            ),
            id=tournament.id,
            name=tournament.name,
            host_name=host_name,
            player_count=player_count,
            can_join=can_join,
            status=tournament.status,
        )


class JoinCodeRead(BaseModel):
    """A freshly minted invitation, returned when the organiser regenerates one."""

    join_code: str
