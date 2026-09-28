#!/usr/bin/env python3
"""Inspect an Android debug APK and record manual phone-flow evidence; never claim UI success from adb."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "ai.karmi.app"
STEPS = (
    "launch", "initial_screen", "configuration", "backend_reachable", "authentication",
    "primary_user_flow", "api_request", "api_error", "logout_expiration", "app_restart",
    "backend_restart", "offline_handling", "network_recovery",
)


def command(*args: str, timeout: int = 20, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    try:
        # Fixed adb/git/flutter argv from this module; no shell and no user-controlled executable.
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd)  # noqa: S603
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 127, "", "")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def revision() -> str:
    result = command("git", "-C", str(ROOT), "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def manual_results(path: Path | None, candidate: str, apk_hash: str | None,
                   serial: str | None) -> tuple[str, list[dict[str, str]]]:
    defaults = [{"id": step, "status": "NOT_RUN", "observation": ""} for step in STEPS]
    if path is None:
        return "BLOCKED", defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "BLOCKED", defaults
    if not isinstance(data, dict) or data.get("karmi_sha") != candidate or not apk_hash or data.get("apk_sha256") != apk_hash or data.get("serial") != serial:
        return "BLOCKED", defaults
    if not isinstance(data.get("reviewer"), str) or not data["reviewer"].strip():
        return "BLOCKED", defaults
    given = data.get("steps")
    if not isinstance(given, list) or len(given) != len(STEPS):
        return "BLOCKED", defaults
    results: list[dict[str, str]] = []
    for expected, entry in zip(STEPS, given, strict=True):
        if not isinstance(entry, dict) or entry.get("id") != expected:
            return "BLOCKED", defaults
        status = entry.get("status")
        observation = entry.get("observation")
        timestamp = entry.get("observed_at")
        if status not in {"PASS", "FAIL", "BLOCKED", "NOT_RUN"} or not isinstance(observation, str) or not isinstance(timestamp, str) or not timestamp.strip():
            return "BLOCKED", defaults
        if status in {"PASS", "FAIL"} and not observation.strip():
            return "BLOCKED", defaults
        if re.search(r"(?i)(authorization\s*[:=]|bearer\s+\S+|(?:token|password|secret|api[_ -]?key|cookie)\s*[:=]|private.key)", observation):
            return "BLOCKED", defaults
        results.append({"id": expected, "status": status, "observation": observation[:500],
                        "observed_at": timestamp})
    state = "FAIL" if any(step["status"] == "FAIL" for step in results) else (
        "PASS" if all(step["status"] == "PASS" for step in results) else "BLOCKED")
    return state, results


def usb_serial() -> str | None:
    devices = command("adb", "devices", "-l")
    connected = [line for line in devices.stdout.splitlines()[1:] if line.strip()]
    authorized = [line.split()[0] for line in connected
                  if len(line.split()) >= 3 and line.split()[1] == "device" and "usb:" in line]
    return authorized[0] if devices.returncode == 0 and len(connected) == 1 and len(authorized) == 1 else None


def navigation(steps: Path | None) -> tuple[str, str]:
    """mobile-e2e tab tour recorded by the driver alongside the 13 steps."""
    try:
        tour = json.loads(steps.read_text(encoding="utf-8")).get("extended_navigation") if steps else None
    except (OSError, ValueError, AttributeError):
        tour = None
    if not isinstance(tour, dict) or not tour:
        return "BLOCKED", "no extended navigation observations"
    statuses = {name: entry.get("status") for name, entry in tour.items() if isinstance(entry, dict)}
    state = "FAIL" if "FAIL" in statuses.values() else (
        "PASS" if len(statuses) == len(tour) and set(statuses.values()) == {"PASS"} else "BLOCKED")
    return state, ", ".join(f"{name}: {status}" for name, status in statuses.items())

def build_and_install(serial: str, apk: Path) -> dict[str, str]:
    """Build the debug APK from the committed tree and install it, so the device runs this candidate."""
    tree = command("git", "-C", str(ROOT), "status", "--porcelain")
    if tree.returncode != 0 or tree.stdout.strip():
        return {"status": "BLOCKED", "detail": "uncommitted Karmi changes; a build would not match any commit"}
    if command("flutter", "--version", timeout=120).returncode != 0:
        return {"status": "BLOCKED", "detail": "flutter not available on PATH"}
    built = command("flutter", "build", "apk", "--debug", "--dart-define=API_BASE_URL=http://127.0.0.1:8000",
                    "--dart-define=KARMI_DEV_AUTH=true", cwd=ROOT / "mobile", timeout=1200)
    if built.returncode != 0 or not apk.is_file():
        return {"status": "FAIL", "detail": f"flutter build apk failed: {(built.stderr or built.stdout)[-300:]}"}
    installed = command("adb", "-s", serial, "install", "-r", "-t", str(apk), timeout=300)
    if installed.returncode != 0 or "Success" not in installed.stdout:
        return {"status": "BLOCKED", "detail": "adb install refused (on a signature mismatch uninstall the old "
                                               "app only with the device owner's approval)"}
    return {"status": "PASS", "detail": f"built from {revision()[:12]} and installed ({sha(apk)[:12]})"}


def probe(output: Path, apk: Path, steps: Path | None, *, extended: bool = False,
          blocked_reason: str | None = None,
          extra_checks: dict[str, dict[str, str]] | None = None) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    candidate = revision()
    checks: dict[str, dict[str, str]] = dict(extra_checks or {})
    def record(name: str, status: str, detail: str) -> None:
        checks[name] = {"status": status, "detail": detail}
    tree = command("git", "-C", str(ROOT), "status", "--porcelain")
    clean = tree.returncode == 0 and not tree.stdout.strip()
    record("source_provenance", "PASS" if clean and re.fullmatch(r"[0-9a-f]{40}", candidate) else "BLOCKED",
           "committed clean Karmi candidate" if clean else "uncommitted changes cannot be attributed to installed APK")

    serial = usb_serial()
    record("usb_device", "PASS" if serial else "BLOCKED", "single USB-authorized Android device" if serial else "exactly one USB-authorized device required")
    installed_hash: str | None = None
    apk_hash = sha(apk) if apk.is_file() else None
    record("local_apk", "PASS" if apk_hash else "BLOCKED", "local debug APK hashed" if apk_hash else "build current Flutter candidate APK first")
    if serial:
        mapping = command("adb", "-s", serial, "reverse", "tcp:8000", "tcp:8000")
        reverse = command("adb", "-s", serial, "reverse", "--list")
        found = mapping.returncode == 0 and "tcp:8000 tcp:8000" in reverse.stdout
        record("usb_reverse", "PASS" if found else "FAIL", "loopback reverse verified" if found else "adb reverse unavailable")
        package = command("adb", "-s", serial, "shell", "pm", "path", PACKAGE)
        remote = next((line.split("package:", 1)[1].strip() for line in package.stdout.splitlines()
                       if line.startswith("package:") and line.endswith("/base.apk")), None)
        if remote and apk_hash:
            with tempfile.TemporaryDirectory(prefix="readiness-apk-") as temp:
                pulled = Path(temp) / "installed.apk"
                result = command("adb", "-s", serial, "pull", remote, str(pulled), timeout=60)
                installed_hash = sha(pulled) if result.returncode == 0 and pulled.is_file() else None
            matched = installed_hash == apk_hash
            record("installed_candidate", "PASS" if matched else "BLOCKED",
                   "installed APK bytes match candidate build" if matched else "installed APK differs from candidate or cannot be read")
        else:
            record("installed_candidate", "BLOCKED", "package not installed or local candidate APK absent")
        if remote:
            launch = command("adb", "-s", serial, "shell", "am", "start", "-W", "-n", f"{PACKAGE}/.MainActivity")
            pid = command("adb", "-s", serial, "shell", "pidof", PACKAGE)
            running = launch.returncode == 0 and pid.returncode == 0 and pid.stdout.strip().isdigit()
            record("process_launch", "PASS" if running else "FAIL",
                   "Android process started" if running else "app launch/process failed")
    else:
        for name in ("usb_reverse", "installed_candidate", "process_launch"):
            record(name, "BLOCKED", "requires authorized device")
    try:
        tick = time.monotonic()
        with urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=3) as response:
            payload = json.loads(response.read(4096))
            ready = (response.status == 200 and payload.get("status") == "ready"
                     and payload.get("database") == "ok" and payload.get("live_models") is False
                     and payload.get("paid_checkout") is False and payload.get("whatsapp") == "policy_disabled")
        record("backend_ready", "PASS" if ready else "FAIL",
               f"local /ready {'returned ready' if ready else 'unexpected response'} in {round((time.monotonic() - tick) * 1000)} ms")
    except (urllib.error.URLError, TimeoutError, ValueError):
        record("backend_ready", "BLOCKED", "local backend unavailable or invalid /ready response")
    state, observed = manual_results(steps, candidate, apk_hash if installed_hash == apk_hash else None, serial)
    record("journeys", state, "13 candidate-matched observed steps" if state == "PASS" else
           blocked_reason or "13 candidate-matched observed steps required")
    if extended:
        record("extended_navigation", *navigation(steps))
    method = "none"
    with contextlib.suppress(OSError, ValueError, AttributeError):
        method = str(json.loads(steps.read_text(encoding="utf-8")).get("method", "manual")) if steps else "none"
    evidence: dict[str, object] = {
        "schema_version": 1, "mode": "synthetic-development", "captured_at": datetime.now(UTC).isoformat(),
        "karmi_sha": candidate, "apk_sha256": apk_hash, "installed_apk_sha256": installed_hash,
        "serial": serial, "checks": checks, "steps": observed, "observation_method": method,
        "warning": "step results are only as strong as their observation method; debug build, "
                   "development sign-in and a synthetic backend do not prove production identity"}
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apk", type=Path, default=ROOT / "mobile/build/app/outputs/flutter-apk/app-debug.apk")
    parser.add_argument("--steps", type=Path, help="13 observed steps with reviewer and matching commit/APK/serial")
    parser.add_argument("--drive", action="store_true",
                        help="build and install the candidate debug APK, run the automated 13-step journey "
                             "(device_driver.py) and validate its evidence")
    parser.add_argument("--no-build", action="store_true", help="with --drive: use the existing local APK")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--smoke", action="store_true")
    modes.add_argument("--extended", action="store_true")
    args = parser.parse_args()
    if args.drive and args.steps:
        parser.error("--drive produces its own steps; do not combine with --steps")
    result: dict[str, object] = {}
    serial = usb_serial() if args.drive else None
    if serial:
        import device_driver  # sibling module; imported lazily so manual validation needs no driver

        build = {"status": "NOT_RUN", "detail": "--no-build: existing local APK used"}
        if not args.no_build:
            build = build_and_install(serial, args.apk)
        extra = {"candidate_build_install": build}

        def validate(steps: Path) -> None:
            # Runs while the driver's backend is still serving so /ready is observed live.
            result.update(probe(args.output, args.apk, steps, extended=args.extended, extra_checks=extra))
        try:
            if build["status"] not in ("PASS", "NOT_RUN"):
                raise device_driver.Blocked(f"candidate build/install {build['status']}: {build['detail']}")
            device_driver.drive(ROOT, args.output / "driver", serial, sha(args.apk) if args.apk.is_file() else None,
                                revision(), args.extended, validate)
        except device_driver.Blocked as blocked:
            result = probe(args.output, args.apk, None, extended=args.extended, blocked_reason=str(blocked),
                           extra_checks=extra)
    else:
        reason = "automated journey needs exactly one USB-authorized device" if args.drive else None
        result = probe(args.output, args.apk, args.steps, extended=args.extended, blocked_reason=reason)
    checks = result["checks"]
    assert isinstance(checks, dict)
    statuses = [check["status"] for check in checks.values()]
    state = "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses else "PASS"
    print(f"Android evidence: {args.output / 'evidence.json'}; {state}")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[state]


if __name__ == "__main__":
    raise SystemExit(main())
