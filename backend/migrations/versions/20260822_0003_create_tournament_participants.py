"""create tournament participants

Revision ID: 20260822_0003
Revises: 20260822_0002
Create Date: 2026-08-22 13:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260822_0003"
down_revision: Union[str, None] = "20260822_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tournament_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Nullable: NULL means a virtual player — no account, no device, scored
        # by someone else in their group.
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
        # Stops one player registering twice. Postgres treats NULLs as distinct,
        # so any number of virtual players is still allowed without a partial index.
        sa.UniqueConstraint("tournament_id", "player_id", name="uq_participants_tournament_player"),
    )
    op.create_index(
        op.f("ix_tournament_participants_tournament_id"),
        "tournament_participants",
        ["tournament_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tournament_participants_player_id"),
        "tournament_participants",
        ["player_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tournament_participants_player_id"), table_name="tournament_participants"
    )
    op.drop_index(
        op.f("ix_tournament_participants_tournament_id"), table_name="tournament_participants"
    )
    op.drop_table("tournament_participants")
