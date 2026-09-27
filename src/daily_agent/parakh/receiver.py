"""Karmi-owned PolicyBundleV1 lifecycle: RECEIVED -> STAGED -> SHADOW -> RETIRED.

Parakh has no path into Karmi. An operator hands Karmi a bundle directory through the
``karmi-parakh`` CLI; Karmi verifies it (trusted Ed25519 signature, checksums, schemas,
model registry, minimum version, self-test), copies it into an immutable store under
``data_dir/policy_bundles`` and re-verifies the copy before staging, shadowing or loading.

SHADOW only *records* the candidate's choice next to the static live decision. CANARY and
PRODUCTION would change live traffic; they are not implemented in this release and every
transition into them is refused.
"""

from __future__ import annotations

import random
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent import __version__
from daily_agent.config import Settings
from daily_agent.models import PolicyBundleEvent, PolicyBundleRecord
from daily_agent.parakh.bundle import BundleRejected, LoadedPolicy, load_bundle
from daily_agent.parakh.routing import FEATURE_SCHEMA_VERSION, KNOWN_ACTIONS

RECEIVED, STAGED, SHADOW, RETIRED = "received", "staged", "shadow", "retired"
TRANSITIONS: dict[str, frozenset[str]] = {
    RECEIVED: frozenset({STAGED, RETIRED}),
    STAGED: frozenset({SHADOW, RETIRED}),
    SHADOW: frozenset({RETIRED}),
    RETIRED: frozenset(),
}
LIVE_TRAFFIC_STATES = frozenset({"canary", "production"})
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")

# (bundle id, checksums digest, trusted keys) -> verified policy. Verification is pure-Python
# Ed25519, so a stored bundle is verified once per process and trust set, not on every request;
# removing a key from settings takes effect on the next request.
_loaded: dict[tuple[str, str, tuple[str, ...]], LoadedPolicy] = {}


def _cache_key(record: PolicyBundleRecord, settings: Settings) -> tuple[str, str, tuple[str, ...]]:
    return (record.id, record.checksums_sha256, tuple(sorted(settings.parakh_trusted_public_keys)))


class BundleStateError(Exception):
    """Unknown bundle or a transition Karmi does not allow."""


def bundle_store(settings: Settings) -> Path:
    return settings.data_dir / "policy_bundles"


def verify_bundle(path: Path, settings: Settings) -> LoadedPolicy:
    if not settings.parakh_trusted_public_keys:
        raise BundleRejected("no trusted Parakh signing keys configured")
    return load_bundle(
        path,
        trusted_public_keys=settings.parakh_trusted_public_keys,
        karmi_version=__version__,
        known_actions=KNOWN_ACTIONS,
        expected_feature_schema_version=FEATURE_SCHEMA_VERSION,
    )


def _event(
    session: Session, record: PolicyBundleRecord, from_state: str | None, to_state: str,
    *, actor: str, reason: str,
) -> None:
    session.add(
        PolicyBundleEvent(
            bundle_id=record.id, from_state=from_state, to_state=to_state, actor=actor,
            reason=reason,
        )
    )


def _require_operator(actor: str, reason: str) -> None:
    if not actor.strip() or not reason.strip():
        raise BundleStateError("an operator actor and reason are required")


def receive_bundle(
    session: Session, settings: Settings, source: Path, *, actor: str, reason: str
) -> PolicyBundleRecord:
    """Verify ``source`` and store an immutable verified copy. Idempotent per artifact version."""
    _require_operator(actor, reason)
    loaded = verify_bundle(source, settings)
    if not _VERSION_RE.match(loaded.version):
        raise BundleRejected(f"unsafe artifact version {loaded.version!r}")
    existing = session.scalar(
        select(PolicyBundleRecord).where(PolicyBundleRecord.artifact_version == loaded.version)
    )
    if existing is not None:
        if existing.checksums_sha256 != loaded.checksums_sha256:
            raise BundleRejected("artifact version already received with different contents")
        return existing
    store = bundle_store(settings)
    store.mkdir(parents=True, exist_ok=True)
    target = store / loaded.version
    if target.exists():
        # Left behind by an interrupted receive: keep it only if it is the same bundle.
        if verify_bundle(target, settings).checksums_sha256 != loaded.checksums_sha256:
            raise BundleRejected(f"stored copy for {loaded.version} differs; refusing overwrite")
    else:
        incoming = store / f".incoming-{uuid.uuid4().hex}"
        shutil.copytree(source, incoming)
        try:
            if verify_bundle(incoming, settings).checksums_sha256 != loaded.checksums_sha256:
                raise BundleRejected("bundle changed while being copied")
            for path in incoming.rglob("*"):
                if path.is_file():
                    path.chmod(0o444)
            incoming.rename(target)
        except BaseException:
            shutil.rmtree(incoming, ignore_errors=True)
            raise
    record = PolicyBundleRecord(
        artifact_version=loaded.version,
        checksums_sha256=loaded.checksums_sha256,
        signer_public_key=loaded.signer_public_key,
        storage_path=str(target),
        state=RECEIVED,
    )
    session.add(record)
    session.flush()
    _event(session, record, None, RECEIVED, actor=actor, reason=reason)
    session.flush()
    return record


def _load_stored(record: PolicyBundleRecord, settings: Settings) -> LoadedPolicy:
    key = _cache_key(record, settings)
    cached = _loaded.get(key)
    if cached is not None:
        return cached
    loaded = verify_bundle(Path(record.storage_path), settings)
    if (
        loaded.checksums_sha256 != record.checksums_sha256
        or loaded.version != record.artifact_version
    ):
        raise BundleRejected(f"stored copy of {record.artifact_version} no longer matches")
    _loaded[key] = loaded
    return loaded


def transition(
    session: Session, settings: Settings, artifact_version: str, to_state: str,
    *, actor: str, reason: str,
) -> PolicyBundleRecord:
    _require_operator(actor, reason)
    if to_state in LIVE_TRAFFIC_STATES:
        raise BundleStateError(
            f"{to_state} changes live traffic and is not implemented in this release; "
            "it requires a separately authorized rollout"
        )
    record = session.scalar(
        select(PolicyBundleRecord).where(PolicyBundleRecord.artifact_version == artifact_version)
    )
    if record is None:
        raise BundleStateError(f"unknown policy bundle {artifact_version}")
    if to_state not in TRANSITIONS.get(record.state, frozenset()):
        raise BundleStateError(f"cannot move {artifact_version} from {record.state} to {to_state}")
    if to_state in (STAGED, SHADOW):
        _loaded.pop(_cache_key(record, settings), None)
        _load_stored(record, settings)  # re-verify the stored copy under current trust/registry
    if to_state == SHADOW:
        for other in session.scalars(
            select(PolicyBundleRecord).where(
                PolicyBundleRecord.state == SHADOW, PolicyBundleRecord.id != record.id
            )
        ):
            _event(session, other, SHADOW, RETIRED, actor=actor,
                   reason=f"superseded in shadow by {artifact_version}")
            other.state = RETIRED
        # Retire first: the single-shadow unique index would reject both rows in one flush.
        session.flush()
    _event(session, record, record.state, to_state, actor=actor, reason=reason)
    record.state = to_state
    session.flush()
    return record


def shadow_select(
    session: Session,
    settings: Settings,
    context: dict[str, Any],
    eligible: list[str],
    *,
    seed: str,
) -> dict[str, Any] | None:
    """The SHADOW bundle's decision for this context, or ``None`` without one."""
    record = session.scalar(select(PolicyBundleRecord).where(PolicyBundleRecord.state == SHADOW))
    if record is None:
        return None
    loaded = _load_stored(record, settings)
    # Seeded by run id so a shadow decision is reproducible; not a security use.
    rng = random.Random(seed)  # noqa: S311
    return loaded.select(context, eligible, rng, shadow=True)


def list_bundles(session: Session) -> list[dict[str, Any]]:
    records = session.scalars(select(PolicyBundleRecord).order_by(PolicyBundleRecord.received_at))
    out = []
    for record in records:
        events = session.scalars(
            select(PolicyBundleEvent)
            .where(PolicyBundleEvent.bundle_id == record.id)
            .order_by(PolicyBundleEvent.created_at)
        )
        out.append({
            "artifact_version": record.artifact_version,
            "state": record.state,
            "checksums_sha256": record.checksums_sha256,
            "signer_public_key": record.signer_public_key,
            "received_at": record.received_at.isoformat(),
            "events": [
                {"from": e.from_state, "to": e.to_state, "actor": e.actor, "reason": e.reason,
                 "at": e.created_at.isoformat()}
                for e in events
            ],
        })
    return out
