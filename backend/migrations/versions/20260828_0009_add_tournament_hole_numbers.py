"""record the holes chosen at setup on a tournament

Revision ID: 20260828_0009
Revises: 20260828_0008
Create Date: 2026-08-28 14:00:00.000000

A Fun Round's host picks which three holes the group plays when they pick the
course, but the draw that consumes the choice happens later, at start — a separate
request, often a separate session. The choice therefore has to be stored, and one
nullable array column is less than a settings table for a three-integer answer.

Nullable rather than defaulted: NULL means "not chosen", which for a fun round is
"use the whole course" and for a tournament is the normal case — tournaments pass
their selection at draw time instead and leave this alone.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260828_0009"
down_revision: Union[str, None] = "20260828_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("hole_numbers", sa.ARRAY(sa.Integer()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "hole_numbers")
