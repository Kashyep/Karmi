"""add user armory progression unlocked_tier and active_theme

Revision ID: 8a4f2c9e1b3d
Revises: 73075806233f
Create Date: 2026-09-26 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8a4f2c9e1b3d"
down_revision: str | Sequence[str] | None = "73075806233f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("unlocked_tier", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.add_column(
            sa.Column("active_theme", sa.Integer(), server_default="1", nullable=False)
        )
        batch_op.create_check_constraint(
            "check_users_unlocked_tier",
            "unlocked_tier BETWEEN 1 AND 4",
        )
        batch_op.create_check_constraint(
            "check_users_active_theme",
            "active_theme BETWEEN 1 AND 4",
        )
        batch_op.create_check_constraint(
            "check_users_theme_le_unlocked",
            "active_theme <= unlocked_tier",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("check_users_theme_le_unlocked", type_="check")
        batch_op.drop_constraint("check_users_active_theme", type_="check")
        batch_op.drop_constraint("check_users_unlocked_tier", type_="check")
        batch_op.drop_column("active_theme")
        batch_op.drop_column("unlocked_tier")
