"""delivery leases for outbox events and reminders

Adds lease_until to outbox_events and reminders, plus reminders.attempts, so
the delivery worker can claim rows exclusively and recover rows stranded by a
crashed worker.

Revision ID: a3b5c7d9e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-26 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b5c7d9e1f2"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reminders", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "reminders", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    with op.batch_alter_table("reminders") as batch:
        batch.drop_column("attempts")
        batch.drop_column("lease_until")
    with op.batch_alter_table("outbox_events") as batch:
        batch.drop_column("lease_until")
