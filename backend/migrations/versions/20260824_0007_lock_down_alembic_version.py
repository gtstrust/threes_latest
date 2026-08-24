"""revoke the PostgREST roles' access to alembic_version

Revision ID: 20260824_0007
Revises: 20260824_0006
Create Date: 2026-08-24 14:40:00.000000

The previous migration enabled RLS on every table this app owns, but Alembic's
own bookkeeping table is not one of them — it is created by Alembic, not by our
models, so it was not in the list and was left with Supabase's default grants.

That was demonstrably not harmless: with the publishable key the frontend ships,
`anon` could both read *and* **UPDATE** `alembic_version`. Rewriting the version
pointer does not touch a single row of tournament data, which is exactly why it
is easy to miss — it silently breaks every future migration instead.

RLS alone would not be enough here. RLS restricts *rows*, and the fix wanted is
the absence of any access at all, so the grants themselves are revoked. RLS is
enabled as well, so that a future default-privileges grant cannot quietly undo
this.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260824_0007"
down_revision: Union[str, None] = "20260824_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Supabase's exposed roles. On a plain Postgres these do not exist, so every
# statement is guarded — this migration has to run locally too.
POSTGREST_ROLES: tuple[str, ...] = ("anon", "authenticated")


def upgrade() -> None:
    for role in POSTGREST_ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL ON TABLE public.alembic_version FROM {role};
                END IF;
            END
            $$;
            """
        )
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY")
    for role in POSTGREST_ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    GRANT SELECT ON TABLE public.alembic_version TO {role};
                END IF;
            END
            $$;
            """
        )
