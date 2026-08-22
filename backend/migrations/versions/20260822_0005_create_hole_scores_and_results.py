"""create hole scores and hole results

Revision ID: 20260822_0005
Revises: 20260822_0004
Create Date: 2026-08-22 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260822_0005"
down_revision: Union[str, None] = "20260822_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Lowercase labels, matching DecidedBy's *values* rather than its member names.
# app/models/score.py passes values_callable for the same reason: the stored
# label then reads the same as the API response and as ADR-007.
decided_by = sa.Enum("strokes", "closest_to_pin", "longest_drive", "no_winner", name="decided_by")


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
        "hole_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hole_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strokes", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hole_id"], ["holes.id"]),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["tournament_participants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "hole_id", "participant_id", name="uq_hole_scores_group_hole_participant"
        ),
        sa.CheckConstraint("strokes >= 1", name="ck_hole_scores_strokes_positive"),
        sa.CheckConstraint("points IN (0, 1)", name="ck_hole_scores_points_range"),
    )
    op.create_index(op.f("ix_hole_scores_group_id"), "hole_scores", ["group_id"], unique=False)
    op.create_index(op.f("ix_hole_scores_hole_id"), "hole_scores", ["hole_id"], unique=False)
    op.create_index(
        op.f("ix_hole_scores_participant_id"), "hole_scores", ["participant_id"], unique=False
    )

    op.create_table(
        "hole_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hole_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("winner_participant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_by", decided_by, nullable=False),
        sa.Column("closest_to_pin_participant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("longest_drive_participant_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hole_id"], ["holes.id"]),
        sa.ForeignKeyConstraint(
            ["winner_participant_id"], ["tournament_participants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["closest_to_pin_participant_id"],
            ["tournament_participants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["longest_drive_participant_id"],
            ["tournament_participants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "hole_id", name="uq_hole_results_group_hole"),
        # ADR-007: a tie-break is recorded only when it actually decided the hole.
        sa.CheckConstraint(
            "closest_to_pin_participant_id IS NULL OR decided_by = 'closest_to_pin'",
            name="ck_hole_results_ctp_decided",
        ),
        sa.CheckConstraint(
            "longest_drive_participant_id IS NULL OR decided_by = 'longest_drive'",
            name="ck_hole_results_longest_drive_decided",
        ),
        # Holes are never halved: exactly one winner, or none at all.
        sa.CheckConstraint(
            "(winner_participant_id IS NULL) = (decided_by = 'no_winner')",
            name="ck_hole_results_winner_matches_decided_by",
        ),
    )
    op.create_index(op.f("ix_hole_results_group_id"), "hole_results", ["group_id"], unique=False)
    op.create_index(op.f("ix_hole_results_hole_id"), "hole_results", ["hole_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_hole_results_hole_id"), table_name="hole_results")
    op.drop_index(op.f("ix_hole_results_group_id"), table_name="hole_results")
    op.drop_table("hole_results")

    op.drop_index(op.f("ix_hole_scores_participant_id"), table_name="hole_scores")
    op.drop_index(op.f("ix_hole_scores_hole_id"), table_name="hole_scores")
    op.drop_index(op.f("ix_hole_scores_group_id"), table_name="hole_scores")
    op.drop_table("hole_scores")

    # drop_table leaves the enum type behind, so a later upgrade would fail with
    # "type already exists". Alembic does not clean these up for us.
    decided_by.drop(op.get_bind(), checkfirst=False)
