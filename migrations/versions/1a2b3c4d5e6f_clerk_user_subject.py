"""link users to stable Clerk identity subjects

Revision ID: 1a2b3c4d5e6f
Revises: c5d7e9f1a2b4
Create Date: 2026-10-10 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1a2b3c4d5e6f"
down_revision: str | Sequence[str] | None = "c5d7e9f1a2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("clerk_subject", sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint("uq_users_clerk_subject", ["clerk_subject"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_clerk_subject", type_="unique")
        batch_op.drop_column("clerk_subject")
