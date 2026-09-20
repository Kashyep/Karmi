"""add users.token_version for token revocation

Tokens now sign the user's token_version; bumping the column revokes all
outstanding tokens without rotating the auth secret.

Revision ID: f1a2b3c4d5e6
Revises: e1f2a4b6c8d9
Create Date: 2026-09-20 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e1f2a4b6c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
