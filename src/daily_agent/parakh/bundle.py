"""PolicyBundleV1 verification and scoring (consumer side of Parakh's artifact contract).

Typed port of Parakh ``contracts/karmi_reference/loader.py`` (Parakh 41674dd). Order:
signature over ``checksums.json`` with a trusted key -> every file's SHA-256 and no extra
files -> artifact/policy schema -> feature schema -> known model ids -> minimum Karmi
version -> parameter self-test. Any failure raises :class:`BundleRejected`; nothing here
touches the database or the live route.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from daily_agent.parakh import ed25519

SUPPORTED_ARTIFACT_MAJOR = "1"
SUPPORTED_POLICY_SCHEMAS = frozenset({"linucb.v1"})
REQUIRED_FILES = (
    "manifest.json",
    "routing_policy.json",
    "feature_schema.json",
    "eligibility_constraints.json",
    "evaluation.json",
    "provenance.json",
)
_PROBE_CONTEXT: dict[str, Any] = {
    "tier": "probe", "task_domain": "probe", "estimated_input_tokens": 0,
    "context_utilization_ratio": 0.0, "tool_count": 0, "requires_structured_output": False,
    "requires_tools": False, "requires_memory": False, "requires_external_data": False,
    "conversation_depth": 0, "retry_number": 0, "previous_tool_failure": False,
}


class BundleRejected(Exception):
    """Invalid artifact: reject it and keep the current policy."""


def _version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _apply(spec: Mapping[str, Any], context: Mapping[str, Any]) -> float:
    kind = spec["transform"]
    if kind == "constant":
        return float(spec["value"])
    value = context.get(spec["source"])
    if kind == "present":
        return 0.0 if value is None else 1.0
    if value is None:
        if spec["source"] == "latency_slo_ms":
            return 0.0
        raise ValueError(f"missing feature source {spec['source']}")
    if kind == "equals":
        return 1.0 if value == spec["value"] else 0.0
    if kind == "not_in":
        return 0.0 if value in spec["values"] else 1.0
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{spec['source']} must be boolean")
        return 1.0 if value else 0.0
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{spec['source']} must be numeric")
    if kind == "clip01":
        return min(1.0, max(0.0, float(value)))
    if kind == "capped_ratio":
        return min(1.0, max(0.0, float(value) / float(spec["cap"])))
    if kind == "log1p_scaled":
        return min(1.0, math.log1p(max(0.0, float(value))) / math.log1p(float(spec["scale"])))
    raise ValueError(f"unknown transform {kind}")


@dataclass(frozen=True)
class LoadedPolicy:
    manifest: dict[str, Any]
    policy: dict[str, Any]
    feature_schema: dict[str, Any]
    checksums_sha256: str
    signer_public_key: str

    @property
    def version(self) -> str:
        return str(self.manifest["artifact_version"])

    def features(self, context: Mapping[str, Any]) -> list[float]:
        return [_apply(spec, context) for spec in self.feature_schema["features"]]

    def _scores(self, x: Sequence[float], eligible: Iterable[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for action in sorted(set(eligible) & set(self.policy["actions"])):
            params = self.policy["parameters"][action]
            mean = sum(t * v for t, v in zip(params["theta"], x, strict=True))
            a_inv = params["a_inv"]
            n = len(x)
            variance = sum(x[i] * sum(a_inv[i][j] * x[j] for j in range(n)) for i in range(n))
            scores[action] = mean + float(self.policy["alpha"]) * math.sqrt(max(0.0, variance))
        return scores

    def probabilities(
        self, context: Mapping[str, Any], eligible: Sequence[str], *, explore: bool = False
    ) -> dict[str, float]:
        """Distribution over eligible known actions only; ``{}`` means the policy cannot score."""
        scores = self._scores(self.features(context), eligible)
        if not scores:
            return {}
        best = max(scores.values())
        greedy = min(a for a, s in scores.items() if s == best)
        exploration = self.policy["exploration"]
        epsilon = (
            float(exploration["epsilon"])
            if explore and exploration["mode"] == "epsilon_greedy"
            else 0.0
        )
        k = len(scores)
        return {a: (1 - epsilon + epsilon / k) if a == greedy else epsilon / k for a in scores}

    def select(
        self,
        context: Mapping[str, Any],
        eligible: Sequence[str],
        rng: random.Random,
        *,
        shadow: bool,
        explore: bool = False,
    ) -> dict[str, Any] | None:
        """A decision with its exact selection probability, or ``None`` if unscorable."""
        try:
            distribution = self.probabilities(context, eligible, explore=explore)
        except ValueError:
            return None
        if not distribution:
            return None
        actions = sorted(distribution)
        draw, cumulative, chosen = rng.random(), 0.0, actions[-1]
        for action in actions:
            cumulative += distribution[action]
            if draw < cumulative:
                chosen = action
                break
        greedy = max(actions, key=distribution.__getitem__)
        return {
            "selected_action": chosen,
            "selection_probability": distribution[chosen],
            "exploration": chosen != greedy,
            "policy_version": self.version,
            "eligible_models": list(eligible),
            "shadow": shadow,
            "feature_schema_version": self.feature_schema["feature_schema_version"],
        }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bundle(
    path: str | Path,
    *,
    trusted_public_keys: Iterable[str],
    karmi_version: str,
    known_actions: Iterable[str],
    expected_feature_schema_version: str,
) -> LoadedPolicy:
    root = Path(path)
    if (root / "checksums.json").is_symlink() or (root / "signature.sig").is_symlink():
        raise BundleRejected("symlink in bundle metadata")
    try:
        checksums_bytes = (root / "checksums.json").read_bytes()
        signature = _read_json(root / "signature.sig")
    except (OSError, ValueError) as exc:
        raise BundleRejected(f"unreadable bundle: {exc}") from exc
    if not isinstance(signature, dict):
        raise BundleRejected("malformed signature file")
    # 1. signature over checksums.json with a trusted key
    try:
        public_hex, signature_hex = str(signature["public_key"]), str(signature["signature"])
        public, sig = bytes.fromhex(public_hex), bytes.fromhex(signature_hex)
    except (KeyError, ValueError) as exc:
        raise BundleRejected("malformed signature file") from exc
    if signature.get("algorithm") != "ed25519" or public_hex not in set(trusted_public_keys):
        raise BundleRejected("untrusted or unsupported signing key")
    if not ed25519.verify(public, checksums_bytes, sig):
        raise BundleRejected("signature invalid")
    # 2. checksums of every file, and nothing extra
    try:
        checksums = json.loads(checksums_bytes)
    except ValueError as exc:
        raise BundleRejected("invalid checksums file") from exc
    if not isinstance(checksums, dict) or not isinstance(checksums.get("files"), dict):
        raise BundleRejected("invalid checksums file")
    listed: dict[str, Any] = checksums["files"]
    if any(not isinstance(digest, str) for digest in listed.values()):
        raise BundleRejected("invalid checksums file")
    entries = list(root.rglob("*"))
    if any(p.is_symlink() for p in entries):
        raise BundleRejected("symlink in bundle")
    present = {str(p.relative_to(root)) for p in entries if p.is_file()} - {
        "checksums.json",
        "signature.sig",
    }
    if present != set(listed):
        raise BundleRejected(f"file set mismatch: {sorted(present ^ set(listed))}")
    resolved_root = root.resolve()
    for name, digest in listed.items():
        if (
            not name
            or "\\" in name
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            or not (root / name).resolve().is_relative_to(resolved_root)
        ):
            raise BundleRejected(f"unsafe bundle path: {name}")
        try:
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
                raise BundleRejected(f"checksum mismatch: {name}")
        except OSError as exc:
            raise BundleRejected(f"unreadable bundle file: {name}") from exc
    missing = [name for name in REQUIRED_FILES if name not in listed]
    if missing:
        raise BundleRejected(f"missing files: {missing}")
    try:
        documents = {name: _read_json(root / name) for name in REQUIRED_FILES}
    except (OSError, ValueError) as exc:
        raise BundleRejected("unreadable bundle document") from exc
    if not all(isinstance(doc, dict) for doc in documents.values()):
        raise BundleRejected("bundle documents must be JSON objects")
    manifest = documents["manifest.json"]
    policy = documents["routing_policy.json"]
    features = documents["feature_schema.json"]
    # 3. artifact schema recognised
    if (
        manifest.get("schema") != "PolicyBundleV1"
        or str(manifest.get("schema_version", "")).split(".")[0] != SUPPORTED_ARTIFACT_MAJOR
    ):
        raise BundleRejected("unrecognised artifact schema")
    if (
        policy.get("policy_schema_version") not in SUPPORTED_POLICY_SCHEMAS
        or policy.get("algorithm") != "linucb"
    ):
        raise BundleRejected("unsupported policy schema")
    # 4. feature schema compatible
    if (
        features.get("feature_schema_version") != expected_feature_schema_version
        or manifest.get("feature_schema_id") != features.get("schema_id")
    ):
        raise BundleRejected("feature schema incompatible")
    if not isinstance(features.get("features"), list) or policy.get("feature_dimension") != len(
        features["features"]
    ):
        raise BundleRejected("policy dimension does not match feature schema")
    exploration = policy.get("exploration")
    epsilon = exploration.get("epsilon") if isinstance(exploration, dict) else None
    if (
        not isinstance(exploration, dict)
        or exploration.get("mode") not in ("none", "epsilon_greedy")
        or isinstance(epsilon, bool)
        or not isinstance(epsilon, int | float)
        or not math.isfinite(epsilon)
        or not 0.0 <= epsilon <= 1.0
    ):
        raise BundleRejected("invalid exploration probability")
    # 5. model ids exist in Karmi's registry
    actions = policy.get("actions")
    if not isinstance(actions, list) or not actions:
        raise BundleRejected("policy has no actions")
    unknown = set(actions) - set(known_actions)
    if unknown:
        raise BundleRejected(f"unknown models: {sorted(unknown)}")
    # 7. minimum Karmi version
    try:
        too_old = _version(karmi_version) < _version(str(manifest["minimum_karmi_version"]))
    except (KeyError, ValueError) as exc:
        raise BundleRejected("invalid minimum Karmi version") from exc
    if too_old:
        raise BundleRejected("Karmi too old for this bundle")
    # 8/9. self-test: every parameter finite and well-shaped, a decision can be produced
    d = policy["feature_dimension"]
    parameters = policy.get("parameters")
    if not isinstance(parameters, dict):
        raise BundleRejected("missing policy parameters")
    for action in actions:
        params = parameters.get(action)
        if (
            not isinstance(params, dict)
            or len(params.get("theta", [])) != d
            or len(params.get("a_inv", [])) != d
            or any(len(row) != d for row in params["a_inv"])
            or not all(math.isfinite(v) for v in params["theta"])
            or not all(math.isfinite(v) for row in params["a_inv"] for v in row)
        ):
            raise BundleRejected(f"malformed parameters for {action}")
    loaded = LoadedPolicy(
        manifest,
        policy,
        features,
        checksums_sha256=hashlib.sha256(checksums_bytes).hexdigest(),
        signer_public_key=public_hex,
    )
    probe: dict[str, Any] = {
        spec["source"]: None for spec in features["features"] if "source" in spec
    }
    probe.update(_PROBE_CONTEXT)
    try:
        distribution = loaded.probabilities(probe, actions, explore=True)
    except (ValueError, TypeError, KeyError) as exc:
        raise BundleRejected("self-test failed") from exc
    if not distribution or abs(sum(distribution.values()) - 1.0) > 1e-9:
        raise BundleRejected("self-test failed")
    return loaded
