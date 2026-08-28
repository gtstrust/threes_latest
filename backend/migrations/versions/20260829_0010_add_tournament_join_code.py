"""give every tournament a short join code

Revision ID: 20260829_0010
Revises: 20260828_0009
Create Date: 2026-08-29 10:00:00.000000

Joining used to mean knowing a tournament's UUID, which cannot be revoked, cannot
be read aloud, and is the same value the app routes on. This column is the
invitation instead: short, unique, and regeneratable when a printed sign outlives
its event.

On the shared table, so a Fun Round gets one too — that is what lets a single
/join/{code} route serve both kinds.

Added nullable, backfilled, then made NOT NULL with its unique index, because
existing rows have no code and a NOT NULL column with no default cannot be added
to a populated table.

The generator is deliberately **inlined rather than imported from `app/`**. A
migration has to keep producing the same result long after the application module
has moved or changed its alphabet; importing it would couple this fixed point in
history to code that is free to evolve.
"""

import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260829_0010"
down_revision: Union[str, None] = "20260828_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Kept in step with app/services/join_code.py at the time of writing; see above
# for why it is copied rather than imported.
ALPHABET = "23456789BCDFGHJKMNPQRSTVWXYZ"
PREFIX = "THR-"
CODE_LENGTH = 5


def _code() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("join_code", sa.String(length=16), nullable=True))

    # One code per existing row, retried on the off-chance two draws collide
    # within this backfill — the unique index does not exist yet to catch it.
    bind = op.get_bind()
    ids = bind.execute(sa.text("SELECT id FROM tournaments")).scalars().all()
    used: set[str] = set()
    for tournament_id in ids:
        code = _code()
        while code in used:
            code = _code()
        used.add(code)
        bind.execute(
            sa.text("UPDATE tournaments SET join_code = :code WHERE id = :id"),
            {"code": code, "id": tournament_id},
        )

    op.alter_column("tournaments", "join_code", nullable=False)
    op.create_unique_constraint("uq_tournaments_join_code", "tournaments", ["join_code"])


def downgrade() -> None:
    op.drop_constraint("uq_tournaments_join_code", "tournaments", type_="unique")
    op.drop_column("tournaments", "join_code")
