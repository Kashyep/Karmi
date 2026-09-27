"""Unit tests for the telemetry CLI subcommands (ADR-0003).

Each test runs the CLI against a throwaway SQLite database built by the real Alembic
migrations, never the developer's default database.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from daily_agent import db
from daily_agent.config import get_settings
from daily_agent.models import utcnow
from daily_agent.telemetry import writer
from daily_agent.telemetry.__main__ import app
from tests.unit.telemetry.conftest import build_synthetic_run_record

runner = CliRunner()


@pytest.fixture(autouse=True)
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("DAILY_AGENT_DATABASE_URL", database_url)
    monkeypatch.setenv("DAILY_AGENT_TELEMETRY_EXPORT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = db.build_engine(get_settings())
    monkeypatch.setattr(db, "_engine", engine)

    # One completed run whose configured attribution window has already elapsed.
    now = utcnow()
    completed = now - timedelta(seconds=get_settings().telemetry_attribution_window_seconds + 60)
    run = build_synthetic_run_record(started_at=completed, completed_at=completed)
    with Session(engine) as session:
        writer.persist_events(
            session,
            [run],
            now=completed,
            attribution_window_seconds=get_settings().telemetry_attribution_window_seconds,
        )
        session.commit()
    yield
    engine.dispose()
    get_settings.cache_clear()


def test_cli_status_command() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "Unfinalized runs: 1" in result.stdout
    assert "Unexported runs: 0" in result.stdout


def test_cli_finalize_command() -> None:
    result = runner.invoke(app, ["finalize"])
    assert result.exit_code == 0, result.output
    assert "Finalized 1 runs." in result.stdout
    status = runner.invoke(app, ["status"])
    assert "Unfinalized runs: 0" in status.stdout
    assert "Unexported runs: 1" in status.stdout


def test_cli_export_command(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_exports"
    assert runner.invoke(app, ["finalize"]).exit_code == 0
    result = runner.invoke(app, ["export", "--out", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert "(1 runs, 0 signals, 0 feedback)" in result.stdout
    assert len(list(out_dir.glob("*.json"))) == 1
    assert "Nothing to export." in runner.invoke(app, ["export", "--out", str(out_dir)]).stdout


def test_cli_purge_command() -> None:
    result = runner.invoke(app, ["purge"])
    assert result.exit_code == 0, result.output
    # The seeded run is inside the retention period and unexported, so nothing is deleted.
    assert "Purge complete: 0 runs" in result.stdout
    assert "Unfinalized runs: 1" in runner.invoke(app, ["status"]).stdout
