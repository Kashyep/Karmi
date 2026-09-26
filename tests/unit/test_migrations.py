from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


def test_sqlite_migrations_match_models_and_cascade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "migrations.db"
    monkeypatch.setenv("DAILY_AGENT_DATABASE_URL", f"sqlite+pysqlite:///{db}")
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "head")
    command.downgrade(alembic, "-1")
    command.upgrade(alembic, "head")
    command.check(alembic)  # raises on any model/schema drift

    with sqlite3.connect(db) as conn:
        for table, fk_count in (("runs", 2), ("budget_reservations", 1)):
            on_delete = [row[6] for row in conn.execute(f"PRAGMA foreign_key_list({table})")]
            assert on_delete.count("CASCADE") == fk_count, table
