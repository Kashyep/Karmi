"""tombstone erased Clerk subjects so erasure cannot be undone by signing in again

Erasing a user deletes the row that held its Clerk subject; without a tombstone the next
Clerk sign-in with that subject would silently provision a fresh free account. The table
stores only the SHA-256 of the subject.

Revision ID: d4e5a6s7t8b9
Revises: c3s1c4l5e6d7
Create Date: 2026-10-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5a6s7t8b9"
down_revision: str | Sequence[str] | None = "c3s1c4l5e6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "erased_clerk_subjects",
        sa.Column("subject_hash", sa.String(length=64), primary_key=True),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("erased_clerk_subjects")
