"""deny-all row level security on every table

Revision ID: 20260824_0006
Revises: 20260822_0005
Create Date: 2026-08-24 14:10:00.000000

Supabase exposes the `public` schema through PostgREST, and the key that reaches
it is the publishable one the frontend ships to every browser. A table created by
Alembic has RLS **off**, so on connecting this app's database to Supabase all
eleven tables would be readable — and writable — by anyone who opened the site
and read its JavaScript.

Enabling RLS with **no policies** closes that: PostgREST, which connects as
`anon` or `authenticated`, matches no policy and sees nothing. The backend
connects as the tables' owner and so bypasses RLS, which is why nothing in the
app changes.

This is not the RLS that ADR-010 rejected. That was a *policy* restating
`require_can_view` in SQL — a second copy of an authorization rule, free to drift
from the Python one. A blanket deny encodes no rule and duplicates nothing:
authorization stays entirely in FastAPI (ADR-001), and this only stops the
database answering questions the app was never meant to be asked.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260824_0006"
down_revision: Union[str, None] = "20260822_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Spelled out rather than read from Base.metadata: a migration is a record of
# what was done to a database on a date, and one that consults today's models
# would silently change meaning as the models do.
TABLES: tuple[str, ...] = (
    "courses",
    "group_holes",
    "group_members",
    "groups",
    "hole_results",
    "hole_scores",
    "holes",
    "players",
    "rounds",
    "tournament_participants",
    "tournaments",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
