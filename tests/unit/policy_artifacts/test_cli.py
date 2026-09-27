"""CLI smoke tests for daily_agent.policy_artifacts (ADR-0003, ART-001)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from daily_agent.config import get_settings
from daily_agent.policy_artifacts.__main__ import app
from tests.support.policy_bundles import generate_keypair, write_bundle

runner = CliRunner()


@pytest.fixture(autouse=True)
def setup_cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    priv, pub = generate_keypair()
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DAILY_AGENT_ROUTER_POLICY_DIR", str(policy_dir))
    monkeypatch.setenv("DAILY_AGENT_ROUTER_POLICY_PUBLIC_KEY", pub)
    get_settings.cache_clear()

    # Save private key in tmp_path for bundle generation in tests
    priv_file = tmp_path / "priv.key"
    priv_file.write_bytes(priv.private_bytes_raw())
    yield tmp_path
    get_settings.cache_clear()


def test_cli_verify_and_install_flow(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_bytes = (tmp_path / "priv.key").read_bytes()
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)

    bundle_dir = write_bundle(tmp_path / "candidate_v1", private_key=priv, version="v1")

    # 1. verify command
    res_verify = runner.invoke(app, ["verify", str(bundle_dir)])
    assert res_verify.exit_code == 0
    assert "Valid bundle: v1" in res_verify.stdout

    # 2. install command
    res_install = runner.invoke(app, ["install", str(bundle_dir)])
    assert res_install.exit_code == 0
    assert "Installed bundle: v1" in res_install.stdout

    # 3. status command
    res_status = runner.invoke(app, ["status"])
    assert res_status.exit_code == 0
    assert "Installed: v1" in res_status.stdout
    assert "Active: None" in res_status.stdout

    # 4. promote command
    res_promote = runner.invoke(app, ["promote", "v1"])
    assert res_promote.exit_code == 0
    assert "Promoted v1 to active" in res_promote.stdout

    # Check status again
    res_status2 = runner.invoke(app, ["status"])
    assert "Active: v1" in res_status2.stdout

    # 5. rollback command
    res_rollback = runner.invoke(app, ["rollback", "--reason", "test anomaly"])
    assert res_rollback.exit_code == 0
    assert "Rolled back. Active is now: None" in res_rollback.stdout


def test_cli_shadow_and_mark_good(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_bytes = (tmp_path / "priv.key").read_bytes()
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)

    bundle_dir = write_bundle(tmp_path / "candidate_v2", private_key=priv, version="v2")
    runner.invoke(app, ["install", str(bundle_dir)])

    # shadow
    res_shadow = runner.invoke(app, ["shadow", "v2"])
    assert res_shadow.exit_code == 0
    assert "Shadow policy set to: v2" in res_shadow.stdout

    # clear shadow
    res_unshadow = runner.invoke(app, ["shadow", "--clear"])
    assert res_unshadow.exit_code == 0
    assert "Shadow policy cleared" in res_unshadow.stdout

    # mark-good
    res_good = runner.invoke(app, ["mark-good", "v2"])
    assert res_good.exit_code == 0
    assert "Marked v2 as last known good" in res_good.stdout


def test_cli_failure_exit_code_1_with_rejection_code(tmp_path: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv_bytes = (tmp_path / "priv.key").read_bytes()
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)

    # Missing signature bundle
    bad_dir = write_bundle(tmp_path / "bad_b", private_key=priv, version="bad", skip_signature=True)

    res = runner.invoke(app, ["verify", str(bad_dir)])
    assert res.exit_code == 1
    assert "Rejected: [missing_file]" in res.stderr or "Rejected: [missing_file]" in res.stdout
