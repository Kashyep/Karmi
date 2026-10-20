"""drop the notes table (notes feature removed by owner decision, 2026-10-20)

DESTRUCTIVE: existing notes are deleted. Downgrade recreates an empty table with the previous
shape; it cannot restore the data.

Revision ID: 4d5e6f708192
Revises: 3c4d5e6f7081
Create Date: 2026-10-20 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d5e6f708192"
down_revision: str | Sequence[str] | None = "3c4d5e6f7081"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_notes_owner_user_id", table_name="notes")
    op.drop_index("ix_notes_account_id", table_name="notes")
    op.drop_table("notes")


def downgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "idempotency_key", name="uq_notes_account_key"),
    )
    op.create_index("ix_notes_account_id", "notes", ["account_id"], unique=False)
    op.create_index("ix_notes_owner_user_id", "notes", ["owner_user_id"], unique=False)
