"""add bug_reports table

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-11-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: str | Sequence[str] | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bug_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("ticket_number", sa.Integer(), nullable=False),
        sa.Column("client_report_id", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("screenshot", sa.LargeBinary(), nullable=True),
        sa.Column("screenshot_content_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_bug_reports_account_id_accounts", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_bug_reports_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_number", name="uq_bug_reports_ticket_number"),
        sa.UniqueConstraint("user_id", "client_report_id", name="uq_bug_reports_user_client_report_id"),
        sa.CheckConstraint(
            "category IN ('crash', 'chat', 'ui', 'account', 'other')",
            name="check_bug_reports_category",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'triaged', 'in_progress', 'fixed', 'closed', 'duplicate', 'wontfix')",
            name="check_bug_reports_status",
        ),
    )
    op.create_index("ix_bug_reports_account_id", "bug_reports", ["account_id"], unique=False)
    op.create_index("ix_bug_reports_user_id", "bug_reports", ["user_id"], unique=False)
    op.create_index("ix_bug_reports_created_at", "bug_reports", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bug_reports_created_at", table_name="bug_reports")
    op.drop_index("ix_bug_reports_user_id", table_name="bug_reports")
    op.drop_index("ix_bug_reports_account_id", table_name="bug_reports")
    op.drop_table("bug_reports")
