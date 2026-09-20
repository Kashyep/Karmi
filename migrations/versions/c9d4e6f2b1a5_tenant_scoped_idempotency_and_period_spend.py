"""tenant-scoped idempotency + non-resetting period spend accumulator

- New ``usage_periods`` table: the monetary ``period_cost_cap_micro`` lives on a
  per-month row instead of being re-granted by every daily ``usage_windows`` row.
- ``budget_reservations``: +``usage_period_id`` FK; uniqueness moves to
  ``(account_id, logical_request_id, stage)``; ``logical_request_id`` widened to
  160 (MessageCreate allows 120-char keys, which overflowed String(80) on
  PostgreSQL).
- ``runs``: +``request_hash`` for replay payload verification; uniqueness moves
  to ``(account_id, logical_request_id)``; ``logical_request_id`` widened.
- ``notes``: +``idempotency_key`` with ``(account_id, idempotency_key)`` unique.

On sqlite, column-level UNIQUE constraints are unnamed and cannot be dropped, so
``runs`` and ``budget_reservations`` are rebuilt via copy-and-rename. All
databases this project uses are disposable dev/test instances, so the rebuild is
safe here.

Revision ID: c9d4e6f2b1a5
Revises: b7c2d4e8f1a3
Create Date: 2026-09-20 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d4e6f2b1a5"
down_revision: str | Sequence[str] | None = "b7c2d4e8f1a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_usage_periods() -> None:
    op.create_table(
        "usage_periods",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("period_key", sa.String(length=40), nullable=False),
        sa.Column("spend_limit_micro", sa.BigInteger(), nullable=False),
        sa.Column("reserved_micro", sa.BigInteger(), nullable=False),
        sa.Column("settled_micro", sa.BigInteger(), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "period_key"),
    )
    op.create_index(op.f("ix_usage_periods_account_id"), "usage_periods", ["account_id"])


_RUNS_COPY_COLUMNS = (
    "id, account_id, user_id, logical_request_id, status, outcome, response_text, generation"
)
_RESERVATION_COPY_COLUMNS = (
    "id, logical_request_id, account_id, usage_window_id, stage, "
    "reserved_micro, actual_micro, status, created_at"
)


def _rebuild_runs_sqlite() -> None:
    op.execute(
        """
        CREATE TABLE runs_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            account_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            logical_request_id VARCHAR(160) NOT NULL,
            request_hash VARCHAR(64),
            status VARCHAR(30) NOT NULL,
            outcome VARCHAR(30),
            response_text TEXT,
            generation INTEGER NOT NULL,
            CONSTRAINT uq_runs_account_request UNIQUE (account_id, logical_request_id)
        )
        """
    )
    op.execute(f"INSERT INTO runs_new ({_RUNS_COPY_COLUMNS}) SELECT {_RUNS_COPY_COLUMNS} FROM runs")
    op.execute("DROP TABLE runs")
    op.execute("ALTER TABLE runs_new RENAME TO runs")
    op.execute("CREATE INDEX ix_runs_account_id ON runs (account_id)")
    op.execute("CREATE INDEX ix_runs_user_id ON runs (user_id)")


def _rebuild_reservations_sqlite() -> None:
    op.execute(
        """
        CREATE TABLE budget_reservations_new (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            logical_request_id VARCHAR(160) NOT NULL,
            account_id VARCHAR(36) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            usage_window_id VARCHAR(36) NOT NULL REFERENCES usage_windows(id),
            usage_period_id VARCHAR(36) REFERENCES usage_periods(id),
            stage VARCHAR(32) NOT NULL,
            reserved_micro BIGINT NOT NULL,
            actual_micro BIGINT,
            status VARCHAR(20) NOT NULL,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_reservations_account_request_stage
                UNIQUE (account_id, logical_request_id, stage)
        )
        """
    )
    op.execute(
        f"INSERT INTO budget_reservations_new ({_RESERVATION_COPY_COLUMNS}) "
        f"SELECT {_RESERVATION_COPY_COLUMNS} FROM budget_reservations"
    )
    op.execute("DROP TABLE budget_reservations")
    op.execute("ALTER TABLE budget_reservations_new RENAME TO budget_reservations")
    op.execute(
        "CREATE INDEX ix_budget_reservations_account_id ON budget_reservations (account_id)"
    )
    op.execute(
        "CREATE INDEX ix_budget_reservations_logical_request_id "
        "ON budget_reservations (logical_request_id)"
    )


def upgrade() -> None:
    _create_usage_periods()
    if op.get_bind().dialect.name == "sqlite":
        _rebuild_runs_sqlite()
        _rebuild_reservations_sqlite()
    else:
        op.drop_constraint("runs_logical_request_id_key", "runs", type_="unique")
        op.alter_column("runs", "logical_request_id", type_=sa.String(160))
        op.add_column("runs", sa.Column("request_hash", sa.String(64), nullable=True))
        op.create_unique_constraint(
            "uq_runs_account_request", "runs", ["account_id", "logical_request_id"]
        )
        op.drop_constraint(
            "budget_reservations_logical_request_id_stage_key",
            "budget_reservations",
            type_="unique",
        )
        op.alter_column(
            "budget_reservations", "logical_request_id", type_=sa.String(160)
        )
        op.add_column(
            "budget_reservations",
            sa.Column(
                "usage_period_id",
                sa.String(36),
                sa.ForeignKey("usage_periods.id"),
                nullable=True,
            ),
        )
        op.create_unique_constraint(
            "uq_reservations_account_request_stage",
            "budget_reservations",
            ["account_id", "logical_request_id", "stage"],
        )
    with op.batch_alter_table("notes") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(120), nullable=True))
        batch_op.create_unique_constraint(
            "uq_notes_account_key", ["account_id", "idempotency_key"]
        )


def downgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.drop_constraint("uq_notes_account_key", type_="unique")
        batch_op.drop_column("idempotency_key")
    if op.get_bind().dialect.name == "sqlite":
        raise NotImplementedError("sqlite downgrade rebuilds are not implemented")
    op.drop_constraint("uq_reservations_account_request_stage", "budget_reservations")
    op.drop_column("budget_reservations", "usage_period_id")
    op.alter_column("budget_reservations", "logical_request_id", type_=sa.String(80))
    op.create_unique_constraint(
        "budget_reservations_logical_request_id_stage_key",
        "budget_reservations",
        ["logical_request_id", "stage"],
    )
    op.drop_constraint("uq_runs_account_request", "runs")
    op.drop_column("runs", "request_hash")
    op.alter_column("runs", "logical_request_id", type_=sa.String(80))
    op.create_unique_constraint("runs_logical_request_id_key", "runs", ["logical_request_id"])
    op.drop_index(op.f("ix_usage_periods_account_id"), table_name="usage_periods")
    op.drop_table("usage_periods")
