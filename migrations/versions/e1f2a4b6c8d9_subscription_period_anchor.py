"""add subscriptions.period_anchor (billing period anchor date)

Billing periods are anchored to the subscription start date rather than the
calendar month. Existing subscriptions default to the migration date; new
subscriptions record their creation date.

Revision ID: e1f2a4b6c8d9
Revises: d0e1f3a5b6c7
Create Date: 2026-09-20 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a4b6c8d9"
down_revision: str | Sequence[str] | None = "d0e1f3a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "period_anchor",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "period_anchor")
