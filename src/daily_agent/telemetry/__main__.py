"""Command-line interface for telemetry operations (ADR-0003).

Provides subcommands to finalize pending runs, export batch artifacts to disk,
purge expired telemetry data according to retention policy, and check operational status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from daily_agent.config import get_settings
from daily_agent.db import get_engine
from daily_agent.models import TelemetryRun, TelemetryRunOutcome, utcnow
from daily_agent.telemetry import exporter, finalizer, retention

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("finalize")
def finalize() -> None:
    """Finalize runs whose outcome attribution window has elapsed."""
    settings = get_settings()
    engine = get_engine()
    with Session(engine) as session:
        count = finalizer.finalize_due(
            session,
            now=utcnow(),
            window_seconds=settings.telemetry_attribution_window_seconds,
        )
        session.commit()
    typer.echo(f"Finalized {count} runs.")


@app.command("export")
def export(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Output directory for telemetry batches"),
    ] = None,
) -> None:
    """Export finalized telemetry runs into a checksummed TelemetryBatchV1 artifact."""
    settings = get_settings()
    engine = get_engine()
    out_dir = out or settings.telemetry_export_dir
    with Session(engine) as session:
        res = exporter.export_batch(
            session,
            out_dir=out_dir,
            producer_version="0.1.0",
            now=utcnow(),
        )
        session.commit()
    if res is None:
        typer.echo("Nothing to export.")
    else:
        typer.echo(
            f"Exported batch {res.batch_id} to {res.path} "
            f"({res.run_count} runs, {res.signal_count} signals, {res.feedback_count} feedback)."
        )


@app.command("purge")
def purge() -> None:
    """Purge expired telemetry rows that have already been exported."""
    settings = get_settings()
    engine = get_engine()
    with Session(engine) as session:
        counts = retention.purge_expired(
            session,
            now=utcnow(),
            retention_days=settings.telemetry_retention_days,
        )
        session.commit()
    typer.echo(
        f"Purge complete: {counts['runs']} runs, {counts['signals']} signals, "
        f"{counts['feedback']} feedback, {counts['orphans']} orphan rows deleted. "
        f"{counts['unexported_kept']} unexported runs and "
        f"{counts['pending_children_kept']} runs with unexported signals/feedback preserved."
    )


@app.command("status")
def status() -> None:
    """Display current telemetry counts and backlog status."""
    engine = get_engine()
    now = utcnow()
    with Session(engine) as session:
        unfinalized = (
            session.scalar(
                select(func.count(TelemetryRunOutcome.run_id)).where(
                    TelemetryRunOutcome.finalized_at.is_(None)
                )
            )
            or 0
        )
        unexported = (
            session.scalar(
                select(func.count(TelemetryRun.run_id))
                .join(TelemetryRunOutcome, TelemetryRun.run_id == TelemetryRunOutcome.run_id)
                .where(
                    TelemetryRunOutcome.finalized_at.is_not(None),
                    TelemetryRun.export_batch_id.is_(None),
                )
            )
            or 0
        )
        oldest_unexp = session.scalar(
            select(TelemetryRun.completed_at)
            .join(TelemetryRunOutcome, TelemetryRun.run_id == TelemetryRunOutcome.run_id)
            .where(
                TelemetryRunOutcome.finalized_at.is_not(None),
                TelemetryRun.export_batch_id.is_(None),
            )
            .order_by(TelemetryRun.completed_at.asc())
            .limit(1)
        )
        oldest_age_s = (
            max(0.0, (now - oldest_unexp).total_seconds()) if oldest_unexp is not None else 0.0
        )

    typer.echo(f"Unfinalized runs: {unfinalized}")
    typer.echo(f"Unexported runs: {unexported}")
    typer.echo(f"Oldest unexported age: {oldest_age_s:.1f}s")


if __name__ == "__main__":
    app()
