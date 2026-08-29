from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Player(Base, TimestampMixin):
    """A player profile. `id` mirrors Supabase auth.users.id — it is always supplied
    explicitly by the service layer from a verified JWT, never generated locally.
    """

    __tablename__ = "players"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # This player's own code, for bringing somebody to the platform. Every player
    # has one from the moment their profile exists — a code you have to go and
    # ask for is a code nobody shares.
    referral_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)

    # Who brought them, set once when the profile is created and never after.
    # Attribution only: nothing is awarded for it, which is deliberate while the
    # organiser fee is still Phase 3's to design.
    #
    # No cascade on the foreign key. Deleting a player who referred others should
    # fail loudly rather than quietly rewrite where those others came from.
    referred_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("players.id"), nullable=True, index=True
    )
