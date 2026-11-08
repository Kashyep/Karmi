"""add served-model debug metadata to runs and a manual users.tester flag

Additive only. ``runs`` gains nullable served-model/attempt/latency/token columns recorded by
the gateway for every reply; ``users.tester`` (default false, set manually in the database)
gates whether a principal receives the ``debug`` object on responses.

Revision ID: e2a3b4c5d6f7
Revises: d8b2e3f4a516
Create Date: 2026-10-23 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2a3b4c5d6f7"
down_revision: str | Sequence[str] | None = "d8b2e3f4a516"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_COLUMNS: tuple[str, ...] = (
    "served_model",
    "served_provider",
    "attempt_count",
    "fallback_used",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "harness_version",
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tester", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("runs", sa.Column("served_model", sa.String(length=200), nullable=True))
    op.add_column("runs", sa.Column("served_provider", sa.String(length=40), nullable=True))
    op.add_column("runs", sa.Column("attempt_count", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("fallback_used", sa.Boolean(), nullable=True))
    op.add_column("runs", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("harness_version", sa.String(length=40), nullable=True))


def downgrade() -> None:
    for column in reversed(RUN_COLUMNS):
        op.drop_column("runs", column)
    op.drop_column("users", "tester")
