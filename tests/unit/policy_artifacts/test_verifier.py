"""Unit tests for PolicyBundleV1 verifier (ADR-0003, ART-001)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from daily_agent.policy_artifacts.schema import (
    EVALUATION_SUMMARY,
    HARNESS_PROMPTS,
    HARNESS_RECOVERY,
    MANIFEST,
    MAX_FILE_BYTES,
    ROUTING_POLICY,
    SIGNATURE,
)
from daily_agent.policy_artifacts.verifier import BundleRejected, _load_strict_json, verify_bundle
from daily_agent.routing.models import FEATURE_NAMES_V1
from daily_agent.routing.registry import entitlement_map
from tests.support.policy_bundles import (
    add_extra_file,
    add_symlink,
    generate_keypair,
    tamper_file,
    write_bundle,
)

KNOWN_MODELS = entitlement_map()
KARMI_VERSION = "0.1.0"
NOW = datetime.now(UTC)


def test_reject_duplicate_json_keys() -> None:
    # Different JSON parsers can disagree about duplicate fields in a signed document.
    with pytest.raises(BundleRejected) as exc:
        _load_strict_json(b'{"algorithm":"sha256","algorithm":"md5"}', "checksums.json")
    assert exc.value.code == "invalid_json"


def test_verify_valid_bundle(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b1", private_key=priv, version="test-1")
    loaded = verify_bundle(
        bundle_dir,
        public_key_b64=pub,
        known_models=KNOWN_MODELS,
        karmi_version=KARMI_VERSION,
        now=NOW,
    )
    assert loaded.manifest.artifact_version == "test-1"
    assert loaded.harness is None
    assert len(loaded.content_sha256) == 64
    assert loaded.verified_at == NOW


def test_verify_valid_bundle_with_harness(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b_harness", private_key=priv, harness=True)
    loaded = verify_bundle(
        bundle_dir,
        public_key_b64=pub,
        known_models=KNOWN_MODELS,
        karmi_version=KARMI_VERSION,
        now=NOW,
    )
    assert loaded.harness is not None
    assert loaded.harness.recovery.max_provider_retries == 1


# --- Test every single rejection code ---


def test_reject_not_a_directory(tmp_path: Path) -> None:
    _priv, pub = generate_keypair()
    non_existent = tmp_path / "does_not_exist"
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            non_existent,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "not_a_directory"

    # Also test when path is a regular file
    regular_file = tmp_path / "regular.txt"
    regular_file.write_text("hello", encoding="utf-8")
    with pytest.raises(BundleRejected) as exc2:
        verify_bundle(
            regular_file,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc2.value.code == "not_a_directory"


def test_reject_symlink(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b_sym", private_key=priv)

    if not add_symlink(bundle_dir, "symlink_file.json"):
        pytest.skip("Symlinks not supported on this platform/user privilege")

    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "symlink"


def test_reject_unexpected_file(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b_unexp", private_key=priv)
    add_extra_file(bundle_dir, "unexpected.txt", "unwanted content")
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "unexpected_file"


def test_reject_missing_file(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b_miss", private_key=priv)
    (bundle_dir / EVALUATION_SUMMARY).unlink()
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "missing_file"


def test_reject_file_too_large(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b_large", private_key=priv)
    # Overwrite manifest with data exceeding MAX_FILE_BYTES
    large_content = b" " * (MAX_FILE_BYTES + 10)
    (bundle_dir / MANIFEST).write_bytes(large_content)
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "file_too_large"


def test_reject_bad_public_key(tmp_path: Path) -> None:
    priv, _pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b_bad_pk", private_key=priv)

    # Missing public key
    with pytest.raises(BundleRejected) as exc1:
        verify_bundle(
            bundle_dir,
            public_key_b64=None,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc1.value.code == "bad_public_key"

    # Invalid length public key
    with pytest.raises(BundleRejected) as exc2:
        verify_bundle(
            bundle_dir,
            public_key_b64="bm90LWEtdmFsaWQtMzItYnl0ZS1rZXk=",  # not 32 bytes
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc2.value.code == "bad_public_key"


def test_reject_bad_signature(tmp_path: Path) -> None:
    priv1, _pub1 = generate_keypair()
    _priv2, pub2 = generate_keypair()
    # Signed with priv1, verified with pub2
    bundle_dir = write_bundle(tmp_path / "b_bad_sig", private_key=priv1)
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub2,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "bad_signature"

    # Corrupt base64 in signature.sig
    tamper_file(bundle_dir, SIGNATURE, "@@@NotBase64@@@")
    with pytest.raises(BundleRejected) as exc2:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub2,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc2.value.code == "bad_signature"


def test_reject_bad_checksums(tmp_path: Path) -> None:
    priv, pub = generate_keypair()

    # ChecksumsV1 lists an extra file not in bundle
    def mutate_checksums(docs: dict[str, object]) -> None:
        pass

    bundle_dir = write_bundle(tmp_path / "b_bad_csums", private_key=priv, mutate=mutate_checksums)

    # Re-write checksums.json with an extra file and re-sign with correct key
    import base64
    import json
    csums_path = bundle_dir / "checksums.json"
    csums_data = json.loads(csums_path.read_text(encoding="utf-8"))
    csums_data["files"]["ghost_file.json"] = "a" * 64
    csums_bytes = json.dumps(csums_data).encode("utf-8")
    csums_path.write_bytes(csums_bytes)
    sig_b64 = base64.b64encode(priv.sign(csums_bytes)).decode("ascii")
    (bundle_dir / SIGNATURE).write_text(sig_b64, encoding="utf-8")

    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "bad_checksums"


def test_reject_checksum_mismatch(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(tmp_path / "b_csum_mismatch", private_key=priv)
    # Modify a file after checksums and signature are written
    tamper_file(bundle_dir, MANIFEST, '{"tampered": true}')
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "checksum_mismatch"


def test_reject_invalid_json(tmp_path: Path) -> None:
    priv, pub = generate_keypair()

    # NaN in JSON
    def mutate_nan(docs: dict[str, object]) -> None:
        docs[ROUTING_POLICY] = '{"schema": "LinUCBPolicyV1", "alpha": NaN}'

    bundle_dir = write_bundle(tmp_path / "b_nan", private_key=priv, mutate=mutate_nan)
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "invalid_json"

    # Invalid UTF-8
    def mutate_utf8(docs: dict[str, object]) -> None:
        docs[MANIFEST] = b"\x80\x81\x82 invalid utf-8"

    bundle_dir_utf8 = write_bundle(tmp_path / "b_utf8", private_key=priv, mutate=mutate_utf8)
    with pytest.raises(BundleRejected) as exc2:
        verify_bundle(
            bundle_dir_utf8,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc2.value.code == "invalid_json"


def test_reject_schema_invalid(tmp_path: Path) -> None:
    priv, pub = generate_keypair()

    def mutate_schema(docs: dict[str, object]) -> None:
        # manifest has invalid schema field
        manifest_doc = docs[MANIFEST]
        assert isinstance(manifest_doc, dict)
        manifest_doc["schema"] = "InvalidSchemaName"

    bundle_dir = write_bundle(tmp_path / "b_schema_inv", private_key=priv, mutate=mutate_schema)
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "schema_invalid"


def test_reject_feature_schema_mismatch(tmp_path: Path) -> None:
    priv, pub = generate_keypair()

    # Feature schema version mismatch
    bundle_dir = write_bundle(
        tmp_path / "b_f_ver",
        private_key=priv,
        feature_schema_version="routing-features-v0",
    )
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "feature_schema_mismatch"

    # Feature names mismatch
    bundle_dir_names = write_bundle(
        tmp_path / "b_f_names",
        private_key=priv,
        feature_names=["bias", "wrong_feature_name"],
    )
    with pytest.raises(BundleRejected) as exc2:
        verify_bundle(
            bundle_dir_names,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc2.value.code == "feature_schema_mismatch"


def test_reject_dimension_mismatch(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    # Arms with wrong dimension (e.g. 5 instead of 21)
    wrong_dim_arms = {
        "fake-economy": {
            "theta": [1.0, 0.0, 0.0, 0.0, 0.0],
            "a_inv": [[1.0 if i == j else 0.0 for j in range(5)] for i in range(5)],
        },
        "typesafe-system-one": {
            "theta": [1.0, 0.0, 0.0, 0.0, 0.0],
            "a_inv": [[1.0 if i == j else 0.0 for j in range(5)] for i in range(5)],
        },
    }
    bundle_dir = write_bundle(tmp_path / "b_dim", private_key=priv, arms=wrong_dim_arms)
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "dimension_mismatch"


def test_reject_unknown_model(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    dim = len(FEATURE_NAMES_V1)
    unknown_arms = {
        "unregistered-exotic-model": {
            "theta": [1.0] * dim,
            "a_inv": [[1.0 if i == j else 0.0 for j in range(dim)] for i in range(dim)],
        },
    }
    bundle_dir = write_bundle(tmp_path / "b_unknown_model", private_key=priv, arms=unknown_arms)
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "unknown_model"


def test_reject_arm_mismatch(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    # manifest model_registry differs from policy arms
    bundle_dir = write_bundle(
        tmp_path / "b_arm_mismatch",
        private_key=priv,
        model_registry=["fake-economy"],  # policy has fake-economy and typesafe-system-one
    )
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "arm_mismatch"


def test_reject_tier_widening(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    # Tier restriction contains a tier that is not entitled in known_models
    bundle_dir = write_bundle(
        tmp_path / "b_tier_widen",
        private_key=priv,
        tier_restrictions={"fake-economy": ["vip_ultra_tier"]},
    )
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "tier_widening"


def test_reject_karmi_too_old(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    bundle_dir = write_bundle(
        tmp_path / "b_too_old",
        private_key=priv,
        min_karmi_version="2.0.0",
    )
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version="0.1.0",
            now=NOW,
        )
    assert exc.value.code == "karmi_too_old"


def test_reject_harness_mismatch(tmp_path: Path) -> None:
    priv, pub = generate_keypair()

    # 1. Manifest says harness_included=True, but harness files not created
    def mutate_remove_harness(docs: dict[str, object]) -> None:
        docs.pop(HARNESS_PROMPTS, None)
        docs.pop(HARNESS_RECOVERY, None)

    bundle_dir1 = write_bundle(
        tmp_path / "b_harness_miss",
        private_key=priv,
        harness=True,
        mutate=mutate_remove_harness,
    )
    with pytest.raises(BundleRejected) as exc1:
        verify_bundle(
            bundle_dir1,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc1.value.code == "harness_mismatch"

    # 2. Manifest says harness_included=False, but harness files are present
    def mutate_add_harness(docs: dict[str, object]) -> None:
        manifest_doc = docs[MANIFEST]
        assert isinstance(manifest_doc, dict)
        manifest_doc["harness_included"] = False

    bundle_dir2 = write_bundle(
        tmp_path / "b_harness_unwanted",
        private_key=priv,
        harness=True,
        mutate=mutate_add_harness,
    )
    with pytest.raises(BundleRejected) as exc2:
        verify_bundle(
            bundle_dir2,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc2.value.code == "harness_mismatch"

    # 3. Only one harness file present
    def mutate_partial_harness(docs: dict[str, object]) -> None:
        docs.pop(HARNESS_RECOVERY, None)

    bundle_dir3 = write_bundle(
        tmp_path / "b_harness_partial",
        private_key=priv,
        harness=True,
        mutate=mutate_partial_harness,
    )
    with pytest.raises(BundleRejected) as exc3:
        verify_bundle(
            bundle_dir3,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc3.value.code == "harness_mismatch"


def test_reject_self_test_failed(tmp_path: Path) -> None:
    priv, pub = generate_keypair()
    # Provide self-test case where expected_model disagrees with greedy_model
    dim = len(FEATURE_NAMES_V1)
    bad_self_test = [
        {
            "feature_vector": [1.0] + [0.0] * (dim - 1),
            "eligible_models": ["fake-economy", "typesafe-system-one"],
            "expected_model": "typesafe-system-one",  # fake-economy has higher theta dot product!
        },
    ]
    bundle_dir = write_bundle(
        tmp_path / "b_self_test",
        private_key=priv,
        self_test_cases=bad_self_test,
    )
    with pytest.raises(BundleRejected) as exc:
        verify_bundle(
            bundle_dir,
            public_key_b64=pub,
            known_models=KNOWN_MODELS,
            karmi_version=KARMI_VERSION,
            now=NOW,
        )
    assert exc.value.code == "self_test_failed"
