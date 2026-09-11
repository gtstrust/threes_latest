"""add group size and loop style to tournaments

Revision ID: 20260910_0014
Revises: 20260829_0013
Create Date: 2026-09-10 10:00:00.000000

How an event's draw is shaped, per ADR-004 (amended) and ADR-011. `group_size` is
the target the draw divides by — three, the format, unless an organiser chooses
fourballs. `loop_style` is how the holes in play are cut into loops: BLOCKS, the
disjoint triples that existed before this, or SHOTGUN, one loop per starting tee.

The two travel together because they are one decision. A real shotgun needs a tee
per group and a course has eighteen: sixty-four players in threes is twenty-one
groups and does not fit, while in fourballs it is sixteen and does.

Every existing row was drawn as threes in blocks, so both columns are NOT NULL
with server defaults saying exactly that — the defaults also let the ORM insert
without naming them. The check constraint holds the format's floor and ceiling in
the database rather than only in the schema.

No new table is created, so the hardcoded RLS list in migration 0006 is unchanged.
No new model either — these are columns on an already-registered one, so
`app/models/__init__.py` needs no edit.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260910_0014"
down_revision: Union[str, None] = "20260829_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

loop_style = sa.Enum("BLOCKS", "SHOTGUN", name="loop_style")


def upgrade() -> None:
    bind = op.get_bind()
    loop_style.create(bind, checkfirst=True)
    op.add_column(
        "tournaments",
        sa.Column(
            "group_size",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "tournaments",
        sa.Column(
            "loop_style",
            loop_style,
            nullable=False,
            server_default="BLOCKS",
        ),
    )
    op.create_check_constraint(
        "ck_tournaments_group_size",
        "tournaments",
        "group_size BETWEEN 3 AND 4",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tournaments_group_size", "tournaments", type_="check")
    op.drop_column("tournaments", "loop_style")
    op.drop_column("tournaments", "group_size")
    # drop_column leaves the enum type behind — Alembic does not clean these up.
    loop_style.drop(op.get_bind(), checkfirst=False)
