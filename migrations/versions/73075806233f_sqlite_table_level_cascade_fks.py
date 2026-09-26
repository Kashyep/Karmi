"""rewrite sqlite runs/budget_reservations cascade FKs as table-level constraints

c9d4e6f2b1a5 rebuilt ``runs`` and ``budget_reservations`` on sqlite with inline
``col REFERENCES t(id) ON DELETE CASCADE``. sqlite enforces the cascade, but
SQLAlchemy only parses ON DELETE from table-level ``FOREIGN KEY`` clauses, so
reflection sees no ondelete and ``alembic check`` reports drift against the
models. Recreate those FKs as named table-level constraints. Behavior is
unchanged. PostgreSQL never went through the rebuild and already has the
cascading FKs from 92174af1e5c5, so this is a no-op there.

Revision ID: 73075806233f
Revises: a3b5c7d9e1f2
Create Date: 2026-09-26 13:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "73075806233f"
down_revision: str | Sequence[str] | None = "a3b5c7d9e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Gives the reflected (unnamed) sqlite FKs a name batch mode can drop.
_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
_CASCADE_FKS = {
    "runs": [("account_id", "accounts"), ("user_id", "users")],
    "budget_reservations": [("account_id", "accounts")],
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    for table, fks in _CASCADE_FKS.items():
        with op.batch_alter_table(table, naming_convention=_NAMING) as batch_op:
            for column, referred in fks:
                name = f"fk_{table}_{column}_{referred}"
                batch_op.drop_constraint(name, type_="foreignkey")
                batch_op.create_foreign_key(name, referred, [column], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    # The previous inline FKs cascaded too; only the DDL spelling differs.
    pass
