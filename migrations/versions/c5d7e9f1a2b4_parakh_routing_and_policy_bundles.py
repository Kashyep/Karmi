"""parakh routing evidence and policy bundle shadow slots

Adds the per-run routing evidence (``routing_records``, ``routing_decisions``)
exported to Parakh as TelemetryBatchV1, and Karmi's verified PolicyBundleV1
copies (``policy_bundles``) with an append-only transition log
(``policy_bundle_events``). No existing table changes.

Revision ID: c5d7e9f1a2b4
Revises: 8a4f2c9e1b3d
Create Date: 2026-09-28 01:32:33.217223
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d7e9f1a2b4"
down_revision: str | Sequence[str] | None = "8a4f2c9e1b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_bundles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("artifact_version", sa.String(length=80), nullable=False),
        sa.Column("checksums_sha256", sa.String(length=64), nullable=False),
        sa.Column("signer_public_key", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_version"),
    )
    op.create_index(op.f("ix_policy_bundles_state"), "policy_bundles", ["state"], unique=False)
    op.create_index(
        "ix_policy_bundles_single_shadow",
        "policy_bundles",
        ["state"],
        unique=True,
        sqlite_where=sa.text("state = 'shadow'"),
        postgresql_where=sa.text("state = 'shadow'"),
    )
    op.create_table(
        "policy_bundle_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bundle_id", sa.String(length=36), nullable=False),
        sa.Column("from_state", sa.String(length=20), nullable=True),
        sa.Column("to_state", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bundle_id"], ["policy_bundles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_policy_bundle_events_bundle_id"), "policy_bundle_events", ["bundle_id"], unique=False
    )
    op.create_table(
        "routing_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("shadow", sa.Boolean(), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=40), nullable=False),
        sa.Column("selected_action", sa.String(length=120), nullable=False),
        sa.Column("selection_probability", sa.Float(), nullable=False),
        sa.Column("exploration", sa.Boolean(), nullable=False),
        sa.Column("eligible_actions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "selection_probability > 0 AND selection_probability <= 1",
            name="check_routing_decisions_probability",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "shadow", "policy_version"),
    )
    op.create_index(
        op.f("ix_routing_decisions_run_id"), "routing_decisions", ["run_id"], unique=False
    )
    op.create_table(
        "routing_records",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("task_domain", sa.String(length=40), nullable=False),
        sa.Column("routing_context", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Text(), nullable=False),
        sa.Column("harness_version", sa.String(length=40), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("policy_version", sa.String(length=80), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=40), nullable=False),
        sa.Column("executed_action", sa.String(length=120), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("cost_micro", sa.BigInteger(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        op.f("ix_routing_records_completed_at"), "routing_records", ["completed_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_policy_bundles_single_shadow", table_name="policy_bundles")
    op.drop_index(op.f("ix_routing_records_completed_at"), table_name="routing_records")
    op.drop_table("routing_records")
    op.drop_index(op.f("ix_routing_decisions_run_id"), table_name="routing_decisions")
    op.drop_table("routing_decisions")
    op.drop_index(op.f("ix_policy_bundle_events_bundle_id"), table_name="policy_bundle_events")
    op.drop_table("policy_bundle_events")
    op.drop_index(op.f("ix_policy_bundles_state"), table_name="policy_bundles")
    op.drop_table("policy_bundles")
