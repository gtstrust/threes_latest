"""add advancement to groups

Revision ID: 20260911_0015
Revises: 20260910_0014
Create Date: 2026-09-11 12:00:00.000000

Who went through from each group of a knockout round, and which level of the
ADR-012 cascade named them. Stored rather than recomputed for ADR-009's reason: a
bracket recalculated on demand records nothing — it would only ever show what
today's code thinks, not who the field was told had gone through.

Both columns are nullable **with no server default**, unlike 0008 and 0014,
because NULL is the meaningful answer here rather than a backfill problem. Every
existing group belongs to a round robin, where nobody advances, and a knockout
group the cascade could not settle stays NULL until the organiser adjudicates.
The check constraint holds the pairing: a level without a player, or a player
without a level, is a half-written verdict.

`tournament_format` already carries KNOCKOUT (migration 0001), so the format
itself needs no migration — this is the only schema change knockout requires.

No new table is created, so the hardcoded RLS list in migration 0006 is
unchanged. No new model either — these are columns on an already-registered one,
so `app/models/__init__.py` needs no edit.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260911_0015"
down_revision: Union[str, None] = "20260910_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Lowercase labels, matching AdvancedBy's *values* rather than its member names,
# for the same reason `decided_by` does: the stored label then reads the same as
# the API response and as ADR-012.
advanced_by = sa.Enum("points", "strokes", "countback", "organiser", name="advanced_by")


def upgrade() -> None:
    advanced_by.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "groups",
        sa.Column("advancing_participant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("groups", sa.Column("advanced_by", advanced_by, nullable=True))
    op.create_foreign_key(
        "fk_groups_advancing_participant",
        "groups",
        "tournament_participants",
        ["advancing_participant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_groups_advancement_pairs",
        "groups",
        "(advancing_participant_id IS NULL) = (advanced_by IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_groups_advancement_pairs", "groups", type_="check")
    op.drop_constraint("fk_groups_advancing_participant", "groups", type_="foreignkey")
    op.drop_column("groups", "advanced_by")
    op.drop_column("groups", "advancing_participant_id")
    # drop_column leaves the enum type behind — Alembic does not clean these up.
    advanced_by.drop(op.get_bind(), checkfirst=False)
