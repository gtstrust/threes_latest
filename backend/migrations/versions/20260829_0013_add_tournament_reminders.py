"""record that a reminder was sent

Revision ID: 20260829_0013
Revises: 20260829_0012
Create Date: 2026-08-29 19:00:00.000000

A table rather than a column on `tournaments`, for two reasons. The scheduled
sweep has to know whether it has already handled an event, and "already sent" is
a fact about one *kind* of reminder rather than about the event — an organiser
pressing the button must not cancel the day-before mail, and vice versa. And the
organiser's screen wants "last sent two hours ago", which needs a time.

No updated_at: a send is an event that happened, not a row that changes.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260829_0013"
down_revision: Union[str, None] = "20260829_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Two objects for one type, deliberately. `sa.Enum` knows how to CREATE TYPE and
# is used for exactly that; the column then references the type with
# `create_type=False`, because `create_table` would otherwise emit a second
# CREATE TYPE and fail with "type reminder_kind already exists".
reminder_kind = sa.Enum("UPCOMING", "MANUAL", name="reminder_kind")
reminder_kind_column = postgresql.ENUM(
    "UPCOMING", "MANUAL", name="reminder_kind", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    reminder_kind.create(bind, checkfirst=True)

    op.create_table(
        "tournament_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tournament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tournaments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", reminder_kind_column, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recipient_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_tournament_reminders_tournament_id", "tournament_reminders", ["tournament_id"]
    )

    # New table, so it needs the same blanket deny migration 0006 applies to every
    # other one: Supabase serves `public` to the internet through PostgREST, and a
    # table created by Alembic has RLS off and inherits grants for anon. No
    # policies — the app connects as the owner and bypasses RLS untouched.
    op.execute("ALTER TABLE tournament_reminders ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_tournament_reminders_tournament_id", table_name="tournament_reminders")
    op.drop_table("tournament_reminders")
    # drop_table leaves the enum type behind — Alembic does not clean these up.
    reminder_kind.drop(op.get_bind(), checkfirst=False)
