"""shared daily counter of live provider requests

Adds ``gateway_request_days``: one row per UTC day holding how many live model-provider requests
were admitted across every account, so the beta stays inside the provider key's daily limit.

Revision ID: 5f708192a3b4
Revises: 4d5e6f708192
Create Date: 2026-10-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f708192a3b4"
down_revision: str | Sequence[str] | None = "4d5e6f708192"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gateway_request_days",
        sa.Column("day_key", sa.String(length=10), nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day_key"),
    )


def downgrade() -> None:
    # Only daily counters are lost; they hold no user data.
    op.drop_table("gateway_request_days")
