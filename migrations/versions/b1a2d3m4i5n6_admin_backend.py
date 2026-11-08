"""admin backend: user admin columns, admin auth tables, append-only audit log, runs.created_at

Revision ID: b1a2d3m4i5n6
Revises: e2a3b4c5d6f7
Create Date: 2026-10-24 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1a2d3m4i5n6"
down_revision: str | Sequence[str] | None = "e2a3b4c5d6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch.add_column(
            sa.Column("disabled", sa.Boolean(), server_default=sa.text("false"), nullable=False)
        )
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            )
        )
        batch.add_column(sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("sessions_revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_users_last_active_at", ["last_active_at"])
    with op.batch_alter_table("runs") as batch:
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            )
        )
        batch.create_index("ix_runs_created_at", ["created_at"])

    op.create_table(
        "admin_credentials",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_admin_sessions_user_id", "admin_sessions", ["user_id"])
    op.create_table(
        "admin_audit_log",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admin_user_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_log_at", "admin_audit_log", ["at"])
    op.create_index("ix_admin_audit_log_admin_user_id", "admin_audit_log", ["admin_user_id"])
    op.create_index("ix_admin_audit_log_target_user_id", "admin_audit_log", ["target_user_id"])

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION admin_audit_log_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'admin_audit_log is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER admin_audit_log_no_update_delete
            BEFORE UPDATE OR DELETE ON admin_audit_log
            FOR EACH ROW EXECUTE FUNCTION admin_audit_log_append_only()
            """
        )
        op.execute(
            """
            CREATE TRIGGER admin_audit_log_no_truncate
            BEFORE TRUNCATE ON admin_audit_log
            FOR EACH STATEMENT EXECUTE FUNCTION admin_audit_log_append_only()
            """
        )
    elif dialect == "sqlite":
        for event in ("UPDATE", "DELETE"):
            op.execute(
                f"""
                CREATE TRIGGER admin_audit_log_no_{event.lower()}
                BEFORE {event} ON admin_audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'admin_audit_log is append-only');
                END
                """
            )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS admin_audit_log_no_truncate ON admin_audit_log")
        op.execute("DROP TRIGGER IF EXISTS admin_audit_log_no_update_delete ON admin_audit_log")
        op.execute("DROP FUNCTION IF EXISTS admin_audit_log_append_only()")
    elif dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS admin_audit_log_no_update")
        op.execute("DROP TRIGGER IF EXISTS admin_audit_log_no_delete")
    op.drop_table("admin_audit_log")
    op.drop_table("admin_sessions")
    op.drop_table("admin_credentials")
    with op.batch_alter_table("runs") as batch:
        batch.drop_index("ix_runs_created_at")
        batch.drop_column("created_at")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_last_active_at")
        batch.drop_column("sessions_revoked_at")
        batch.drop_column("last_active_at")
        batch.drop_column("created_at")
        batch.drop_column("disabled")
        batch.drop_column("email")
