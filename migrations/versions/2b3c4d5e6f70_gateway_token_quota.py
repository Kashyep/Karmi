"""daily token quota counters for the model gateway

Adds ``usage_windows.token_limit/tokens_reserved/tokens_settled`` and
``budget_reservations.reserved_tokens``. Windows that already exist get the largest plan quota so
an in-flight day is not retroactively locked; new windows take the plan's own quota.

Revision ID: 2b3c4d5e6f70
Revises: 1a2b3c4d5e6f
Create Date: 2026-10-18 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2b3c4d5e6f70"
down_revision: str | Sequence[str] | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("usage_windows") as batch:
        batch.add_column(
            sa.Column("token_limit", sa.BigInteger(), server_default="2000000", nullable=False)
        )
        batch.add_column(
            sa.Column("tokens_reserved", sa.BigInteger(), server_default="0", nullable=False)
        )
        batch.add_column(
            sa.Column("tokens_settled", sa.BigInteger(), server_default="0", nullable=False)
        )
    with op.batch_alter_table("budget_reservations") as batch:
        batch.add_column(
            sa.Column("reserved_tokens", sa.BigInteger(), server_default="0", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("budget_reservations") as batch:
        batch.drop_column("reserved_tokens")
    with op.batch_alter_table("usage_windows") as batch:
        batch.drop_column("tokens_settled")
        batch.drop_column("tokens_reserved")
        batch.drop_column("token_limit")
