"""create courses and holes, link tournaments to a course

Revision ID: 20260822_0002
Revises: 20260822_0001
Create Date: 2026-08-22 12:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260822_0002"
down_revision: Union[str, None] = "20260822_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["created_by"], ["players.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_courses_created_by"), "courses", ["created_by"], unique=False)
    # Case-insensitive, so "Royal Melbourne" and "royal melbourne" can't both exist.
    op.create_index("uq_courses_name_lower", "courses", [sa.text("lower(name)")], unique=True)

    op.create_table(
        "holes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hole_number", sa.Integer(), nullable=False),
        sa.Column("par", sa.Integer(), nullable=True),
        sa.Column("stroke_index", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "hole_number", name="uq_holes_course_hole_number"),
        sa.CheckConstraint("hole_number BETWEEN 1 AND 18", name="ck_holes_hole_number_range"),
        sa.CheckConstraint("par IS NULL OR par BETWEEN 3 AND 6", name="ck_holes_par_range"),
        sa.CheckConstraint(
            "stroke_index IS NULL OR stroke_index BETWEEN 1 AND 18",
            name="ck_holes_stroke_index_range",
        ),
    )
    op.create_index(op.f("ix_holes_course_id"), "holes", ["course_id"], unique=False)

    # Replace the free-text course name with a real link. Dropped outright rather
    # than migrated: the column holds no production data, and keeping both would
    # let the text drift from the linked course's name.
    op.drop_column("tournaments", "course_name")
    op.add_column(
        "tournaments",
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_tournaments_course_id"), "tournaments", ["course_id"], unique=False)
    op.create_foreign_key(
        "fk_tournaments_course_id_courses", "tournaments", "courses", ["course_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_tournaments_course_id_courses", "tournaments", type_="foreignkey")
    op.drop_index(op.f("ix_tournaments_course_id"), table_name="tournaments")
    op.drop_column("tournaments", "course_id")
    op.add_column("tournaments", sa.Column("course_name", sa.String(), nullable=True))

    op.drop_index(op.f("ix_holes_course_id"), table_name="holes")
    op.drop_table("holes")

    op.drop_index("uq_courses_name_lower", table_name="courses")
    op.drop_index(op.f("ix_courses_created_by"), table_name="courses")
    op.drop_table("courses")
