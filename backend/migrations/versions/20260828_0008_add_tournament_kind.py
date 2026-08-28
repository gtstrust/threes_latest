"""add kind discriminator to tournaments

Revision ID: 20260828_0008
Revises: 20260824_0007
Create Date: 2026-08-28 10:00:00.000000

A Fun Round (Phase 2) is a casual, self-run round that reuses the entire
scoring/grouping/leaderboard stack, so it is stored as a `tournaments` row rather
than in a parallel set of tables. This column is the discriminator that keeps the
two apart in listings and in tournament-only concerns.

Every existing row is a real tournament, so the column is NOT NULL with a server
default of TOURNAMENT — the default also lets the ORM insert without naming it.
No new table is created, so the hardcoded RLS list in migration 0006 is unchanged.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260828_0008"
down_revision: Union[str, None] = "20260824_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

tournament_kind = sa.Enum("TOURNAMENT", "FUN_ROUND", name="tournament_kind")


def upgrade() -> None:
    bind = op.get_bind()
    tournament_kind.create(bind, checkfirst=True)
    op.add_column(
        "tournaments",
        sa.Column(
            "kind",
            tournament_kind,
            nullable=False,
            server_default="TOURNAMENT",
        ),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "kind")
    # drop_column leaves the enum type behind — Alembic does not clean these up.
    tournament_kind.drop(op.get_bind(), checkfirst=False)
