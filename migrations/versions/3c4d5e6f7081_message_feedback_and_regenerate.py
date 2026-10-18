"""message feedback table and regenerate links on runs

Adds ``message_feedback`` (one account-scoped rating per reply, fixed-vocabulary reason) and
``runs.previous_run_id`` / ``runs.regenerate_reason`` so a regenerated reply links to the one it
replaces.

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
Create Date: 2026-10-18 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c4d5e6f7081"
down_revision: str | Sequence[str] | None = "2b3c4d5e6f70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("previous_run_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("regenerate_reason", sa.String(length=20), nullable=True))
        batch.create_foreign_key(
            "fk_runs_previous_run_id", "runs", ["previous_run_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_runs_previous_run_id", ["previous_run_id"])
    op.create_table(
        "message_feedback",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(length=36),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "run_id"),
        sa.CheckConstraint("rating IN ('up', 'down')", name="check_message_feedback_rating"),
    )
    op.create_index("ix_message_feedback_account_id", "message_feedback", ["account_id"])
    op.create_index("ix_message_feedback_run_id", "message_feedback", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_message_feedback_run_id", table_name="message_feedback")
    op.drop_index("ix_message_feedback_account_id", table_name="message_feedback")
    op.drop_table("message_feedback")
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_previous_run_id")
        batch.drop_constraint("fk_runs_previous_run_id", type_="foreignkey")
        batch.drop_column("regenerate_reason")
        batch.drop_column("previous_run_id")
