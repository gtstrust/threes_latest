"""create tournaments table

Revision ID: 20260822_0001
Revises: 20260101_0000
Create Date: 2026-08-22 11:06:03.898783

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260822_0001"
down_revision: Union[str, None] = "20260101_0000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

tournament_status = sa.Enum(
    "CREATED",
    "REGISTRATION_OPEN",
    "REGISTRATION_CLOSED",
    "ROUND_IN_PROGRESS",
    "ROUND_COMPLETE",
    "TOURNAMENT_COMPLETE",
    name="tournament_status",
)
tournament_format = sa.Enum("ROUND_ROBIN", "KNOCKOUT", name="tournament_format")


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("organiser_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", tournament_status, nullable=False),
        sa.Column("format", tournament_format, nullable=False),
        sa.Column("course_name", sa.String(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # No ondelete: deleting a player who organised a tournament should fail
        # rather than silently destroy the event.
        sa.ForeignKeyConstraint(["organiser_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tournaments_organiser_id"), "tournaments", ["organiser_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tournaments_organiser_id"), table_name="tournaments")
    op.drop_table("tournaments")
    # drop_table leaves the enum types behind, so a later upgrade would fail with
    # "type already exists". Alembic does not clean these up for us.
    tournament_status.drop(op.get_bind(), checkfirst=False)
    tournament_format.drop(op.get_bind(), checkfirst=False)
