"""Unit tests for the telemetry CLI subcommands (ADR-0003)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from daily_agent.telemetry.__main__ import app

runner = CliRunner()


def test_cli_status_command() -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Unfinalized runs:" in result.stdout
    assert "Unexported runs:" in result.stdout


def test_cli_finalize_command() -> None:
    result = runner.invoke(app, ["finalize"])
    assert result.exit_code == 0
    assert "Finalized" in result.stdout


def test_cli_export_command(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_exports"
    result = runner.invoke(app, ["export", "--out", str(out_dir)])
    assert result.exit_code == 0


def test_cli_purge_command() -> None:
    result = runner.invoke(app, ["purge"])
    assert result.exit_code == 0
    assert "Purge complete:" in result.stdout
