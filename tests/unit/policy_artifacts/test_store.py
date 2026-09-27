"""Unit tests for PolicyStore (ADR-0003, ART-001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from daily_agent.observability import Metrics
from daily_agent.policy_artifacts.schema import MANIFEST
from daily_agent.policy_artifacts.store import PolicyStore, StoreCorrupt
from daily_agent.policy_artifacts.verifier import BundleRejected
from daily_agent.routing.registry import entitlement_map
from tests.support.policy_bundles import (
    generate_keypair,
    tamper_file,
    write_bundle,
)

KNOWN_MODELS = entitlement_map()
KARMI_VERSION = "0.1.0"


@pytest.fixture
def store_setup(tmp_path: Path) -> tuple[PolicyStore, Path, Ed25519PrivateKey, str]:
    priv, pub = generate_keypair()
    metrics = Metrics()
    store = PolicyStore(
        root=tmp_path / "store",
        public_key_b64=pub,
        known_models=KNOWN_MODELS,
        karmi_version=KARMI_VERSION,
        metrics=metrics,
    )
    return store, tmp_path / "sources", priv, pub


def test_install_and_idempotence(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup
    b1_dir = write_bundle(src_dir / "b1", private_key=priv, version="v1")

    # First install
    loaded = store.install(b1_dir)
    assert loaded.manifest.artifact_version == "v1"

    state = store.read_state()
    assert state.installed == ["v1"]
    assert state.active is None
    assert state.shadow is None
    assert len(state.history) == 1
    assert state.history[0].action == "install"
    assert state.history[0].version == "v1"

    # Idempotent re-install of identical content
    loaded2 = store.install(b1_dir)
    assert loaded2.content_sha256 == loaded.content_sha256
    state2 = store.read_state()
    assert state2.installed == ["v1"]
    assert state2.active is None


def test_install_version_conflict(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup
    b1_dir = write_bundle(src_dir / "b1", private_key=priv, version="v1", alpha=0.0)
    store.install(b1_dir)

    # Different content with same version
    b1_conflict = write_bundle(src_dir / "b1_alt", private_key=priv, version="v1", alpha=1.0)
    with pytest.raises(BundleRejected) as exc:
        store.install(b1_conflict)
    assert exc.value.code == "version_conflict"


def test_failed_install_leaves_state_and_active_untouched(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup
    # Install and promote valid bundle first
    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    store.install(b1)
    store.promote("v1")

    initial_state = store.read_state()
    assert initial_state.active == "v1"

    # Attempt to install an invalid bundle (e.g. missing signature)
    bad_dir = src_dir / "bad_bundle"
    write_bundle(bad_dir, private_key=priv, version="v2", skip_signature=True)

    with pytest.raises(BundleRejected):
        store.install(bad_dir)

    # Verify state and active policy remain unchanged
    after_state = store.read_state()
    assert after_state.active == "v1"
    assert after_state.revision == initial_state.revision
    assert "v2" not in after_state.installed


def test_promote_requires_regression_pass(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    # Bundle that failed regression
    failed_dir = write_bundle(
        src_dir / "b_fail",
        private_key=priv,
        version="fail-1",
        passed_regression=False,
    )
    store.install(failed_dir)

    with pytest.raises(BundleRejected) as exc:
        store.promote("fail-1")
    assert exc.value.code == "not_promotable"

    # Attempt to promote uninstalled version
    with pytest.raises(BundleRejected) as exc2:
        store.promote("never-installed")
    assert exc2.value.code == "not_promotable"


def test_promote_and_rollback_restores_previous(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    b2 = write_bundle(src_dir / "b2", private_key=priv, version="v2")
    store.install(b1)
    store.install(b2)

    store.promote("v1")
    assert store.read_state().active == "v1"
    assert store.read_state().previous is None

    store.promote("v2")
    state = store.read_state()
    assert state.active == "v2"
    assert state.previous == "v1"

    # Rollback restores previous in one call
    new_active = store.rollback(reason="v2 latency spike")
    assert new_active == "v1"

    state_after = store.read_state()
    assert state_after.active == "v1"
    assert state_after.previous is None


def test_rollback_falls_back_to_last_known_good_when_previous_corrupted(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    b2 = write_bundle(src_dir / "b2", private_key=priv, version="v2")
    b3 = write_bundle(src_dir / "b3", private_key=priv, version="v3")
    store.install(b1)
    store.install(b2)
    store.install(b3)

    # Mark v1 as last known good
    store.mark_known_good("v1")
    store.promote("v2")
    store.promote("v3")

    state = store.read_state()
    assert state.active == "v3"
    assert state.previous == "v2"
    assert state.last_known_good == "v1"

    # Corrupt v2 (previous) on disk
    v2_dir = store.bundles_dir / "v2"
    tamper_file(v2_dir, MANIFEST, '{"corrupted": true}')

    # Rollback skips corrupted v2 and falls back to last_known_good (v1)
    new_active = store.rollback(reason="v3 failure and v2 broken")
    assert new_active == "v1"

    state_after = store.read_state()
    assert state_after.active == "v1"


def test_rollback_to_static_when_nothing_verifies(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    store.install(b1)
    store.promote("v1")

    # There is no previous and no last_known_good
    new_active = store.rollback(reason="v1 decommission")
    assert new_active is None

    state = store.read_state()
    assert state.active is None


def test_rollback_clears_failing_active_from_shadow(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    store.install(b1)
    store.promote("v1")
    store.set_shadow("v1")

    assert store.read_state().shadow == "v1"
    store.rollback(reason="testing shadow clear")

    state = store.read_state()
    assert state.shadow is None


def test_deactivate(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    store.install(b1)
    store.promote("v1")
    assert store.read_state().active == "v1"

    store.deactivate(reason="manual maintenance")
    state = store.read_state()
    assert state.active is None
    assert state.previous == "v1"


def test_load_re_verifies_from_disk_every_time(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    store.install(b1)

    # Initial load succeeds
    loaded = store.load("v1")
    assert loaded.manifest.artifact_version == "v1"

    # Tamper with installed files directly on disk
    tamper_file(store.bundles_dir / "v1", MANIFEST, '{"tampered": true}')

    # Subsequent load must fail because disk is not trusted
    with pytest.raises(BundleRejected) as exc:
        store.load("v1")
    assert exc.value.code == "checksum_mismatch"


def test_state_remains_valid_json_after_every_operation(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    store.install(b1)
    store.set_shadow("v1")
    store.promote("v1")
    store.mark_known_good("v1")
    store.rollback("test rollback")
    store.deactivate("test deactivate")

    # Read state.json raw and ensure valid JSON parseable
    raw = store.state_file.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["revision"] > 0
    assert isinstance(parsed["history"], list)


def test_corrupt_state_raises_store_corrupt(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, _src_dir, _priv, _pub = store_setup
    store.state_file.write_text("invalid json {{{", encoding="utf-8")
    with pytest.raises(StoreCorrupt):
        store.read_state()


def test_metrics_recording(
    store_setup: tuple[PolicyStore, Path, Ed25519PrivateKey, str],
) -> None:
    store, src_dir, priv, _pub = store_setup

    b1 = write_bundle(src_dir / "b1", private_key=priv, version="v1")
    store.install(b1)
    store.promote("v1")
    store.rollback("anomaly")

    assert store.metrics.counter("policy_rollbacks_total") == 1
    # Trigger a verification failure
    bad_dir = src_dir / "bad"
    write_bundle(bad_dir, private_key=priv, version="bad", skip_signature=True)
    with pytest.raises(BundleRejected):
        store.install(bad_dir)

    assert store.metrics.counter("policy_verification_failures_total", {"code": "missing_file"}) >= 1
