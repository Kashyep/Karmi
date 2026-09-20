"""backfill usage_periods from existing windows and widen outbox logical_key

The previous migration introduced ``usage_periods`` empty, which would re-grant
the full period cap to accounts with existing month-to-date spend. Backfill one
period row per account from its ``usage_windows`` rows (current-month settled,
all open reserved) and attach open reservations to it so ``settle_budget``
accounts them.

Also widens ``outbox_events.logical_key`` to 255 — the namespaced key
``response:{account_id}:{key}`` can reach 166 chars, overflowing String(160).

Revision ID: d0e1f3a5b6c7
Revises: c9d4e6f2b1a5
Create Date: 2026-09-20 12:30:00.000000
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from daily_agent.plans import SYNTHETIC_POLICIES

revision: str = "d0e1f3a5b6c7"
down_revision: str | Sequence[str] | None = "c9d4e6f2b1a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_usage_periods() -> None:
    now = datetime.now(UTC)
    period_key = now.strftime("%Y-%m")
    if now.month == 12:
        reset_at = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        reset_at = datetime(now.year, now.month + 1, 1, tzinfo=UTC)

    conn = op.get_bind()
    accounts = conn.execute(
        sa.text(
            "SELECT account_id FROM usage_windows "
            "UNION SELECT account_id FROM budget_reservations "
            "WHERE status = 'reserved' AND usage_period_id IS NULL"
        )
    ).all()
    for (account_id,) in accounts:
        plan_id = conn.execute(
            sa.text("SELECT plan_id FROM subscriptions WHERE account_id = :a"),
            {"a": account_id},
        ).scalar()
        policy = SYNTHETIC_POLICIES.get(plan_id or "", SYNTHETIC_POLICIES["ananta"])
        # Open reservations are current money in flight regardless of which daily
        # window created them; settled spend only counts within this period.
        reserved = conn.execute(
            sa.text(
                "SELECT COALESCE(SUM(reserved_micro), 0) FROM usage_windows "
                "WHERE account_id = :a"
            ),
            {"a": account_id},
        ).scalar()
        settled = conn.execute(
            sa.text(
                "SELECT COALESCE(SUM(settled_micro), 0) FROM usage_windows "
                "WHERE account_id = :a AND window_key LIKE :prefix"
            ),
            {"a": account_id, "prefix": f"{period_key}-%"},
        ).scalar()
        period_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO usage_periods "
                "(id, account_id, period_key, spend_limit_micro, reserved_micro, "
                "settled_micro, reset_at) "
                "VALUES (:id, :a, :k, :lim, :r, :s, :reset)"
            ),
            {
                "id": period_id,
                "a": account_id,
                "k": period_key,
                "lim": policy.period_cost_cap_micro,
                "r": reserved,
                "s": settled,
                "reset": reset_at,
            },
        )
        conn.execute(
            sa.text(
                "UPDATE budget_reservations SET usage_period_id = :pid "
                "WHERE account_id = :a AND status = 'reserved' AND usage_period_id IS NULL"
            ),
            {"pid": period_id, "a": account_id},
        )


def upgrade() -> None:
    _backfill_usage_periods()
    with op.batch_alter_table("outbox_events") as batch_op:
        batch_op.alter_column(
            "logical_key", type_=sa.String(255), existing_type=sa.String(160)
        )


def downgrade() -> None:
    with op.batch_alter_table("outbox_events") as batch_op:
        batch_op.alter_column(
            "logical_key", type_=sa.String(160), existing_type=sa.String(255)
        )
    now = datetime.now(UTC)
    op.execute(
        sa.text("DELETE FROM usage_periods WHERE period_key = :k"),
        {"k": now.strftime("%Y-%m")},
    )
    op.execute(
        sa.text("UPDATE budget_reservations SET usage_period_id = NULL")
    )
