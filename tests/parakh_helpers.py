"""Build signed PolicyBundleV1 directories over Karmi's own actions for tests.

The feature schema and supporting documents are taken verbatim from the Parakh-exported
fixture, so these bundles differ from a real Parakh export only in their actions/parameters.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from daily_agent.parakh import ed25519

FIXTURE = Path(__file__).parent / "fixtures" / "parakh" / "policy-2026.09.27.1"
FIXTURE_PUBLIC_KEY = "8588d3d16dfd2a08e691a8da48aea9925f4dea853ba036477593dcdcebbe21d5"
SIM_ACTIONS = ["sim/balanced", "sim/cheap", "sim/flagship"]
TEST_SECRET = bytes(range(32))
TEST_PUBLIC_KEY = ed25519.public_key(TEST_SECRET).hex()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sign_directory(root: Path, secret: bytes = TEST_SECRET) -> None:
    """(Re)write checksums.json and signature.sig for every other file under ``root``."""
    files = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name not in ("checksums.json", "signature.sig")
    }
    checksums = _canonical({"algorithm": "sha256", "files": files})
    (root / "checksums.json").write_bytes(checksums)
    signature = {
        "algorithm": "ed25519",
        "public_key": ed25519.public_key(secret).hex(),
        "signature": ed25519.sign(secret, checksums).hex(),
        "signed_file": "checksums.json",
    }
    (root / "signature.sig").write_bytes(_canonical(signature))


def make_karmi_bundle(
    parent: Path,
    version: str,
    *,
    bias: dict[str, float],
    epsilon: float = 0.0,
    secret: bytes = TEST_SECRET,
    minimum_karmi_version: str = "0.1.0",
) -> Path:
    """A LinUCB bundle whose score for each Karmi action is its constant ``bias`` weight."""
    root = parent / version
    root.mkdir(parents=True)
    features = json.loads((FIXTURE / "feature_schema.json").read_text(encoding="utf-8"))
    d = len(features["features"])
    identity = [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]
    actions = sorted(bias)
    policy = {
        "actions": actions,
        "algorithm": "linucb",
        "alpha": 0.0,
        "exploration": {"epsilon": epsilon, "mode": "epsilon_greedy" if epsilon else "none"},
        "fallback": "static",
        "feature_dimension": d,
        "feature_schema_version": features["feature_schema_version"],
        "parameters": {
            a: {"theta": [bias[a]] + [0.0] * (d - 1), "a_inv": identity, "n": 1, "weight_sum": 1.0}
            for a in actions
        },
        "policy_schema_version": "linucb.v1",
    }
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    manifest.update({
        "artifact_version": version,
        "minimum_karmi_version": minimum_karmi_version,
        "model_registry": [
            {"action": a, "provider": a.split("/")[0], "model": a.split("/")[1]} for a in actions
        ],
    })
    documents = {"manifest.json": manifest, "routing_policy.json": policy,
                 "feature_schema.json": features}
    for name in ("eligibility_constraints.json", "evaluation.json", "provenance.json"):
        documents[name] = json.loads((FIXTURE / name).read_text(encoding="utf-8"))
    for name, document in documents.items():
        (root / name).write_bytes(_canonical(document))
    sign_directory(root, secret)
    return root
