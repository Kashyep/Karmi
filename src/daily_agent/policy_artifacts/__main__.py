"""CLI entrypoint for policy artifact management (python -m daily_agent.policy_artifacts)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from daily_agent import __version__
from daily_agent.config import get_settings
from daily_agent.policy_artifacts.store import PolicyStore, StoreCorrupt, utcnow
from daily_agent.policy_artifacts.verifier import BundleRejected, verify_bundle
from daily_agent.routing.registry import entitlement_map

app = typer.Typer(
    help="Daily Agent policy artifact management CLI (ADR-0003).",
    no_args_is_help=True,
    add_completion=False,
)


def _get_store() -> PolicyStore:
    settings = get_settings()
    return PolicyStore(
        root=settings.router_policy_dir,
        public_key_b64=settings.router_policy_public_key,
        known_models=entitlement_map(),
        karmi_version=__version__,
    )


@app.command("verify")
def verify_command(
    path: Annotated[Path, typer.Argument(help="Path to bundle directory", exists=True)],
) -> None:
    """Verify a policy bundle directory against cryptographic and schema contracts."""
    settings = get_settings()
    try:
        bundle = verify_bundle(
            path,
            public_key_b64=settings.router_policy_public_key,
            known_models=entitlement_map(),
            karmi_version=__version__,
            now=utcnow(),
        )
        typer.echo(
            f"Valid bundle: {bundle.manifest.artifact_version} "
            f"(content_sha256={bundle.content_sha256[:16]}...)",
        )
    except BundleRejected as e:
        typer.echo(f"Rejected: [{e.code}] {e.detail}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("install")
def install_command(
    path: Annotated[Path, typer.Argument(help="Path to bundle directory", exists=True)],
) -> None:
    """Verify and install a policy bundle into the policy store."""
    store = _get_store()
    try:
        bundle = store.install(path)
        typer.echo(f"Installed bundle: {bundle.manifest.artifact_version}")
    except BundleRejected as e:
        typer.echo(f"Rejected: [{e.code}] {e.detail}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("shadow")
def shadow_command(
    version: Annotated[str | None, typer.Argument(help="Version to shadow")] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Clear shadow policy")] = False,
) -> None:
    """Set or clear the shadow policy bundle."""
    store = _get_store()
    try:
        if clear:
            store.set_shadow(None)
            typer.echo("Shadow policy cleared")
        elif version is not None:
            store.set_shadow(version)
            typer.echo(f"Shadow policy set to: {version}")
        else:
            typer.echo("Error: specify VERSION to shadow or use --clear", err=True)
            raise typer.Exit(code=1)
    except BundleRejected as e:
        typer.echo(f"Rejected: [{e.code}] {e.detail}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("promote")
def promote_command(
    version: Annotated[str, typer.Argument(help="Installed version to promote to active")],
) -> None:
    """Promote an installed and regression-passed policy bundle to active."""
    store = _get_store()
    try:
        bundle = store.promote(version)
        typer.echo(f"Promoted {bundle.manifest.artifact_version} to active")
    except BundleRejected as e:
        typer.echo(f"Rejected: [{e.code}] {e.detail}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("mark-good")
def mark_good_command(
    version: Annotated[str, typer.Argument(help="Installed version to mark as last known good")],
) -> None:
    """Mark an installed and verified policy bundle as the last known good."""
    store = _get_store()
    try:
        store.mark_known_good(version)
        typer.echo(f"Marked {version} as last known good")
    except BundleRejected as e:
        typer.echo(f"Rejected: [{e.code}] {e.detail}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("rollback")
def rollback_command(
    reason: Annotated[str, typer.Option("--reason", "-r", help="Reason for rollback")],
) -> None:
    """Roll back and quarantine the active policy (to previous, last-known-good or static)."""
    store = _get_store()
    try:
        new_active = store.rollback(reason=reason)
        typer.echo(f"Rolled back. Active is now: {new_active}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("deactivate")
def deactivate_command(
    reason: Annotated[str, typer.Option("--reason", "-r", help="Reason for deactivation")],
) -> None:
    """Deactivate active learned policy back to None (static baseline)."""
    store = _get_store()
    try:
        store.deactivate(reason=reason)
        typer.echo("Active policy deactivated (static routing)")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@app.command("status")
def status_command() -> None:
    """Print the current policy store state."""
    store = _get_store()
    try:
        state = store.read_state()
        typer.echo(f"Revision: {state.revision}")
        typer.echo(f"Active: {state.active}")
        typer.echo(f"Previous: {state.previous}")
        typer.echo(f"Last known good: {state.last_known_good}")
        typer.echo(f"Shadow: {state.shadow}")
        installed_str = ", ".join(state.installed) if state.installed else "none"
        typer.echo(f"Installed: {installed_str}")
        quarantined_str = ", ".join(state.quarantined) if state.quarantined else "none"
        typer.echo(f"Quarantined: {quarantined_str}")
    except StoreCorrupt as e:
        typer.echo(f"Store corrupt: {e}", err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    app()
