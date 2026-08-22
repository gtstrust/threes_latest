"""create rounds, groups, members and group holes

Revision ID: 20260822_0004
Revises: 20260822_0003
Create Date: 2026-08-22 14:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260822_0004"
down_revision: Union[str, None] = "20260822_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

round_status = sa.Enum("PENDING", "IN_PROGRESS", "COMPLETE", name="round_status")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "rounds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tournament_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("status", round_status, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["tournament_id"], ["tournaments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tournament_id", "round_number", name="uq_rounds_tournament_number"),
        sa.CheckConstraint("round_number >= 1", name="ck_rounds_number_positive"),
    )
    op.create_index(op.f("ix_rounds_tournament_id"), "rounds", ["tournament_id"], unique=False)

    op.create_table(
        "groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_number", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "group_number", name="uq_groups_round_number"),
        sa.CheckConstraint("group_number >= 1", name="ck_groups_number_positive"),
    )
    op.create_index(op.f("ix_groups_round_id"), "groups", ["round_id"], unique=False)

    op.create_table(
        "group_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        # Cascade so deleting a tournament still works: participants cascade from
        # the tournament, and a restricting FK here would block that.
        sa.ForeignKeyConstraint(
            ["participant_id"], ["tournament_participants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "participant_id", name="uq_group_members_group_participant"
        ),
    )
    op.create_index(op.f("ix_group_members_group_id"), "group_members", ["group_id"], unique=False)
    op.create_index(
        op.f("ix_group_members_participant_id"), "group_members", ["participant_id"], unique=False
    )

    op.create_table(
        "group_holes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hole_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hole_id"], ["holes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "hole_id", name="uq_group_holes_group_hole"),
        sa.UniqueConstraint("group_id", "sequence", name="uq_group_holes_group_sequence"),
        sa.CheckConstraint("sequence BETWEEN 1 AND 3", name="ck_group_holes_sequence_range"),
    )
    op.create_index(op.f("ix_group_holes_group_id"), "group_holes", ["group_id"], unique=False)
    op.create_index(op.f("ix_group_holes_hole_id"), "group_holes", ["hole_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_group_holes_hole_id"), table_name="group_holes")
    op.drop_index(op.f("ix_group_holes_group_id"), table_name="group_holes")
    op.drop_table("group_holes")

    op.drop_index(op.f("ix_group_members_participant_id"), table_name="group_members")
    op.drop_index(op.f("ix_group_members_group_id"), table_name="group_members")
    op.drop_table("group_members")

    op.drop_index(op.f("ix_groups_round_id"), table_name="groups")
    op.drop_table("groups")

    op.drop_index(op.f("ix_rounds_tournament_id"), table_name="rounds")
    op.drop_table("rounds")
    # drop_table leaves the enum type behind, so a later upgrade would fail with
    # "type already exists". Alembic does not clean these up for us.
    round_status.drop(op.get_bind(), checkfirst=False)
