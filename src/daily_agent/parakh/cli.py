"""``karmi-parakh``: operator CLI for the Parakh exchange (telemetry out, bundles in).

No command changes the executed route. ``shadow`` only makes a verified bundle record its
own choices next to the static live decision.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from daily_agent.config import get_settings
from daily_agent.db import SessionLocal, get_engine
from daily_agent.parakh import receiver
from daily_agent.parakh.bundle import BundleRejected
from daily_agent.parakh.telemetry import build_telemetry_batch

app = typer.Typer(no_args_is_help=True, add_completion=False)

Actor = Annotated[str, typer.Option("--actor", help="Operator performing the action")]
Reason = Annotated[str, typer.Option("--reason", help="Why; stored in the audit log")]


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise typer.BadParameter("timestamps need a timezone offset")
    return parsed.astimezone(UTC)


def _print(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, sort_keys=True))


@app.command("export-telemetry")
def export_telemetry(
    start: Annotated[str, typer.Option(help="Window start (ISO 8601 with offset), inclusive")],
    end: Annotated[str, typer.Option(help="Window end (ISO 8601 with offset), exclusive")],
    out: Annotated[Path, typer.Option(help="Output TelemetryBatchV1 JSON path")],
) -> None:
    """Write sanitized routing evidence for ``[start, end)`` as TelemetryBatchV1."""
    with SessionLocal(bind=get_engine()) as session:
        batch = build_telemetry_batch(session, start=_timestamp(start), end=_timestamp(end))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(batch, sort_keys=True) + "\n", encoding="utf-8")
    decisions = [d for run in batch["runs"] for d in run["decisions"]]
    _print({
        "path": str(out), "batch_id": batch["batch_id"], "runs": len(batch["runs"]),
        "shadow_decisions": sum(1 for d in decisions if d["shadow"]),
    })


def _change(version: str, to_state: str, actor: str, reason: str) -> None:
    settings = get_settings()
    with SessionLocal(bind=get_engine()) as session:
        try:
            record = receiver.transition(session, settings, version, to_state, actor=actor,
                                         reason=reason)
        except (BundleRejected, receiver.BundleStateError) as exc:
            session.rollback()
            typer.echo(f"refused: {exc}", err=True)
            raise typer.Exit(1) from exc
        session.commit()
        _print({"artifact_version": record.artifact_version, "state": record.state})


@app.command("receive-bundle")
def receive_bundle(
    path: Annotated[Path, typer.Argument(help="PolicyBundleV1 directory from Parakh")],
    actor: Actor,
    reason: Reason,
) -> None:
    """Verify a bundle against the trusted keys and store an immutable copy (RECEIVED)."""
    settings = get_settings()
    with SessionLocal(bind=get_engine()) as session:
        try:
            record = receiver.receive_bundle(session, settings, path, actor=actor, reason=reason)
        except (BundleRejected, receiver.BundleStateError) as exc:
            session.rollback()
            typer.echo(f"rejected: {exc}", err=True)
            raise typer.Exit(1) from exc
        session.commit()
        _print({"artifact_version": record.artifact_version, "state": record.state,
                "checksums_sha256": record.checksums_sha256})


@app.command()
def stage(version: str, actor: Actor, reason: Reason) -> None:
    """RECEIVED -> STAGED after re-verifying the stored copy."""
    _change(version, receiver.STAGED, actor, reason)


@app.command()
def shadow(version: str, actor: Actor, reason: Reason) -> None:
    """STAGED -> SHADOW: record the bundle's choices; live routing is unchanged."""
    _change(version, receiver.SHADOW, actor, reason)


@app.command()
def retire(version: str, actor: Actor, reason: Reason) -> None:
    """Stop using a bundle."""
    _change(version, receiver.RETIRED, actor, reason)


@app.command()
def bundles() -> None:
    """List received bundles, their states and audit events."""
    with SessionLocal(bind=get_engine()) as session:
        _print(receiver.list_bundles(session))


if __name__ == "__main__":
    app()
