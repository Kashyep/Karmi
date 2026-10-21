"""stream runs columns

Revision ID: c7a1d2e3f405
Revises: 5f708192a3b4
Create Date: 2026-10-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a1d2e3f405"
down_revision: str | Sequence[str] | None = "5f708192a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("finish_reason", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("partial_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("last_seq", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("continuation_of_run_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("continuation_of_run_id")
        batch.drop_column("heartbeat_at")
        batch.drop_column("last_seq")
        batch.drop_column("partial_text")
        batch.drop_column("finish_reason")
