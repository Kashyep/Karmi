from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

import pytest

from daily_agent.config import Settings
from daily_agent.parakh.bundle import BundleRejected, LoadedPolicy, load_bundle
from daily_agent.parakh.receiver import verify_bundle
from daily_agent.parakh.routing import (
    FEATURE_SCHEMA_VERSION,
    KNOWN_ACTIONS,
    UnknownPlanError,
    contract_tier,
)
from daily_agent.plans import SYNTHETIC_POLICIES
from tests.parakh_helpers import (
    FIXTURE,
    FIXTURE_PUBLIC_KEY,
    SIM_ACTIONS,
    TEST_PUBLIC_KEY,
    make_karmi_bundle,
    sign_directory,
)

CONTEXT = {
    "tier": "trika", "task_domain": "communication", "estimated_input_tokens": 900,
    "context_utilization_ratio": 0.05, "tool_count": 0, "requires_structured_output": False,
    "requires_tools": False, "requires_memory": True, "requires_external_data": False,
    "conversation_depth": 0, "retry_number": 0, "previous_tool_failure": False,
    "latency_slo_ms": None,
}


def _load(path: Path, **overrides: object) -> LoadedPolicy:
    kwargs: dict[str, object] = {
        "trusted_public_keys": [FIXTURE_PUBLIC_KEY],
        "karmi_version": "0.1.0",
        "known_actions": SIM_ACTIONS,
        "expected_feature_schema_version": FEATURE_SCHEMA_VERSION,
    }
    kwargs.update(overrides)
    return load_bundle(path, **kwargs)  # type: ignore[arg-type]


def test_parakh_exported_bundle_verifies_and_scores_eligible_actions() -> None:
    loaded = _load(FIXTURE)
    probabilities = loaded.probabilities(CONTEXT, SIM_ACTIONS, explore=True)
    assert loaded.version == "policy-2026.09.27.1"
    assert set(probabilities) == set(SIM_ACTIONS)
    assert sum(probabilities.values()) == pytest.approx(1.0)
    # epsilon 0.05 over three actions: greedy gets 1 - eps + eps/3, others eps/3.
    assert sorted(probabilities.values()) == pytest.approx([0.05 / 3, 0.05 / 3, 1 - 0.05 + 0.05 / 3])
    decision = loaded.select(CONTEXT, ["sim/cheap"], random.Random(1), shadow=True)  # noqa: S311
    assert decision is not None
    assert decision["selected_action"] == "sim/cheap"
    assert decision["selection_probability"] == 1.0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"trusted_public_keys": [TEST_PUBLIC_KEY]}, "untrusted"),
        ({"known_actions": list(KNOWN_ACTIONS)}, "unknown models"),
        ({"expected_feature_schema_version": "routing-features.v2"}, "feature schema"),
        ({"karmi_version": "0.0.9"}, "too old"),
    ],
)
def test_incompatible_bundle_is_rejected(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(BundleRejected, match=message):
        _load(FIXTURE, **overrides)


def test_tampered_or_padded_bundle_is_rejected(tmp_path: Path) -> None:
    tampered = tmp_path / "tampered"
    shutil.copytree(FIXTURE, tampered)
    policy_path = tampered / "routing_policy.json"
    policy_path.chmod(0o644)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["alpha"] = 5.0
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(BundleRejected, match="checksum mismatch"):
        _load(tampered)

    padded = tmp_path / "padded"
    shutil.copytree(FIXTURE, padded)
    padded.chmod(0o755)
    (padded / "extra.py").write_text("print('not data')\n", encoding="utf-8")
    with pytest.raises(BundleRejected, match="file set mismatch"):
        _load(padded)


def test_resigned_bundle_needs_a_trusted_key(tmp_path: Path) -> None:
    root = make_karmi_bundle(tmp_path, "policy-test.1", bias={"karmi/fake-economy": 1.0})
    with pytest.raises(BundleRejected, match="untrusted"):
        _load(root, known_actions=KNOWN_ACTIONS)
    assert _load(root, known_actions=KNOWN_ACTIONS, trusted_public_keys=[TEST_PUBLIC_KEY])


def test_signed_bundle_with_malformed_parameters_is_rejected(tmp_path: Path) -> None:
    root = make_karmi_bundle(tmp_path, "policy-test.2", bias={"karmi/fake-economy": 1.0})
    policy = json.loads((root / "routing_policy.json").read_text(encoding="utf-8"))
    policy["parameters"]["karmi/fake-economy"]["theta"] = [1.0]
    (root / "routing_policy.json").write_text(json.dumps(policy), encoding="utf-8")
    sign_directory(root)
    with pytest.raises(BundleRejected, match="malformed parameters"):
        _load(root, known_actions=KNOWN_ACTIONS, trusted_public_keys=[TEST_PUBLIC_KEY])


def test_receiver_refuses_every_bundle_without_configured_trust(tmp_path: Path) -> None:
    settings = Settings(environment="test", data_dir=tmp_path)
    with pytest.raises(BundleRejected, match="no trusted Parakh signing keys"):
        verify_bundle(FIXTURE, settings)
    settings.parakh_trusted_public_keys = [FIXTURE_PUBLIC_KEY]
    with pytest.raises(BundleRejected, match="unknown models"):
        verify_bundle(FIXTURE, settings)


def test_every_plan_maps_to_contract_tier_and_unknown_plans_fail_closed() -> None:
    # A new plan without a contract tier would fail every message on it: this catches it in CI.
    assert {p: contract_tier(p) for p in SYNTHETIC_POLICIES} == {
        "ananta": "ananta", "yanta": "yanta", "trika": "trika", "parth": "part",
    }
    with pytest.raises(UnknownPlanError):
        contract_tier("enterprise")
