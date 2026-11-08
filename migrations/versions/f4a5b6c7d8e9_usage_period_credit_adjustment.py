"""persist admin usage-period credit adjustments

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-10-24 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | Sequence[str] | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "usage_periods",
        sa.Column("credit_adjust_micro", sa.BigInteger(), server_default="0", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("usage_periods", "credit_adjust_micro")
