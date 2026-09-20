"""widen money and version columns to BigInteger

All *_micro columns and event_version counters were Integer (int32), which
overflows at ~2.1 billion micro-units (~$2,147). Widen to BigInteger.

Revision ID: b7c2d4e8f1a3
Revises: 92174af1e5c5
Create Date: 2026-09-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c2d4e8f1a3"
down_revision: str | Sequence[str] | None = "92174af1e5c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_MONEY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("usage_windows", "spend_limit_micro"),
    ("usage_windows", "reserved_micro"),
    ("usage_windows", "settled_micro"),
    ("platform_budgets", "spend_limit_micro"),
    ("platform_budgets", "reserved_micro"),
    ("platform_budgets", "settled_micro"),
    ("budget_reservations", "reserved_micro"),
    ("budget_reservations", "actual_micro"),
    ("cost_ledger", "cost_micro"),
    ("subscriptions", "event_version"),
    ("billing_events", "event_version"),
)


def upgrade() -> None:
    for table, column in _MONEY_COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(column, type_=sa.BigInteger(), existing_type=sa.Integer())


def downgrade() -> None:
    for table, column in _MONEY_COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(column, type_=sa.Integer(), existing_type=sa.BigInteger())
