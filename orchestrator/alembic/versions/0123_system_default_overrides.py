"""Add per-user System Default Agent overrides.

Revision ID: 0123_system_default_overrides
Revises: 0122_personal_skills
Create Date: 2026-08-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0123_system_default_overrides"
down_revision = "0122_personal_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_purchased_agents", sa.Column("agent_overrides", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_purchased_agents") as batch_op:
        batch_op.drop_column("agent_overrides")