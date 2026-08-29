"""give every player a referral code, and record who brought them

Revision ID: 20260829_0012
Revises: 20260829_0011
Create Date: 2026-08-29 17:00:00.000000

Attribution, not rewards. `referred_by` answers "is word of mouth working?",
which is a question worth being able to ask before there is any revenue to fund
a rewards scheme — and a scheme invented now would collide with the organiser fee
that Phase 3 has yet to design.

`referral_code` is added nullable, backfilled and then made NOT NULL and unique,
the same shape migration 0010 used for join codes and for the same reason: a NOT
NULL column with no default cannot be added to a populated table.

`referred_by` is a nullable self-reference with no cascade. Deleting a player who
referred others should fail loudly rather than quietly rewrite where those others
came from.
"""

import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260829_0012"
down_revision: Union[str, None] = "20260829_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Inlined rather than imported from app/services/join_code.py, exactly as 0010
# does: a migration has to keep producing the same result long after the module
# has moved or changed its alphabet.
ALPHABET = "23456789BCDFGHJKMNPQRSTVWXYZ"
PREFIX = "MATE-"
CODE_LENGTH = 5


def _code() -> str:
    return PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def upgrade() -> None:
    op.add_column("players", sa.Column("referral_code", sa.String(length=16), nullable=True))
    op.add_column(
        "players",
        sa.Column("referred_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )

    bind = op.get_bind()
    ids = bind.execute(sa.text("SELECT id FROM players")).scalars().all()
    used: set[str] = set()
    for player_id in ids:
        code = _code()
        while code in used:
            code = _code()
        used.add(code)
        bind.execute(
            sa.text("UPDATE players SET referral_code = :code WHERE id = :id"),
            {"code": code, "id": player_id},
        )

    op.alter_column("players", "referral_code", nullable=False)
    op.create_unique_constraint("uq_players_referral_code", "players", ["referral_code"])
    op.create_foreign_key("fk_players_referred_by", "players", "players", ["referred_by"], ["id"])
    op.create_index("ix_players_referred_by", "players", ["referred_by"])


def downgrade() -> None:
    op.drop_index("ix_players_referred_by", table_name="players")
    op.drop_constraint("fk_players_referred_by", "players", type_="foreignkey")
    op.drop_constraint("uq_players_referral_code", "players", type_="unique")
    op.drop_column("players", "referred_by")
    op.drop_column("players", "referral_code")
