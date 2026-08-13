"""Add private user-authored skill folders.

Revision ID: 0122_personal_skills
Revises: 0121_seed_system_default_agent
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

from app.types.guid import GUID

revision = "0122_personal_skills"
down_revision = "0121_seed_system_default_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_skills",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("normalized_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "normalized_name", name="uq_personal_skills_user_name"),
        sa.CheckConstraint("revision >= 1", name="ck_personal_skills_revision_positive"),
    )
    op.create_index("ix_personal_skills_user_id", "personal_skills", ["user_id"])

    op.create_table(
        "personal_skill_files",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "skill_id",
            GUID(),
            sa.ForeignKey("personal_skills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("is_directory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("skill_id", "path", name="uq_personal_skill_files_skill_path"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_personal_skill_files_size_nonnegative"),
        sa.CheckConstraint(
            "(is_directory = true AND content IS NULL AND size_bytes = 0) OR "
            "(is_directory = false AND content IS NOT NULL)",
            name="ck_personal_skill_files_entry_shape",
        ),
    )
    op.create_index("ix_personal_skill_files_skill_id", "personal_skill_files", ["skill_id"])

    op.create_table(
        "personal_skill_assignments",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "skill_id",
            GUID(),
            sa.ForeignKey("personal_skills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            GUID(),
            sa.ForeignKey("marketplace_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "user_id", "skill_id", "agent_id", name="uq_personal_skill_assignments_binding"
        ),
    )
    op.create_index(
        "ix_personal_skill_assignments_skill_id", "personal_skill_assignments", ["skill_id"]
    )
    op.create_index(
        "ix_personal_skill_assignments_agent_id", "personal_skill_assignments", ["agent_id"]
    )
    op.create_index(
        "ix_personal_skill_assignments_user_id", "personal_skill_assignments", ["user_id"]
    )


def downgrade() -> None:
    op.drop_table("personal_skill_assignments")
    op.drop_table("personal_skill_files")
    op.drop_table("personal_skills")