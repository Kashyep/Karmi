"""PolicyStore and state machine for PolicyBundleV1 artifacts (ADR-0003, ART-001).

Manages the filesystem layout:
  root/bundles/<artifact_version>/
  root/state.json

Guarantees atomic state transitions, idempotent installs, rollback semantics,
and metric emissions. Assumes a single-writer process (CLI) while guarding
in-process concurrent calls with a threading lock.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from daily_agent.observability import METRICS, Metrics
from daily_agent.policy_artifacts.schema import LoadedBundle
from daily_agent.policy_artifacts.verifier import BundleRejected, verify_bundle


def utcnow() -> datetime:
    """Return the current time with UTC timezone."""
    return datetime.now(UTC)


class StoreCorrupt(Exception):
    """Raised when root/state.json is malformed or cannot be validated."""


class StateEvent(BaseModel):
    """An event recording an administrative lifecycle action on the policy store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    version: str | None = None
    at: datetime
    reason: str | None = None


class PolicyState(BaseModel):
    """The persistent state of installed, active, previous, and shadow policy bundles."""

    model_config = ConfigDict(extra="forbid")

    active: str | None = None
    previous: str | None = None
    last_known_good: str | None = None
    shadow: str | None = None
    installed: list[str] = Field(default_factory=list)
    # Versions demoted by rollback or a guardrail. Every process serves static routing for
    # them until an operator explicitly promotes the version again.
    quarantined: list[str] = Field(default_factory=list)
    history: list[StateEvent] = Field(default_factory=list)
    revision: int = 0


def _atomic_dir_replace(src: Path, dst: Path) -> None:
    """Safely replace or move a directory to `dst`, handling Windows os.replace directory semantics."""
    try:
        os.replace(src, dst)
    except (FileExistsError, PermissionError, OSError):
        if dst.exists():
            trash = dst.with_name(f".trash_{dst.name}_{uuid.uuid4().hex}")
            os.replace(dst, trash)
            try:
                os.replace(src, dst)
            except Exception:
                if trash.exists() and not dst.exists():
                    os.replace(trash, dst)
                raise
            shutil.rmtree(trash, ignore_errors=True)
        else:
            raise


class PolicyStore:
    """Stateful storage and lifecycle manager for verified PolicyBundleV1 packages."""

    def __init__(
        self,
        root: Path,
        *,
        public_key_b64: str | None,
        known_models: Mapping[str, frozenset[str]],
        karmi_version: str,
        clock: Callable[[], datetime] = utcnow,
        metrics: Metrics = METRICS,
    ) -> None:
        self.root = Path(root)
        self.bundles_dir = self.root / "bundles"
        self.state_file = self.root / "state.json"
        self._public_key_b64 = public_key_b64
        self._known_models = known_models
        self._karmi_version = karmi_version
        self._clock = clock
        self.metrics = metrics
        self._lock = threading.Lock()

        self.root.mkdir(parents=True, exist_ok=True)
        self.bundles_dir.mkdir(parents=True, exist_ok=True)

    def _verify(self, path: Path) -> LoadedBundle:
        try:
            return verify_bundle(
                path,
                public_key_b64=self._public_key_b64,
                known_models=self._known_models,
                karmi_version=self._karmi_version,
                now=self._clock(),
            )
        except BundleRejected as e:
            self.metrics.inc("policy_verification_failures_total", {"code": e.code})
            raise

    def _record_activation_metrics(self, state: PolicyState) -> None:
        active_version = state.active or "none"
        shadow_version = state.shadow or "none"
        self.metrics.set_gauge("policy_active", 1.0 if state.active else 0.0, {"version": active_version})
        self.metrics.set_gauge("policy_shadow", 1.0 if state.shadow else 0.0, {"version": shadow_version})

    def _write_state(self, state: PolicyState) -> None:
        """Atomically persist state.json using a tempfile and os.replace."""
        state.revision += 1
        payload = state.model_dump_json(indent=2).encode("utf-8")
        temp_file = self.root / f".state.tmp.{uuid.uuid4().hex}"
        try:
            with open(temp_file, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.state_file)
        finally:
            if temp_file.exists():
                with contextlib.suppress(OSError):
                    temp_file.unlink()
        self._record_activation_metrics(state)

    def read_state(self) -> PolicyState:
        """Read and validate the current state.json. Missing file returns empty state."""
        if not self.state_file.exists():
            return PolicyState()
        try:
            raw = self.state_file.read_bytes()
            return PolicyState.model_validate_json(raw)
        except Exception as e:
            raise StoreCorrupt(f"Corrupt policy store state at {self.state_file}: {e}") from e

    def install(self, source: Path) -> LoadedBundle:
        """Verify, stage, and install a bundle into bundles/<version>.

        Re-installing the identical bundle is an idempotent no-op.
        Re-installing a conflicting bundle with the same version raises BundleRejected('version_conflict').
        """
        source_bundle = self._verify(source)
        version = source_bundle.manifest.artifact_version

        with self._lock:
            state = self.read_state()
            target_dir = self.bundles_dir / version

            if target_dir.exists():
                existing = self._verify(target_dir)
                if existing.content_sha256 == source_bundle.content_sha256:
                    if version not in state.installed:
                        state.installed.append(version)
                        event = StateEvent(
                            action="install",
                            version=version,
                            at=self._clock(),
                            reason="idempotent",
                        )
                        state.history = (state.history + [event])[-200:]
                        self._write_state(state)
                    return existing

                raise BundleRejected(
                    "version_conflict",
                    f"Version '{version}' is already installed with different content "
                    f"({existing.content_sha256} != {source_bundle.content_sha256})",
                )

            temp_dir = self.bundles_dir / f".tmp_{version}_{uuid.uuid4().hex}"
            try:
                shutil.copytree(source, temp_dir)
                copied_bundle = self._verify(temp_dir)
                _atomic_dir_replace(temp_dir, target_dir)
            finally:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)

            if version not in state.installed:
                state.installed.append(version)
            event = StateEvent(action="install", version=version, at=self._clock(), reason=None)
            state.history = (state.history + [event])[-200:]
            self._write_state(state)
            return copied_bundle

    def load(self, version: str) -> LoadedBundle:
        """Re-verify and load an installed bundle directly from disk every time.

        The signed manifest must name the directory it was loaded from, so a validly
        signed bundle copied over another version's directory is rejected.
        """
        target_dir = self.bundles_dir / version
        if not target_dir.exists() or not target_dir.is_dir():
            raise BundleRejected("not_a_directory", f"Bundle version '{version}' does not exist on disk")
        bundle = self._verify(target_dir)
        if bundle.manifest.artifact_version != version:
            self.metrics.inc("policy_verification_failures_total", {"code": "version_conflict"})
            raise BundleRejected(
                "version_conflict",
                f"Bundle at '{version}' is signed as '{bundle.manifest.artifact_version}'",
            )
        return bundle

    def set_shadow(self, version: str | None) -> None:
        """Set or clear the active shadow bundle."""
        with self._lock:
            state = self.read_state()
            if version is not None:
                if version not in state.installed:
                    raise BundleRejected("not_promotable", f"Version '{version}' is not installed")
                self.load(version)

            state.shadow = version
            action = "shadow" if version is not None else "unshadow"
            event = StateEvent(action=action, version=version, at=self._clock(), reason=None)
            state.history = (state.history + [event])[-200:]
            self._write_state(state)

    def promote(self, version: str) -> LoadedBundle:
        """Promote an installed and verified bundle to active.

        Requires evaluation.passed_regression to be True. Sets previous = active,
        active = version. Re-promoting the active version is a no-op so a retried
        command cannot make the active version its own rollback target. An explicit
        promotion is the operator decision that lifts a quarantine on that version.
        """
        with self._lock:
            state = self.read_state()
            if version not in state.installed:
                raise BundleRejected("not_promotable", f"Version '{version}' is not installed")

            bundle = self.load(version)
            if not bundle.evaluation.passed_regression:
                raise BundleRejected(
                    "not_promotable",
                    f"Version '{version}' failed regression evaluation (passed_regression=False)",
                )
            if state.active == version and version not in state.quarantined:
                return bundle

            if state.active != version:
                state.previous = state.active
            state.active = version
            reason = "lift_quarantine" if version in state.quarantined else None
            state.quarantined = [item for item in state.quarantined if item != version]
            event = StateEvent(action="promote", version=version, at=self._clock(), reason=reason)
            state.history = (state.history + [event])[-200:]
            self._write_state(state)
            return bundle

    def mark_known_good(self, version: str) -> None:
        """Mark an installed and verified version as the last known good bundle."""
        with self._lock:
            state = self.read_state()
            if version not in state.installed:
                raise BundleRejected("not_promotable", f"Version '{version}' is not installed")
            self.load(version)
            state.last_known_good = version
            event = StateEvent(action="mark_known_good", version=version, at=self._clock(), reason=None)
            state.history = (state.history + [event])[-200:]
            self._write_state(state)

    def rollback(self, reason: str, *, expected_active: str | None = None) -> str | None:
        """Roll back and quarantine the active policy.

        New active is previous if it verifies, else last_known_good if it verifies, else
        None (static). Neither the failing active nor any quarantined version is a
        candidate. With no active policy the store stays static. ``expected_active``
        makes the call a no-op when another actor already changed the active version.
        Executes in one call with one atomic state write.
        """
        with self._lock:
            state = self.read_state()
            failing_active = state.active
            if expected_active is not None and failing_active != expected_active:
                return failing_active
            new_active: str | None = None
            if failing_active is not None:
                blocked = {failing_active, *state.quarantined}
                for candidate in (state.previous, state.last_known_good):
                    if candidate is None or candidate in blocked:
                        continue
                    try:
                        self.load(candidate)
                    except BundleRejected:
                        continue
                    new_active = candidate
                    break
                if failing_active not in state.quarantined:
                    state.quarantined.append(failing_active)
                if state.shadow == failing_active:
                    state.shadow = None

            state.active = new_active
            state.previous = None
            event = StateEvent(action="rollback", version=new_active, at=self._clock(), reason=reason)
            state.history = (state.history + [event])[-200:]
            self._write_state(state)
            self.metrics.inc("policy_rollbacks_total")
            return new_active

    def deactivate(self, reason: str) -> None:
        """Deactivate the active policy (static routing); a later rollback stays static."""
        with self._lock:
            state = self.read_state()
            deactivated = state.active
            state.previous = None
            state.active = None
            event = StateEvent(
                action="deactivate", version=deactivated, at=self._clock(), reason=reason
            )
            state.history = (state.history + [event])[-200:]
            self._write_state(state)
