"""scale indexes: chat message lookups, reservation sweep, trigram search

Plain b-tree indexes back the chat message lookups and the reservation sweep
on every dialect. Trigram GIN indexes back the case-insensitive substring
search over message content and conversation titles; they exist only on
PostgreSQL (pg_trgm), so other dialects skip them.

Revision ID: c3s1c4l5e6d7
Revises: b1a2d3m4i5n6
Create Date: 2026-10-24 09:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3s1c4l5e6d7"
down_revision: str | Sequence[str] | None = "b1a2d3m4i5n6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLAIN_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_chat_messages_account_id", "chat_messages", "account_id"),
    ("ix_chat_messages_run_id", "chat_messages", "run_id"),
    ("ix_chat_messages_parent_message_id", "chat_messages", "parent_message_id"),
    ("ix_chat_messages_client_message_id", "chat_messages", "client_message_id"),
    ("ix_budget_reservations_status_created", "budget_reservations", "status, created_at"),
)

TRGM_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_chat_messages_content_trgm", "chat_messages", "content"),
    ("ix_conversations_title_trgm", "conversations", "title"),
)


def upgrade() -> None:
    for name, table, columns in PLAIN_INDEXES:
        op.create_index(name, table, [c.strip() for c in columns.split(",")], if_not_exists=True)

    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        for name, table, column in TRGM_INDEXES:
            op.execute(
                f"CREATE INDEX IF NOT EXISTS {name} ON {table} USING gin ({column} gin_trgm_ops)"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for name, _table, _column in TRGM_INDEXES:
            op.execute(f"DROP INDEX IF EXISTS {name}")

    for name, table, _columns in reversed(PLAIN_INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
