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


def test_debug_meta_migration_round_trips_to_its_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "debug_meta.db"
    monkeypatch.setenv("DAILY_AGENT_DATABASE_URL", f"sqlite+pysqlite:///{db}")
    alembic = Config("alembic.ini")
    command.upgrade(alembic, "d8b2e3f4a516")
    command.upgrade(alembic, "head")
    with sqlite3.connect(db) as conn:
        assert "tester" in {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        assert "served_model" in {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    command.downgrade(alembic, "d8b2e3f4a516")
    with sqlite3.connect(db) as conn:
        assert "tester" not in {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        assert "served_model" not in {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    command.upgrade(alembic, "head")
    command.check(alembic)
