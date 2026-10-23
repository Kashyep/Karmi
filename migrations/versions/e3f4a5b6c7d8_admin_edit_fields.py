"""add tester_label, admin_notes, tier_expires_at, revert_plan_id

Revision ID: e3f4a5b6c7d8
Revises: d4e5a6s7t8b9
Create Date: 2026-10-24 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | Sequence[str] | None = "d4e5a6s7t8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tester_label", sa.String(40), nullable=True))
    op.add_column("users", sa.Column("admin_notes", sa.Text, nullable=True))
    op.add_column(
        "subscriptions",
        sa.Column("tier_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("revert_plan_id", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "revert_plan_id")
    op.drop_column("subscriptions", "tier_expires_at")
    op.drop_column("users", "admin_notes")
    op.drop_column("users", "tester_label")
