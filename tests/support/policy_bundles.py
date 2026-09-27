"""Synthetic PolicyBundleV1 test factory and tampering helpers (ADR-0003, ART-001).

Shared with end-to-end tests to generate signed, verifiable bundles or intentionally
tampered artifacts.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from daily_agent.policy_artifacts import scoring
from daily_agent.policy_artifacts.schema import (
    FEATURE_SCHEMA,
    HARNESS_PROMPTS,
    HARNESS_RECOVERY,
    MANIFEST,
    PROVENANCE,
    ROUTER_METADATA,
    ROUTING_POLICY,
    LinUCBPolicyV1,
)
from daily_agent.routing.models import FEATURE_NAMES_V1, FEATURE_SCHEMA_VERSION


def generate_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Generate an Ed25519 private key and its base64-encoded raw public key."""
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key_b64 = base64.b64encode(public_bytes).decode("ascii")
    return private_key, public_key_b64


def default_arms(dimension: int = len(FEATURE_NAMES_V1)) -> dict[str, dict[str, Any]]:
    """Return default arms for fake-economy and typesafe-system-one.

    Theta ensures fake-economy wins for [1.0] + [0.0] * (dimension - 1).
    """
    eye = [[1.0 if i == j else 0.0 for j in range(dimension)] for i in range(dimension)]
    theta_fake = [2.0] + [0.0] * (dimension - 1)
    theta_typesafe = [1.0] + [0.0] * (dimension - 1)
    return {
        "fake-economy": {
            "theta": theta_fake,
            "a_inv": eye,
        },
        "typesafe-system-one": {
            "theta": theta_typesafe,
            "a_inv": eye,
        },
    }


def write_bundle(
    dir: Path,
    *,
    private_key: Ed25519PrivateKey,
    version: str = "test-1",
    arms: dict[str, dict[str, Any]] | None = None,
    alpha: float = 0.0,
    harness: bool = False,
    passed_regression: bool = True,
    min_karmi_version: str = "0.1.0",
    tier_restrictions: dict[str, list[str]] | None = None,
    mutate: Callable[[dict[str, Any]], None] | None = None,
    model_registry: list[str] | None = None,
    created_at: str = "2026-09-27T00:00:00Z",
    self_test_cases: list[dict[str, Any]] | None = None,
    feature_schema_version: str = FEATURE_SCHEMA_VERSION,
    feature_names: list[str] | None = None,
    skip_checksums: bool = False,
    skip_signature: bool = False,
) -> Path:
    """Build a complete, signed PolicyBundleV1 directory."""
    bundle_path = Path(dir)
    bundle_path.mkdir(parents=True, exist_ok=True)

    arms_data = arms if arms is not None else default_arms()
    registry_data = model_registry if model_registry is not None else sorted(arms_data.keys())

    policy_doc: dict[str, Any] = {
        "schema": "LinUCBPolicyV1",
        "feature_schema_version": feature_schema_version,
        "alpha": alpha,
        "arms": arms_data,
    }

    manifest_doc: dict[str, Any] = {
        "schema": "PolicyBundleV1",
        "artifact_version": version,
        "policy_schema_version": "LinUCBPolicyV1",
        "feature_schema_version": feature_schema_version,
        "algorithm": "linucb",
        "min_karmi_version": min_karmi_version,
        "model_registry": registry_data,
        "evaluation_run_ids": ["eval-run-1"],
        "created_at": created_at,
        "previous_compatible_version": None,
        "harness_included": harness,
        "tier_restrictions": tier_restrictions or {},
    }

    feature_schema_doc: dict[str, Any] = {
        "schema": "RoutingFeatureSchemaV1",
        "feature_schema_version": feature_schema_version,
        "feature_names": feature_names if feature_names is not None else list(FEATURE_NAMES_V1),
    }

    if self_test_cases is None:
        dim = len(next(iter(arms_data.values()))["theta"])
        vec = [1.0] + [0.0] * (dim - 1)
        temp_policy = LinUCBPolicyV1.model_validate(policy_doc)
        expected = scoring.greedy_model(temp_policy, registry_data, vec)
        if expected is None:
            expected = registry_data[0]
        cases: list[dict[str, Any]] = [
            {
                "feature_vector": vec,
                "eligible_models": registry_data,
                "expected_model": expected,
            },
        ]
    else:
        cases = self_test_cases

    metadata_doc: dict[str, Any] = {
        "schema": "RouterMetadataV1",
        "description": "Synthetic test bundle",
        "self_test_cases": cases,
    }

    evaluation_doc: dict[str, Any] = {
        "schema": "EvaluationSummaryV1",
        "evaluation_run_ids": ["eval-run-1"],
        "metrics": {"mean_reward": 0.85},
        "passed_regression": passed_regression,
    }

    provenance_doc: dict[str, Any] = {
        "schema": "ProvenanceV1",
        "producer_repo": "rossonerian-parakh",
        "producer_version": "0.1.0",
        "telemetry_batch_ids": ["batch-1"],
        "benchmark_ids": ["bench-1"],
    }

    docs: dict[str, Any] = {
        MANIFEST: manifest_doc,
        ROUTING_POLICY: policy_doc,
        ROUTER_METADATA: metadata_doc,
        FEATURE_SCHEMA: feature_schema_doc,
        "evaluation_summary.json": evaluation_doc,
        PROVENANCE: provenance_doc,
    }

    if harness:
        docs[HARNESS_PROMPTS] = {
            "schema": "HarnessPromptsV1",
            "prompt_version": "v1",
            "intent_instructions": "Classify user intent.",
            "intent_criteria": {
                "query_memory": "User queries notes.",
                "store_memory": "User stores a note.",
                "create_task": "User schedules a task.",
                "general_draft": "User asks for general draft.",
            },
            "relevance_instructions_template": "Score relevance of {note_ref} to query.",
            "relevance_criteria": ["low", "medium", "high"],
        }
        docs[HARNESS_RECOVERY] = {
            "schema": "RecoveryPolicyV1",
            "max_provider_retries": 1,
            "fallback_to_local": True,
        }

    if mutate is not None:
        mutate(docs)

    # Write payload files
    for rel_path, doc in docs.items():
        file_path = bundle_path / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(doc, bytes):
            file_path.write_bytes(doc)
        elif isinstance(doc, str):
            file_path.write_text(doc, encoding="utf-8")
        else:
            file_path.write_bytes(json.dumps(doc, indent=2).encode("utf-8"))

    if skip_checksums:
        return bundle_path

    # Compute sha256 checksums for present files
    checksums_map: dict[str, str] = {}
    for root, _dirs, files in os.walk(bundle_path):
        for f in files:
            p = Path(root) / f
            rel = p.relative_to(bundle_path).as_posix()
            if rel in ("checksums.json", "signature.sig"):
                continue
            checksums_map[rel] = hashlib.sha256(p.read_bytes()).hexdigest()

    checksums_doc = {
        "schema": "ChecksumsV1",
        "algorithm": "sha256",
        "files": checksums_map,
    }
    checksums_bytes = json.dumps(checksums_doc, indent=2).encode("utf-8")
    (bundle_path / "checksums.json").write_bytes(checksums_bytes)

    if skip_signature:
        return bundle_path

    sig_bytes = private_key.sign(checksums_bytes)
    sig_b64 = base64.b64encode(sig_bytes).decode("ascii")
    (bundle_path / "signature.sig").write_text(sig_b64, encoding="utf-8")

    return bundle_path


def tamper_file(bundle_dir: Path, rel_path: str, content: str | bytes) -> None:
    """Overwrite a file in an already signed bundle."""
    target = bundle_dir / rel_path
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)


def add_extra_file(
    bundle_dir: Path,
    rel_path: str = "extra.txt",
    content: str | bytes = "unexpected",
) -> Path:
    """Add an unexpected file into an already signed bundle."""
    target = bundle_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        target.write_text(content, encoding="utf-8")
    else:
        target.write_bytes(content)
    return target


def add_symlink(bundle_dir: Path, link_name: str, target: Path | None = None) -> bool:
    """Attempt to create a symlink in bundle_dir; returns False if unsupported by OS."""
    link_path = bundle_dir / link_name
    dest = target if target is not None else bundle_dir / MANIFEST
    try:
        os.symlink(dest, link_path)
        return True
    except (OSError, NotImplementedError):
        return False
