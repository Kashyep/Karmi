"""Drive the Karmi Android app over adb against the device-harness backend and keep evidence.

Every observation comes from the live device: the uiautomator hierarchy (to find nodes by
text / content-description), `adb exec-out screencap` screenshots and a JSON log. Nothing is
sent to a real model provider when the backend is started with ``dev_fake_provider.py
serve-backend`` and the fake provider is running; the prompts are keyword-driven.

Prerequisites (see docs/release1/DEVICE_TESTING.md):
  * fake provider:   python scripts/dev_fake_provider.py fake            (127.0.0.1:8900)
  * backend:         python scripts/dev_fake_provider.py serve-backend --port 8000
  * adb reverse tcp:8000 tcp:<backend port>
  * profile APK built with --dart-define=API_BASE_URL=http://127.0.0.1:8000 and installed

Usage:
  python scripts/device_smoke.py [--serial SERIAL] [--out-root docs/release1/device-runs]

Output: <out-root>/<UTC timestamp>/NN-<name>.png and log.json.
If the build offers no development sign-in, the run stops and reports that a manual sign-in is
needed; it never types credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "ai.karmi.app"
LAUNCHER = f"{PACKAGE}/.LauncherAnanta"
DEFAULT_SERIAL = "5B271XEBF3XDF0"


class StepFailed(Exception):
    pass


class Abort(Exception):
    """Stops the run: the app is on a screen this script must not drive."""


CLERK_MARKERS = ("Sign in securely", "Welcome back", "Create an account")
COMPOSER_HINT = "Message Karmi"


def guard_not_clerk(nodes: list[Node]) -> None:
    """Never type into Clerk's sign-in card: the device build must use development sign-in."""
    for node in nodes:
        if any(marker in node.label or marker in node.text for marker in CLERK_MARKERS):
            raise Abort(f"Clerk sign-in is showing ({node.label or node.text!r}); use the development sign-in build")

TESTAUTH_ENV = Path(os.environ.get("KARMI_TESTAUTH_ENV", ROOT / ".env.testauth"))

def read_tester_code() -> str:
    """KARMI_TEST_AUTH_CODE from the local env file. The value is read, typed, never printed/logged."""
    try:
        lines = TESTAUTH_ENV.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise StepFailed(f"cannot read the tester env file: {exc.strerror}") from exc
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() == "KARMI_TEST_AUTH_CODE" and value.strip().strip("'\""):
            return value.strip().strip("'\"")
    raise StepFailed("KARMI_TEST_AUTH_CODE is missing from the tester env file")

def clerk_showing(nodes: list[Node]) -> bool:
    return any(marker in f"{n.label} {n.text}" for n in nodes for marker in CLERK_MARKERS)


@dataclass
class Node:
    text: str
    desc: str
    kind: str
    bounds: tuple[int, int, int, int]
    selected: bool
    checked: bool

    @property
    def label(self) -> str:
        return self.desc or self.text

    @property
    def centre(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2


@dataclass
class Report:
    started: str
    serial: str
    steps: list[dict[str, object]] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    outcome: str = "running"

    def add(self, step: str, status: str, **details: object) -> None:
        self.steps.append({"step": step, "status": status, "at": datetime.now(UTC).isoformat(), **details})


class Device:
    def __init__(self, serial: str, shots: Path) -> None:
        self.serial = serial
        self.shots = shots
        self.count = 0
        self.guard_clerk = True
        self.width, self.height = self._screen_size()

    def adb(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # fixed argv, no shell
            ["adb", "-s", self.serial, *args], capture_output=True, text=True,
            errors="replace", timeout=timeout, check=False,
        )

    def _screen_size(self) -> tuple[int, int]:
        match = re.search(r"(\d+)x(\d+)", self.adb("shell", "wm", "size").stdout)
        if not match:
            raise StepFailed("could not read the screen size from `wm size`")
        return int(match.group(1)), int(match.group(2))

    def nodes(self) -> list[Node]:
        for _ in range(3):
            raw = self.adb("exec-out", "uiautomator", "dump", "/dev/tty").stdout
            start, end = raw.find("<?xml"), raw.rfind(">")
            if start >= 0 and end > start:
                break
            time.sleep(0.5)
        else:
            return []
        tree = ET.fromstring(raw[start:end + 1])  # uiautomator output from the attached device
        found: list[Node] = []
        for node in tree.iter("node"):
            numbers = [int(v) for v in re.findall(r"\d+", node.get("bounds", ""))]
            if len(numbers) != 4:
                continue
            found.append(Node(
                text=node.get("text") or "",
                desc=node.get("content-desc") or "",
                kind=(node.get("class") or "").rsplit(".", 1)[-1],
                bounds=(numbers[0], numbers[1], numbers[2], numbers[3]),
                selected=node.get("selected") == "true",
                checked=node.get("checked") == "true",
            ))
        if self.guard_clerk:
            guard_not_clerk(found)
        return found

    def find(self, pred: Callable[[Node], bool], timeout: float = 0) -> Node | None:
        deadline = time.monotonic() + timeout
        while True:
            for node in self.nodes():
                if pred(node):
                    return node
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.5)

    def wait(self, pred: Callable[[Node], bool], what: str, timeout: float) -> Node:
        node = self.find(pred, timeout)
        if node is None:
            raise StepFailed(f"timed out after {timeout:.0f}s waiting for {what}")
        return node

    def tap(self, node: Node) -> None:
        x, y = node.centre
        self.adb("shell", "input", "tap", str(x), str(y))

    def tap_desc(self, prefix: str, timeout: float = 15) -> None:
        self.tap(self.wait(lambda n: n.label.startswith(prefix), repr(prefix), timeout))

    def composer(self, timeout: float = 15) -> Node:
        """The chat composer: an EditText plus its Send/Stop action on the same screen."""
        deadline = time.monotonic() + timeout
        while True:
            nodes = self.nodes()
            action = any(n.label.startswith(("Send message", "Stop generating")) for n in nodes)
            fields = [n for n in nodes if n.kind == "EditText" and n.text in ("", COMPOSER_HINT)]
            if action and fields:
                return fields[0]
            if time.monotonic() >= deadline:
                raise StepFailed(f"chat composer '{COMPOSER_HINT}' not on screen after {timeout:.0f}s")
            time.sleep(0.5)

    def type_into(self, field_node: Node, text: str, allowed: str = r"[A-Za-z0-9 ]+") -> None:
        if not re.fullmatch(allowed, text):
            raise StepFailed("text has characters adb input cannot type reliably; nothing was typed")
        self.tap(field_node)
        time.sleep(0.6)
        if field_node.text and field_node.text != COMPOSER_HINT:
            self.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
            for _ in range(len(field_node.text)):
                self.adb("shell", "input", "keyevent", "KEYCODE_DEL")
        self.adb("shell", "input", "text", text.replace(" ", "%s"))
        time.sleep(0.4)
        if self.find(lambda n: n.kind == "EditText" and n.text == text, 5) is None:
            raise StepFailed("the field did not show the typed text; nothing was sent")
    def type_text(self, text: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9 ]+", text):
            raise ValueError("adb input text only carries plain ASCII words here")
        field_node = self.composer()
        self.tap(field_node)
        time.sleep(0.6)
        existing = "" if field_node.text in ("", COMPOSER_HINT) else field_node.text
        if existing:
            # Clear leftovers from an earlier step so the new text is the whole message.
            self.adb("shell", "input", "keyevent", "KEYCODE_MOVE_END")
            for _ in range(len(existing)):
                self.adb("shell", "input", "keyevent", "KEYCODE_DEL")
        self.adb("shell", "input", "text", text.replace(" ", "%s"))
        time.sleep(0.4)
        if self.find(lambda n: n.kind == "EditText" and n.text == text, 5) is None:
            raise StepFailed(f"composer did not show {text!r} after typing; nothing was sent")

    def swipe(self, dy: int, duration_ms: int = 350) -> None:
        """Positive dy drags the content up (reveals older messages when scrolled up)."""
        x = self.width // 2
        y_mid = self.height // 2
        self.adb("shell", "input", "swipe", str(x), str(y_mid + dy // 2), str(x), str(y_mid - dy // 2),
                 str(duration_ms))

    def back(self) -> None:
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")

    def screenshot(self, report: Report, name: str) -> str:
        self.count += 1
        target = self.shots / f"{self.count:02d}-{name}.png"
        with target.open("wb") as sink:
            subprocess.run(  # fixed argv
                ["adb", "-s", self.serial, "exec-out", "screencap", "-p"], stdout=sink,
                timeout=30, check=False,
            )
        report.screenshots.append(target.name)
        return target.name


def busy(node: Node) -> bool:
    return node.label.startswith("Stop generating")


def composer_idle(node: Node) -> bool:
    return node.label.startswith("Send message")


def wait_until_done(device: Device, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        nodes = device.nodes()
        if not any(busy(n) for n in nodes) and any(composer_idle(n) for n in nodes):
            return True
        time.sleep(1.0)
    return False


def send(device: Device, text: str) -> float:
    device.type_text(text)
    device.tap_desc("Send message", timeout=15)
    return time.monotonic()


def run(serial: str, out_root: Path) -> Report:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    shots = out_root / stamp
    shots.mkdir(parents=True, exist_ok=True)
    report = Report(started=stamp, serial=serial)
    device = Device(serial, shots)

    def step(name: str, fn: Callable[[], dict[str, object] | None]) -> bool:
        started = time.monotonic()
        try:
            details = fn() or {}
            report.add(name, "ok", seconds=round(time.monotonic() - started, 1), **details)
            return True
        except StepFailed as exc:
            report.add(name, "failed", seconds=round(time.monotonic() - started, 1), error=str(exc))
            return False

    def launch() -> dict[str, object]:
        device.adb("shell", "am", "force-stop", PACKAGE)
        result = device.adb("shell", "am", "start", "-W", "-n", LAUNCHER)
        if "Status: ok" not in result.stdout:
            raise StepFailed("activity manager did not report a launch")
        device.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        return {}

    def sign_in() -> dict[str, object]:
        """Sign in through Clerk's email card with the tester code (never printed)."""
        def ready(nodes: list[Node]) -> bool:
            return any(n.label.startswith(("Send message", "Stop generating")) for n in nodes)

        device.guard_clerk = False
        try:
            nodes = device.nodes()
            deadline = time.monotonic() + 25
            while not ready(nodes) and not clerk_showing(nodes) and time.monotonic() < deadline:
                time.sleep(1.0)
                nodes = device.nodes()
            if ready(nodes):
                return {"method": "already signed in"}
            if not clerk_showing(nodes):
                raise StepFailed("neither chat composer nor Clerk's sign-in card appeared")
            email = next((n for n in nodes if n.kind == "EditText"), None)
            if email is None:
                raise StepFailed("Clerk sign-in card has no email field")
            device.type_into(email, read_tester_code(), allowed=r"[A-Za-z0-9._@+-]+")
            device.tap(device.wait(lambda n: n.label == "Continue" or n.text == "Continue", "Clerk Continue button", 10))
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if ready(device.nodes()):
                    return {"method": "clerk sign-in with tester code"}
                time.sleep(1.0)
            raise StepFailed("Clerk did not reach the chat within 60s after Continue (verification step not handled)")
        finally:
            device.guard_clerk = True

    def new_chat() -> dict[str, object]:
        device.tap_desc("New chat", timeout=15)
        device.composer()
        time.sleep(1.0)
        return {"shot": device.screenshot(report, "empty-chat")}

    def render() -> dict[str, object]:
        send(device, "render test")
        done = wait_until_done(device, 60)
        time.sleep(1.0)
        return {"completed": done, "shot": device.screenshot(report, "render")}

    def long_scrolled() -> dict[str, object]:
        send(device, "long test")
        time.sleep(4.0)
        device.swipe(int(device.height * 0.45))
        time.sleep(0.5)
        device.swipe(int(device.height * 0.30))
        time.sleep(2.5)
        pill = device.find(lambda n: n.label.startswith("New messages") or n.label.startswith("Jump to latest"), 0)
        shot = device.screenshot(report, "long-midstream-scrolled")
        return {"pill_visible": pill is not None, "pill_label": pill.label if pill else None,
                "still_streaming": any(busy(n) for n in device.nodes()), "shot": shot}

    def long_done() -> dict[str, object]:
        done = wait_until_done(device, 150)
        time.sleep(1.0)
        pill = device.find(lambda n: n.label.startswith("New messages") or n.label.startswith("Jump to latest"), 0)
        return {"completed": done, "pill_label": pill.label if pill else None,
                "shot": device.screenshot(report, "long-done")}

    def slow() -> dict[str, object]:
        started = send(device, "slow test")
        remaining = 11.0 - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(remaining)
        status = [n.label for n in device.nodes() if busy(n) or "Status" in n.label][:3]
        shot = device.screenshot(report, "slow-11s")
        done = wait_until_done(device, 60)
        return {"at_seconds": round(time.monotonic() - started, 1), "status_labels": status,
                "completed": done, "shot": shot}

    def fail() -> dict[str, object]:
        send(device, "fail test")
        node = device.wait(lambda n: n.label in {"Retry", "Try again", "Regenerate"} or n.text in {"Retry", "Try again"}
                           or "went wrong" in n.label.lower() or "unavailable" in n.label.lower(),
                           "error card", 60)
        time.sleep(1.0)
        return {"retry_label": node.label or node.text, "shot": device.screenshot(report, "fail-error-retry")}

    def history() -> dict[str, object]:
        device.tap_desc("Conversation history", timeout=15)
        time.sleep(1.5)
        shot = device.screenshot(report, "history")
        device.back()
        time.sleep(1.0)
        return {"shot": shot}

    def dark_mode() -> dict[str, object]:
        if device.find(lambda n: n.label.startswith("Settings tab"), 0) is None:
            device.tap_desc("More options", timeout=10)
            device.tap_desc("Settings", timeout=10)
        else:
            device.tap_desc("Settings tab", timeout=10)
        device.wait(lambda n: n.text == "Dark", "dark theme control", 15)
        selected = [n.text for n in device.nodes() if n.text in {"System", "Light", "Dark"} and (n.selected or n.checked)]
        device.tap(device.wait(lambda n: n.text == "Dark", "Dark control", 5))
        time.sleep(1.5)
        shot = device.screenshot(report, "dark-mode")
        restore = selected[0] if selected else "System"
        device.tap(device.wait(lambda n: n.text == restore, f"{restore} control", 5))
        time.sleep(1.0)
        return {"previous_theme": selected, "shot": shot, "restored_to": restore}

    def launch_and_sign_in() -> None:
        if not step("launch", launch):
            raise StepFailed("launch failed")
        if not step("sign_in", sign_in):
            raise StepFailed("sign-in failed")

    try:
        launch_and_sign_in()
        for name, fn in [
            ("new_chat_empty", new_chat),
            ("render", render),
            ("long_scrolled_midstream", long_scrolled),
            ("long_done", long_done),
            ("slow_11s", slow),
            ("fail_error", fail),
            ("history", history),
            ("dark_mode", dark_mode),
        ]:
            step(name, fn)
    except Abort as exc:
        report.outcome = f"aborted: {exc}"
        return report
    except StepFailed as exc:
        report.outcome = f"stopped: {exc}"
        return report
    failed = [s["step"] for s in report.steps if s["status"] != "ok"]
    report.outcome = "all steps ok" if not failed else f"steps failed: {', '.join(map(str, failed))}"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serial", default=os.environ.get("ANDROID_SERIAL", DEFAULT_SERIAL))
    parser.add_argument("--out-root", type=Path, default=ROOT / "docs" / "release1" / "device-runs")
    args = parser.parse_args()
    report = run(args.serial, args.out_root)
    target = args.out_root / report.started / "log.json"
    target.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"outcome": report.outcome, "log": str(target), "screenshots": report.screenshots}, indent=2))
    return 0 if report.outcome == "all steps ok" else 1


if __name__ == "__main__":
    sys.exit(main())
