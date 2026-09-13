"""add handicaps: the event flag, the per-participant allowance, the shots dealt

Revision ID: 20260913_0016
Revises: 20260911_0015
Create Date: 2026-09-13 12:00:00.000000

ADR-013. A playing handicap is pro-rated to the three-hole loop, dealt to the
loop's holes hardest-first by `stroke_index`, and ADR-007's cascade then runs
unchanged on net strokes. Three columns carry all of it.

`tournaments.handicap_enabled` is the per-event opt-in, non-null with a server
default of false — the same shape as `group_size` and `loop_style`, so the ORM
inserts without naming it and every existing row reads as scratch.

`tournament_participants.playing_handicap` is nullable and per event: an
allowance differs between events, and a Virtual Player has no `players` row to
carry one. 0-54 is the WHS range. Plus handicaps are deliberately out of scope —
a +2 pro-rates to zero shots over three holes, so the sign would never change a
result.

`hole_scores.strokes_received` holds the shots that player got on that hole, and
is the reason net is never stored: net is `strokes - strokes_received`, exact by
arithmetic, and a second column would be free to disagree with the first — the
failure ADR-009 already warns about across its two tables. The allocation itself
*is* stored rather than recomputed, for ADR-009's reason verbatim: an audit trail
recalculated on demand would only show what today's code thinks, not what the
group was told on the day.

**It defaults to 0, and that is the proof nothing moved.** Every existing row, and
every row of every scratch event after this, carries zero — so `net_strokes`
equals `strokes` and the leaderboard and the knockout cascade are provably the
ones they were. The same device as `rounds_survived = 0` for a round robin.

No new table, so the hardcoded RLS list in migration 0006 is unchanged. No new
model either — these are columns on already-registered ones, so
`app/models/__init__.py` needs no edit.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260913_0016"
down_revision: Union[str, None] = "20260911_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("handicap_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tournament_participants",
        sa.Column("playing_handicap", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_participants_playing_handicap_range",
        "tournament_participants",
        "playing_handicap IS NULL OR playing_handicap BETWEEN 0 AND 54",
    )
    op.add_column(
        "hole_scores",
        sa.Column("strokes_received", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_hole_scores_strokes_received_positive",
        "hole_scores",
        "strokes_received >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_hole_scores_strokes_received_positive", "hole_scores", type_="check"
    )
    op.drop_column("hole_scores", "strokes_received")
    op.drop_constraint(
        "ck_participants_playing_handicap_range", "tournament_participants", type_="check"
    )
    op.drop_column("tournament_participants", "playing_handicap")
    op.drop_column("tournaments", "handicap_enabled")
