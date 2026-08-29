"""let an organiser cap the field

Revision ID: 20260829_0011
Revises: 20260829_0010
Create Date: 2026-08-29 15:00:00.000000

Now that a join link lets people arrive without being invited one at a time, an
organiser needs a way to stop the field growing past the day they actually
booked — tee times, carts and catering are all bought for a number.

Nullable, and NULL means no cap, which is what every existing event has and what
an organiser who never thinks about it keeps. A cap is opt-in; a default would be
this migration inventing a limit nobody asked for.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260829_0011"
down_revision: Union[str, None] = "20260829_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("max_players", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tournaments", "max_players")
