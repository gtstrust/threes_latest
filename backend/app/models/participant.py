from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TournamentParticipant(Base, TimestampMixin):
    """Someone playing in a tournament, whether or not they have an account.

    This is the identity everything downstream points at — groups and scores
    foreign-key to a *participant*, never directly to a player. That's what lets
    a Virtual Player (someone without a device, scored by a groupmate) be grouped
    and scored exactly like anyone else.
    """

    __tablename__ = "tournament_participants"
    __table_args__ = (
        # Stops one player registering twice. Postgres treats NULLs as distinct,
        # so this still allows any number of virtual players in one tournament —
        # no partial index needed.
        UniqueConstraint("tournament_id", "player_id", name="uq_participants_tournament_player"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    tournament_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # NULL means a virtual player: no account, no device, scored by a groupmate.
    player_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("players.id"),
        nullable=True,
        index=True,
    )

    # A snapshot, not a lookup. Virtual players have no profile to read a name
    # from, and for real players this keeps leaderboards stable even if they
    # rename themselves afterwards.
    display_name: Mapped[str] = mapped_column(String, nullable=False)

    @property
    def is_virtual(self) -> bool:
        return self.player_id is None
