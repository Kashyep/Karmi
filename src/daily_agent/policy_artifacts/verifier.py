"""PolicyBundleV1 verification (ADR-0003, ART-001).

Guarantees that untrusted artifacts produced by an external optimizer (Parakh)
are strictly validated before any learned policy is staged, shadowed, or promoted.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import hmac
import json
import math
import os
import stat
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import ValidationError

from daily_agent.policy_artifacts import scoring
from daily_agent.policy_artifacts.schema import (
    CHECKSUMS,
    EVALUATION_SUMMARY,
    FEATURE_SCHEMA,
    HARNESS_FILES,
    HARNESS_PROMPTS,
    HARNESS_RECOVERY,
    MANIFEST,
    MAX_FILE_BYTES,
    PROVENANCE,
    REQUIRED_FILES,
    ROUTER_METADATA,
    ROUTING_POLICY,
    SIGNATURE,
    ChecksumsV1,
    EvaluationSummaryV1,
    HarnessBundleV1,
    HarnessPromptsV1,
    LinUCBPolicyV1,
    LoadedBundle,
    PolicyBundleManifestV1,
    ProvenanceV1,
    RecoveryPolicyV1,
    RouterMetadataV1,
    RoutingFeatureSchemaV1,
)
from daily_agent.routing.models import FEATURE_NAMES_V1, FEATURE_SCHEMA_VERSION


class BundleRejected(Exception):
    """Raised when a candidate policy bundle fails verification."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _parse_semver(v: str) -> tuple[int, ...]:
    try:
        parts = v.split(".")
        return tuple(int(x) for x in parts)
    except Exception as e:
        raise ValueError(f"Invalid semver: {v}") from e


def _reject_constant(val: str) -> None:
    raise ValueError(f"Disallowed constant in strict JSON: {val}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _load_strict_json(raw: bytes, filename: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise BundleRejected("invalid_json", f"File {filename} is not valid UTF-8: {e}") from e
    try:
        return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except Exception as e:
        raise BundleRejected("invalid_json", f"File {filename} contains invalid JSON: {e}") from e


_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _read_regular_file(path: Path, rel_file: str) -> bytes:
    """Read one bundle file exactly once, refusing links, non-regular files and oversize.

    The returned bytes are the only copy that is hashed and parsed, so a file swapped
    on disk after the read cannot change what was verified.
    """
    try:
        fd = os.open(path, _OPEN_FLAGS)
    except OSError as e:
        code = "symlink" if e.errno == errno.ELOOP else "missing_file"
        raise BundleRejected(code, f"Cannot open {rel_file} safely: {e}") from e
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise BundleRejected("unexpected_file", f"{rel_file} is not a regular file")
        chunks: list[bytes] = []
        remaining = MAX_FILE_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1 << 16))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) > MAX_FILE_BYTES:
        raise BundleRejected(
            "file_too_large",
            f"File {rel_file} exceeds maximum size {MAX_FILE_BYTES} bytes",
        )
    return raw



def verify_bundle(
    path: Path,
    *,
    public_key_b64: str | None,
    known_models: Mapping[str, frozenset[str]],
    karmi_version: str,
    now: datetime,
) -> LoadedBundle:
    """Verify a policy bundle directory against strict cryptographic and semantic constraints."""
    target_path = Path(path)

    # 1. Path safety: path is a real directory (not a symlink/junction).
    if target_path.is_symlink() or (
        hasattr(target_path, "is_junction") and target_path.is_junction()
    ):
        raise BundleRejected("symlink", f"Path is a symlink: {target_path}")

    if not target_path.exists() or not target_path.is_dir():
        raise BundleRejected("not_a_directory", f"Path is not a directory: {target_path}")

    present_files: set[str] = set()
    for root, dirs, files in os.walk(target_path, followlinks=False):
        root_path = Path(root)
        for d in dirs:
            dir_path = root_path / d
            if dir_path.is_symlink() or (
                hasattr(dir_path, "is_junction") and dir_path.is_junction()
            ):
                raise BundleRejected("symlink", f"Directory is a symlink: {dir_path}")
            rel_dir = dir_path.relative_to(target_path).as_posix()
            if rel_dir != "harness" and not rel_dir.startswith("harness/"):
                raise BundleRejected("unexpected_file", f"Unexpected directory in bundle: {rel_dir}")

        for f in files:
            file_path = root_path / f
            if file_path.is_symlink() or (
                hasattr(file_path, "is_junction") and file_path.is_junction()
            ):
                raise BundleRejected("symlink", f"File is a symlink: {file_path}")

            rel_file = file_path.relative_to(target_path).as_posix()
            if rel_file not in (REQUIRED_FILES | HARNESS_FILES):
                raise BundleRejected("unexpected_file", f"Unexpected file in bundle: {rel_file}")

            st = file_path.stat(follow_symlinks=False)
            if st.st_size > MAX_FILE_BYTES:
                raise BundleRejected(
                    "file_too_large",
                    f"File {rel_file} exceeds maximum size {MAX_FILE_BYTES} bytes ({st.st_size})",
                )
            present_files.add(rel_file)

    # Snapshot every file exactly once; all hashing and parsing below uses these bytes.
    contents = {
        rel_file: _read_regular_file(target_path / rel_file, rel_file)
        for rel_file in sorted(present_files)
    }

    # 2. Required files present.
    missing_required = REQUIRED_FILES - present_files
    if missing_required:
        missing_names = ", ".join(sorted(missing_required))
        raise BundleRejected("missing_file", f"Missing required file(s): {missing_names}")

    harness_present_count = len(present_files & HARNESS_FILES)
    if 0 < harness_present_count < len(HARNESS_FILES):
        raise BundleRejected(
            "harness_mismatch",
            "Bundle contains incomplete harness files; both harness files or neither must be present",
        )

    # 3. Signature: public key is base64 of 32 raw Ed25519 bytes; verify over checksums.json bytes.
    if not public_key_b64:
        raise BundleRejected("bad_public_key", "Missing public key")

    try:
        key_bytes = base64.b64decode(public_key_b64, validate=True)
        if len(key_bytes) != 32:
            raise ValueError(f"Public key length is {len(key_bytes)}, expected 32 bytes")
        public_key = Ed25519PublicKey.from_public_bytes(key_bytes)
    except Exception as e:
        raise BundleRejected("bad_public_key", f"Invalid public key: {e}") from e

    checksums_raw = contents[CHECKSUMS]

    try:
        sig_text = contents[SIGNATURE].decode("utf-8").strip()
        sig_bytes = base64.b64decode(sig_text, validate=True)
    except Exception as e:
        raise BundleRejected("bad_signature", f"Cannot decode signature.sig: {e}") from e

    try:
        public_key.verify(sig_bytes, checksums_raw)
    except InvalidSignature as e:
        raise BundleRejected("bad_signature", "Signature does not match checksums.json") from e
    except Exception as e:
        raise BundleRejected("bad_signature", f"Signature verification error: {e}") from e

    # 4. ChecksumsV1: listed files must equal present files minus checksums.json/signature.sig;
    # every sha256 matches.
    checksums_data = _load_strict_json(checksums_raw, CHECKSUMS)
    try:
        checksums_model = ChecksumsV1.model_validate(checksums_data)
    except ValidationError as e:
        raise BundleRejected("schema_invalid", f"checksums.json failed schema validation: {e}") from e

    expected_checksum_files = present_files - {CHECKSUMS, SIGNATURE}
    if set(checksums_model.files.keys()) != expected_checksum_files:
        raise BundleRejected(
            "bad_checksums",
            "Files listed in checksums.json do not match bundle contents",
        )

    for rel_file, expected_sha in checksums_model.files.items():
        file_bytes = contents[rel_file]
        actual_sha = hashlib.sha256(file_bytes).hexdigest()
        if not hmac.compare_digest(actual_sha, expected_sha):
            raise BundleRejected(
                "checksum_mismatch",
                f"Checksum mismatch for {rel_file}: expected {expected_sha}, computed {actual_sha}",
            )

    # 5. Parse JSON strictly: UTF-8, reject NaN/Infinity, validate Pydantic model for each file.
    manifest_data = _load_strict_json(contents[MANIFEST], MANIFEST)
    try:
        manifest = PolicyBundleManifestV1.model_validate(manifest_data)
    except ValidationError as e:
        raise BundleRejected("schema_invalid", f"manifest.json failed schema validation: {e}") from e

    # Harness presence check against manifest.harness_included
    if manifest.harness_included:
        if not HARNESS_FILES.issubset(present_files):
            raise BundleRejected(
                "harness_mismatch",
                "manifest.harness_included is True but harness files are missing",
            )
        prompts_data = _load_strict_json(contents[HARNESS_PROMPTS], HARNESS_PROMPTS)
        try:
            harness_prompts = HarnessPromptsV1.model_validate(prompts_data)
        except ValidationError as e:
            raise BundleRejected(
                "schema_invalid",
                f"harness/prompts.json failed schema validation: {e}",
            ) from e

        recovery_data = _load_strict_json(contents[HARNESS_RECOVERY], HARNESS_RECOVERY)
        try:
            recovery_policy = RecoveryPolicyV1.model_validate(recovery_data)
        except ValidationError as e:
            raise BundleRejected(
                "schema_invalid",
                f"harness/recovery_policy.json failed schema validation: {e}",
            ) from e

        harness_bundle: HarnessBundleV1 | None = HarnessBundleV1(
            prompts=harness_prompts,
            recovery=recovery_policy,
        )
    else:
        if present_files & HARNESS_FILES:
            raise BundleRejected(
                "harness_mismatch",
                "manifest.harness_included is False but harness files are present",
            )
        harness_bundle = None

    policy_data = _load_strict_json(contents[ROUTING_POLICY], ROUTING_POLICY)
    try:
        policy = LinUCBPolicyV1.model_validate(policy_data)
    except ValidationError as e:
        raise BundleRejected(
            "schema_invalid",
            f"routing_policy.json failed schema validation: {e}",
        ) from e

    metadata_data = _load_strict_json(contents[ROUTER_METADATA], ROUTER_METADATA)
    try:
        metadata = RouterMetadataV1.model_validate(metadata_data)
    except ValidationError as e:
        raise BundleRejected(
            "schema_invalid",
            f"router_metadata.json failed schema validation: {e}",
        ) from e

    feature_schema_data = _load_strict_json(contents[FEATURE_SCHEMA], FEATURE_SCHEMA)
    try:
        feature_schema = RoutingFeatureSchemaV1.model_validate(feature_schema_data)
    except ValidationError as e:
        raise BundleRejected(
            "schema_invalid",
            f"feature_schema.json failed schema validation: {e}",
        ) from e

    evaluation_data = _load_strict_json(contents[EVALUATION_SUMMARY], EVALUATION_SUMMARY)
    try:
        evaluation = EvaluationSummaryV1.model_validate(evaluation_data)
    except ValidationError as e:
        raise BundleRejected(
            "schema_invalid",
            f"evaluation_summary.json failed schema validation: {e}",
        ) from e

    provenance_data = _load_strict_json(contents[PROVENANCE], PROVENANCE)
    try:
        provenance = ProvenanceV1.model_validate(provenance_data)
    except ValidationError as e:
        raise BundleRejected(
            "schema_invalid",
            f"provenance.json failed schema validation: {e}",
        ) from e

    # 6. Compatibility:
    # manifest/policy/feature-schema versions all equal FEATURE_SCHEMA_VERSION;
    # feature_schema.feature_names == list(FEATURE_NAMES_V1);
    # policy.dimension == len(FEATURE_NAMES_V1);
    # set(policy.arms) == set(manifest.model_registry) (arm_mismatch);
    # each model id in known_models (unknown_model);
    # tier_restrictions keys in model_registry and tiers subset of known_models[model] (tier_widening);
    # min_karmi_version <= karmi_version (numeric tuple compare).
    if (
        manifest.feature_schema_version != FEATURE_SCHEMA_VERSION
        or policy.feature_schema_version != FEATURE_SCHEMA_VERSION
        or feature_schema.feature_schema_version != FEATURE_SCHEMA_VERSION
        or feature_schema.feature_names != list(FEATURE_NAMES_V1)
    ):
        raise BundleRejected(
            "feature_schema_mismatch",
            f"Feature schema or version mismatch: expected {FEATURE_SCHEMA_VERSION}",
        )

    if policy.dimension != len(FEATURE_NAMES_V1):
        raise BundleRejected(
            "dimension_mismatch",
            f"Policy dimension {policy.dimension} != expected {len(FEATURE_NAMES_V1)}",
        )

    if set(policy.arms.keys()) != set(manifest.model_registry):
        raise BundleRejected(
            "arm_mismatch",
            f"Policy arms {set(policy.arms.keys())} != manifest model_registry {set(manifest.model_registry)}",
        )

    for model_id in manifest.model_registry:
        if model_id not in known_models:
            raise BundleRejected("unknown_model", f"Model '{model_id}' is not in known_models")

    for model_id, tiers in manifest.tier_restrictions.items():
        if model_id not in manifest.model_registry:
            raise BundleRejected(
                "tier_widening",
                f"Model '{model_id}' in tier_restrictions is not in manifest.model_registry",
            )
        entitled_tiers = known_models.get(model_id, frozenset())
        if not set(tiers).issubset(entitled_tiers):
            widened = set(tiers) - entitled_tiers
            raise BundleRejected(
                "tier_widening",
                f"Tier restrictions for model '{model_id}' widen entitlements: {widened}",
            )

    if _parse_semver(manifest.min_karmi_version) > _parse_semver(karmi_version):
        raise BundleRejected(
            "karmi_too_old",
            f"Bundle min_karmi_version {manifest.min_karmi_version} > Karmi version {karmi_version}",
        )

    # 7. Self-test: for each self_test_cases entry:
    # vector length equals dimension, eligible models subset of arms,
    # scoring.greedy_model(policy, eligible, vector) == expected_model; every score finite.
    for idx, test_case in enumerate(metadata.self_test_cases):
        if len(test_case.feature_vector) != policy.dimension:
            raise BundleRejected(
                "dimension_mismatch",
                f"Self-test case {idx} feature vector dimension {len(test_case.feature_vector)} != policy dimension {policy.dimension}",
            )
        if not set(test_case.eligible_models).issubset(policy.arms.keys()):
            raise BundleRejected(
                "self_test_failed",
                f"Self-test case {idx} eligible models {test_case.eligible_models} not in arms {set(policy.arms.keys())}",
            )
        for model in test_case.eligible_models:
            try:
                score = scoring.linucb_score(policy, model, test_case.feature_vector)
                if not math.isfinite(score):
                    raise ValueError(f"Score for model '{model}' is non-finite: {score}")
            except Exception as e:
                raise BundleRejected(
                    "self_test_failed",
                    f"Self-test case {idx} score error for model '{model}': {e}",
                ) from e

        chosen = scoring.greedy_model(policy, test_case.eligible_models, test_case.feature_vector)
        if chosen != test_case.expected_model:
            raise BundleRejected(
                "self_test_failed",
                f"Self-test case {idx} disagreement: expected '{test_case.expected_model}', got '{chosen}'",
            )

    # 8. Return LoadedBundle
    content_sha256 = hashlib.sha256(checksums_raw).hexdigest()
    return LoadedBundle(
        manifest=manifest,
        policy=policy,
        metadata=metadata,
        feature_schema=feature_schema,
        evaluation=evaluation,
        provenance=provenance,
        harness=harness_bundle,
        content_sha256=content_sha256,
        verified_at=now,
    )
