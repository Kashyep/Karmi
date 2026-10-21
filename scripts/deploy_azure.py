#!/usr/bin/env python3
"""Azure Container Apps deployment and management CLI for Karmi."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
RG = "rg-karmi-prod"
LOCATION = "eastasia"
CAE = "cae-karmi-prod"
APP = "karmi-beta"
IMAGE_REPO = "karmi-backend"
TARGET_PORT = 8000
ENV_AZURE = ROOT / ".env.azure"
PROD_ENV = ROOT / ".env.azure.prod"
PRODUCTION_BUDGET_MICRO = "1000000"
GLOBAL_BUDGET_MICRO = "1000000"
# Two gateway attempts must finish inside the mobile client's request timeout.
GATEWAY_TIMEOUT_SECONDS = "12"
REGISTRY_IN_IMAGE = (
    "/usr/local/lib/python3.12/site-packages/daily_agent/gateway/data/model_registry.json"
)


def az(*args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    """Run an Azure CLI command with captured output and timeout."""
    return subprocess.run(  # noqa: S603
        ["az", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def die(msg: str) -> int:
    """Print an error message to stderr and return 1."""
    print(msg, file=sys.stderr)
    return 1


def fail_step(step_name: str, code: int) -> int:
    """Print a step failure message to stderr and return the exit code."""
    print(f"step {step_name} failed with exit code {code}", file=sys.stderr)
    return code


def write_private(path: Path, mapping: dict[str, str]) -> None:
    """Write KEY=VALUE mapping to a file with mode 0600."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        for k, v in mapping.items():
            f.write(f"{k}={v}\n")


def read_private(path: Path) -> dict[str, str]:
    """Read a dotenv file without interpolation, returning empty dict if missing."""
    if not path.is_file():
        return {}
    raw = dotenv_values(path, interpolate=False)
    return {k: v for k, v in raw.items() if k is not None and v is not None}


def require_login() -> int:
    """Verify that Azure CLI is logged in."""
    proc = az("account", "show", "-o", "none")
    if proc.returncode != 0:
        return die("Run az login first")
    return 0


def ensure_state() -> dict[str, str]:
    """Ensure AUTH_SECRET and WEBHOOK_SECRET exist in private state and return state."""
    state = read_private(ENV_AZURE)
    dirty = False
    if not state.get("AUTH_SECRET"):
        state["AUTH_SECRET"] = secrets.token_hex(32)
        dirty = True
    if not state.get("WEBHOOK_SECRET"):
        state["WEBHOOK_SECRET"] = secrets.token_hex(32)
        dirty = True
    if dirty:
        write_private(ENV_AZURE, state)
    return state


def connect_read_only(url: str) -> psycopg.Connection:
    """Establish a read-only PostgreSQL connection with safe defaults."""
    return psycopg.connect(
        url,
        connect_timeout=15,
        sslmode="verify-full",
        autocommit=True,
        options="-c default_transaction_read_only=on -c statement_timeout=10000",
    )


def migrate() -> int:
    """Validate Neon schema state and upgrade to Alembic head."""
    try:
        neon_path = ROOT / ".env.neon"
        if not neon_path.is_file():
            return die("Missing .env.neon file")
        values = dotenv_values(neon_path, interpolate=False)
        db_url = values.get("DAILY_AGENT_DATABASE_URL")
        mig_url = values.get("DAILY_AGENT_MIGRATION_DATABASE_URL")
        if not db_url or not mig_url:
            return die(
                "Missing DAILY_AGENT_DATABASE_URL or DAILY_AGENT_MIGRATION_DATABASE_URL in .env.neon"
            )

        runtime = make_url(db_url)
        direct = make_url(mig_url)
        if (
            runtime.database != "neondb"
            or direct.database != "neondb"
            or not runtime.host
            or not runtime.host.endswith(".neon.tech")
            or "-pooler." not in runtime.host
            or not direct.host
            or not direct.host.endswith(".neon.tech")
            or "-pooler." in direct.host
            or direct.host != runtime.host.replace("-pooler.", ".", 1)
        ):
            print(
                "Refusing migration: expected matching Neon pooled/direct URLs for neondb.",
                file=sys.stderr,
            )
            return 1

        if str(ROOT / "src") not in sys.path:
            sys.path.insert(0, str(ROOT / "src"))
        from daily_agent.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                _env_file=None,
                database_url=db_url,
                migration_database_url=mig_url,
            )
        direct_driver_url = (
            make_url(settings.migration_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )

        with connect_read_only(direct_driver_url) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_schema()")
            db, schema = cursor.fetchone()
            if db != "neondb" or schema != "public":
                print(
                    "Refusing migration: database or schema does not match neondb/public.",
                    file=sys.stderr,
                )
                return 1

            cursor.execute(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
            tables = {row[0] for row in cursor.fetchall()}

            revisions: list[str] = []
            if "alembic_version" in tables:
                cursor.execute(
                    "SELECT version_num FROM public.alembic_version ORDER BY version_num"
                )
                revisions = [row[0] for row in cursor.fetchall()]

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        sd = ScriptDirectory.from_config(cfg)
        heads = sorted(sd.get_heads())
        if len(heads) != 1:
            print(
                f"Refusing migration: expected exactly one Alembic head, got {heads}",
                file=sys.stderr,
            )
            return 1
        known = {s.revision for s in sd.walk_revisions()}

        has_alembic = "alembic_version" in tables
        if not tables and not has_alembic:
            pass  # (a) fresh
        elif has_alembic and all(r in known for r in revisions):
            pass  # (b) alembic_version exists and every revision is known
        else:
            print(
                "Refusing migration: schema is neither empty nor at a recognized Alembic revision.",
                file=sys.stderr,
            )
            return 1

        revs_before_str = ", ".join(revisions) if revisions else "(none)"
        print(f"revisions before: {revs_before_str}")

        child_env = {k: v for k, v in os.environ.items() if not k.startswith("DAILY_AGENT_")}
        child_env["DAILY_AGENT_DATABASE_URL"] = db_url
        child_env["DAILY_AGENT_MIGRATION_DATABASE_URL"] = mig_url

        res = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        if res.returncode != 0:
            print(
                f"alembic upgrade failed with exit code {res.returncode}; diagnostic output suppressed."
            )
            return res.returncode

        with connect_read_only(direct_driver_url) as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT version_num FROM public.alembic_version ORDER BY version_num"
            )
            revisions_after = [row[0] for row in cursor.fetchall()]

        revs_after_str = ", ".join(revisions_after) if revisions_after else "(none)"
        print(f"revisions after: {revs_after_str}")

        if revisions_after != heads:
            print(
                f"Migration verification failed: expected {heads}, got {revisions_after}",
                file=sys.stderr,
            )
            return 1

        print(f"MIGRATED: head {heads[0]}")
        return 0
    except Exception as exc:
        print(type(exc).__name__, file=sys.stderr)
        return 1


def build() -> int:
    """Ensure ACR exists, tag the current commit, and run ACR build."""
    if rc := require_login():
        return rc

    state = ensure_state()
    acr_name = state.get("ACR_NAME")
    if not acr_name:
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        for _ in range(5):
            candidate = f"karmiprod{''.join(secrets.choice(alphabet) for _ in range(6))}"
            check_res = az(
                "acr",
                "check-name",
                "-n",
                candidate,
                "--query",
                "nameAvailable",
                "-o",
                "tsv",
            )
            if check_res.returncode == 0 and check_res.stdout.strip().lower() == "true":
                acr_name = candidate
                state["ACR_NAME"] = acr_name
                write_private(ENV_AZURE, state)
                break
        if not acr_name:
            return die("Failed to generate an available ACR name after 5 attempts")

    show_res = az("acr", "show", "-g", RG, "-n", acr_name, "-o", "none")
    if show_res.returncode != 0:
        create_res = az(
            "acr",
            "create",
            "-g",
            RG,
            "-n",
            acr_name,
            "-l",
            LOCATION,
            "--sku",
            "Basic",
            "--admin-enabled",
            "true",
            "-o",
            "none",
        )
        if create_res.returncode != 0:
            return die(f"step acr create failed with exit code {create_res.returncode}")
    else:
        update_res = az(
            "acr", "update", "-n", acr_name, "--admin-enabled", "true", "-o", "none"
        )
        if update_res.returncode != 0:
            return die(f"step acr update failed with exit code {update_res.returncode}")

    sha_proc = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if sha_proc.returncode != 0 or not sha_proc.stdout.strip():
        return die("git rev-parse failed")
    sha = sha_proc.stdout.strip()

    status_proc = subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = bool(status_proc.stdout.strip())
    if dirty:
        print("warning: git working tree is dirty; tag will include -dirty")
        tag = f"{sha}-dirty"
    else:
        tag = sha

    state["IMAGE_TAG"] = tag
    write_private(ENV_AZURE, state)

    # ACR Tasks is not permitted on this subscription: build locally with podman, push to ACR.
    image_ref = f"{acr_name}.azurecr.io/{IMAGE_REPO}:{tag}"
    build_res = subprocess.run(  # noqa: S603
        ["podman", "build", "--platform", "linux/amd64", "-f", "Dockerfile", "-t", image_ref, "."],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if build_res.returncode != 0:
        # Podman output is not printed: it can echo build args or registry details.
        return fail_step("podman build", build_res.returncode)

    pw_proc = az("acr", "credential", "show", "-n", acr_name, "--query", "passwords[0].value", "-o", "tsv")
    if pw_proc.returncode != 0 or not pw_proc.stdout.strip():
        return fail_step("acr credential show", pw_proc.returncode)
    login_res = subprocess.run(  # noqa: S603
        ["podman", "login", f"{acr_name}.azurecr.io", "--username", acr_name, "--password-stdin"],  # noqa: S607
        input=pw_proc.stdout.strip(),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if login_res.returncode != 0:
        return fail_step("podman login", login_res.returncode)
    push_res = subprocess.run(  # noqa: S603
        ["podman", "push", image_ref],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    subprocess.run(  # noqa: S603
        ["podman", "logout", f"{acr_name}.azurecr.io"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    if push_res.returncode != 0:
        return fail_step("podman push", push_res.returncode)

    verify_res = az(
        "acr",
        "repository",
        "show-tags",
        "-n",
        acr_name,
        "--repository",
        IMAGE_REPO,
        "--query",
        f"contains(@, '{tag}')",
        "-o",
        "tsv",
    )
    if verify_res.returncode != 0 or verify_res.stdout.strip().lower() != "true":
        return die(f"step verify tag {tag} failed")

    login_proc = az(
        "acr", "show", "-n", acr_name, "-g", RG, "--query", "loginServer", "-o", "tsv"
    )
    if login_proc.returncode != 0 or not login_proc.stdout.strip():
        return die(f"step acr show loginServer failed with exit code {login_proc.returncode}")
    login_server = login_proc.stdout.strip()
    print(f"IMAGE: {login_server}/{IMAGE_REPO}:{tag}")
    return 0


def deploy() -> int:
    """Deploy the backend container to Azure Container Apps and emit .env.azure.prod."""
    if rc := require_login():
        return rc

    state = ensure_state()
    acr_name = state.get("ACR_NAME")
    image_tag = state.get("IMAGE_TAG")
    if not acr_name or not image_tag:
        return die("run build first")

    auth_secret = state.get("AUTH_SECRET")
    webhook_secret = state.get("WEBHOOK_SECRET")
    if not auth_secret or not webhook_secret:
        return die("missing AUTH_SECRET or WEBHOOK_SECRET in state")

    neon = dotenv_values(ROOT / ".env.neon", interpolate=False)
    db_url = neon.get("DAILY_AGENT_DATABASE_URL")
    if not db_url:
        return die("Missing DAILY_AGENT_DATABASE_URL in .env.neon")
    try:
        parsed_db = make_url(db_url)
    except Exception:
        return die("Invalid DAILY_AGENT_DATABASE_URL in .env.neon")
    if (
        not parsed_db.host
        or not parsed_db.host.endswith(".neon.tech")
        or "-pooler." not in parsed_db.host
        or not parsed_db.drivername.startswith("postgresql+psycopg")
    ):
        return die("Invalid pooled Neon database URL in .env.neon")

    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from daily_agent.config import clerk_verification_config_valid

    clerk = dotenv_values(ROOT / ".env.clerk", interpolate=False)
    clerk_issuer = clerk.get("DAILY_AGENT_CLERK_ISSUER")
    clerk_jwt_key = clerk.get("DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64")
    if not clerk_issuer or not clerk_jwt_key:
        return die(
            "Missing DAILY_AGENT_CLERK_ISSUER or DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64 in .env.clerk"
        )
    if not clerk_verification_config_valid(clerk_issuer, clerk_jwt_key):
        return die("Invalid Clerk verification configuration in .env.clerk")

    openrouter = dotenv_values(ROOT / ".env.openrouter", interpolate=False)
    openrouter_api_key = openrouter.get("OPEN_ROUTER_KEY") or openrouter.get(
        "OPENROUTER_API_KEY"
    )
    if not openrouter_api_key:
        return die("Missing OPEN_ROUTER_KEY or OPENROUTER_API_KEY in .env.openrouter")

    login_proc = az(
        "acr", "show", "-n", acr_name, "-g", RG, "--query", "loginServer", "-o", "tsv"
    )
    if login_proc.returncode != 0 or not login_proc.stdout.strip():
        return fail_step("acr show loginServer", login_proc.returncode)
    login_server = login_proc.stdout.strip()

    update_proc = az(
        "acr", "update", "-n", acr_name, "--admin-enabled", "true", "-o", "none"
    )
    if update_proc.returncode != 0:
        return fail_step("acr update admin-enabled", update_proc.returncode)

    cred_proc = az(
        "acr",
        "credential",
        "show",
        "-n",
        acr_name,
        "--query",
        "passwords[0].value",
        "-o",
        "tsv",
    )
    if cred_proc.returncode != 0 or not cred_proc.stdout.strip():
        return fail_step("acr credential show", cred_proc.returncode)
    registry_password = cred_proc.stdout.strip()

    secrets_map = {
        "database-url": db_url,
        "auth-secret": auth_secret,
        "webhook-secret": webhook_secret,
        "openrouter-api-key": openrouter_api_key,
        "clerk-jwt-public-key": clerk_jwt_key,
    }
    secrets_args = [f"{k}={v}" for k, v in secrets_map.items()]

    plain_env_vars = [
        "DAILY_AGENT_ENVIRONMENT=production",
        "DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH=false",
        "DAILY_AGENT_OPENROUTER_ENABLED=true",
        "DAILY_AGENT_GATEWAY_KILL_SWITCH=false",
        f"DAILY_AGENT_GATEWAY_TIMEOUT_SECONDS={GATEWAY_TIMEOUT_SECONDS}",
        "DAILY_AGENT_PAID_CHECKOUT_ENABLED=false",
        "DAILY_AGENT_WHATSAPP_ENABLED=false",
        f"DAILY_AGENT_CLERK_ISSUER={clerk_issuer}",
        f"DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO={PRODUCTION_BUDGET_MICRO}",
        f"DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO={GLOBAL_BUDGET_MICRO}",
        f"DAILY_AGENT_MODEL_REGISTRY_PATH={REGISTRY_IN_IMAGE}",
    ]
    secret_env_vars = [
        "DAILY_AGENT_DATABASE_URL=secretref:database-url",
        "DAILY_AGENT_AUTH_SECRET=secretref:auth-secret",
        "DAILY_AGENT_WEBHOOK_SECRET=secretref:webhook-secret",
        "DAILY_AGENT_OPENROUTER_API_KEY=secretref:openrouter-api-key",
        "DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64=secretref:clerk-jwt-public-key",
    ]
    all_env_vars = plain_env_vars + secret_env_vars
    image = f"{login_server}/{IMAGE_REPO}:{image_tag}"

    app_exists_proc = az("containerapp", "show", "-g", RG, "-n", APP, "-o", "none")
    exists = app_exists_proc.returncode == 0

    if not exists:
        create_res = az(
            "containerapp",
            "create",
            "-g",
            RG,
            "-n",
            APP,
            "--environment",
            CAE,
            "--image",
            image,
            "--ingress",
            "external",
            "--target-port",
            str(TARGET_PORT),
            "--min-replicas",
            "1",
            "--max-replicas",
            "1",
            "--registry-server",
            login_server,
            "--registry-username",
            acr_name,
            "--registry-password",
            registry_password,
            "--secrets",
            *secrets_args,
            "--env-vars",
            *all_env_vars,
            "-o",
            "none",
        )
        if create_res.returncode != 0:
            return fail_step("containerapp create", create_res.returncode)
    else:
        sec_res = az(
            "containerapp",
            "secret",
            "set",
            "-g",
            RG,
            "-n",
            APP,
            "--secrets",
            *secrets_args,
            "-o",
            "none",
        )
        if sec_res.returncode != 0:
            return fail_step("containerapp secret set", sec_res.returncode)

        reg_res = az(
            "containerapp",
            "registry",
            "set",
            "-g",
            RG,
            "-n",
            APP,
            "--server",
            login_server,
            "--username",
            acr_name,
            "--password",
            registry_password,
            "-o",
            "none",
        )
        if reg_res.returncode != 0:
            return fail_step("containerapp registry set", reg_res.returncode)

        ing_res = az(
            "containerapp",
            "ingress",
            "enable",
            "-g",
            RG,
            "-n",
            APP,
            "--type",
            "external",
            "--target-port",
            str(TARGET_PORT),
            "-o",
            "none",
        )
        if ing_res.returncode != 0:
            return fail_step("containerapp ingress enable", ing_res.returncode)

        upd_res = az(
            "containerapp",
            "update",
            "-g",
            RG,
            "-n",
            APP,
            "--image",
            image,
            "--min-replicas",
            "1",
            "--max-replicas",
            "1",
            "--replace-env-vars",
            *all_env_vars,
            "-o",
            "none",
        )
        if upd_res.returncode != 0:
            return fail_step("containerapp update", upd_res.returncode)

    # latestReadyRevisionName stays empty for single-revision apps on this platform, so check the
    # revision running the image we just deployed: Healthy + Running.
    ready = False
    latest_ready_rev = ""
    for _ in range(40):
        time.sleep(15)
        rev_proc = az(
            "containerapp",
            "revision",
            "list",
            "-g",
            RG,
            "-n",
            APP,
            "--query",
            "[].{name:name,image:properties.template.containers[0].image,"
            "health:properties.healthState,run:properties.runningState}",
            "-o",
            "json",
        )
        if rev_proc.returncode != 0:
            continue
        try:
            revisions = json.loads(rev_proc.stdout or "[]")
        except json.JSONDecodeError:
            continue
        for rev in revisions if isinstance(revisions, list) else []:
            if (
                rev.get("image") == image
                and rev.get("health") == "Healthy"
                and rev.get("run") == "Running"
            ):
                ready = True
                latest_ready_rev = str(rev.get("name"))
                break
        if ready:
            break

    if not ready:
        return die("Container app failed to become ready within timeout")

    fqdn_proc = az(
        "containerapp",
        "show",
        "-g",
        RG,
        "-n",
        APP,
        "--query",
        "properties.configuration.ingress.fqdn",
        "-o",
        "tsv",
    )
    if fqdn_proc.returncode != 0 or not fqdn_proc.stdout.strip():
        return die("Failed to retrieve container app FQDN")
    fqdn = fqdn_proc.stdout.strip()

    prod_mapping = {
        "DAILY_AGENT_ENVIRONMENT": "production",
        "DAILY_AGENT_DATABASE_URL": db_url,
        "DAILY_AGENT_AUTH_SECRET": auth_secret,
        "DAILY_AGENT_WEBHOOK_SECRET": webhook_secret,
        "DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH": "false",
        "DAILY_AGENT_CLERK_ISSUER": clerk_issuer,
        "DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64": clerk_jwt_key,
        "DAILY_AGENT_OPENROUTER_ENABLED": "true",
        "DAILY_AGENT_OPENROUTER_API_KEY": openrouter_api_key,
        "DAILY_AGENT_GATEWAY_KILL_SWITCH": "false",
        "DAILY_AGENT_GATEWAY_TIMEOUT_SECONDS": GATEWAY_TIMEOUT_SECONDS,
        "DAILY_AGENT_PAID_CHECKOUT_ENABLED": "false",
        "DAILY_AGENT_WHATSAPP_ENABLED": "false",
        "DAILY_AGENT_LIVE_MODELS_ENABLED": "false",
        "DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO": PRODUCTION_BUDGET_MICRO,
        "DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO": GLOBAL_BUDGET_MICRO,
        "DAILY_AGENT_MODEL_REGISTRY_PATH": str(
            ROOT / "src/daily_agent/gateway/data/model_registry.json"
        ),
        "DAILY_AGENT_PUBLIC_BASE_URL": f"https://{fqdn}",
    }
    write_private(PROD_ENV, prod_mapping)

    print(f"DEPLOYED: https://{fqdn}")
    print(f"revision: {latest_ready_rev}")
    print("prod env written: .env.azure.prod (mode 600)")
    return 0


def status() -> int:
    """Show the current deployment state and replica count for the Container App."""
    if rc := require_login():
        return rc

    query = (
        "{provisioningState:properties.provisioningState,"
        "runningStatus:properties.runningStatus,"
        "fqdn:properties.configuration.ingress.fqdn,"
        "latestRevision:properties.latestRevisionName,"
        "latestReady:properties.latestReadyRevisionName,"
        "minReplicas:properties.template.scale.minReplicas,"
        "maxReplicas:properties.template.scale.maxReplicas,"
        "image:properties.template.containers[0].image}"
    )
    res = az("containerapp", "show", "-g", RG, "-n", APP, "--query", query, "-o", "json")
    if res.returncode != 0 or not res.stdout.strip():
        print("not deployed")
        return 1

    try:
        data = json.loads(res.stdout)
    except Exception:
        print("not deployed")
        return 1

    if not isinstance(data, dict):
        print("not deployed")
        return 1

    latest_rev = data.get("latestRevision")
    replicas_count = 0
    if latest_rev:
        rep_res = az(
            "containerapp",
            "replica",
            "list",
            "-g",
            RG,
            "-n",
            APP,
            "--revision",
            str(latest_rev),
            "--query",
            "[].name",
            "-o",
            "json",
        )
        if rep_res.returncode == 0 and rep_res.stdout.strip():
            try:
                rep_list = json.loads(rep_res.stdout)
            except (json.JSONDecodeError, TypeError):
                rep_list = None
            if isinstance(rep_list, list):
                replicas_count = len(rep_list)

    data["replicas"] = replicas_count
    print(json.dumps(data, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for deployment subcommands."""
    parser = argparse.ArgumentParser(
        description="Azure Container Apps deployment and management CLI for Karmi."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    subparsers.add_parser("migrate", help="Run database migrations against Neon head")
    subparsers.add_parser(
        "build", help="Build and push container image to Azure Container Registry"
    )
    subparsers.add_parser("deploy", help="Deploy container app to Azure Container Apps")
    subparsers.add_parser(
        "status", help="Show current deployment status and replica count"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point dispatching to subcommands."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "migrate": migrate,
        "build": build,
        "deploy": deploy,
        "status": status,
    }
    handler = handlers.get(args.subcommand)
    if handler:
        return handler()
    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
