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

    def type_text(self, text: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9 ]+", text):
            raise ValueError("adb input text only carries plain ASCII words here")
        field_node = self.wait(lambda n: n.kind == "EditText", "message field", 15)
        self.tap(field_node)
        time.sleep(0.6)
        self.adb("shell", "input", "text", text.replace(" ", "%s"))
        time.sleep(0.4)

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
        node = device.find(lambda n: n.label.startswith("Continue (development sign-in)"), 25)
        if node is not None:
            device.tap(node)
            device.wait(lambda n: n.kind == "EditText" or n.label.startswith("New chat"), "chat after sign-in", 40)
            return {"method": "development sign-in"}
        if device.find(lambda n: "sign-in" in n.label.lower() or "clerk" in n.label.lower(), 0) is not None:
            raise StepFailed("manual sign-in needed: this build shows only Clerk sign-in, no dev auth")
        device.wait(lambda n: n.kind == "EditText" or n.label.startswith("New chat"), "chat screen", 20)
        return {"method": "already signed in"}

    def new_chat() -> dict[str, object]:
        device.tap_desc("New chat", timeout=15)
        device.wait(lambda n: n.kind == "EditText", "composer after New chat", 15)
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
    except StepFailed as exc:
        report.outcome = f"stopped: {exc}"
        return report

    step("new_chat_empty", new_chat)
    step("render", render)
    step("long_scrolled_midstream", long_scrolled)
    step("long_done", long_done)
    step("slow_11s", slow)
    step("fail_error", fail)
    step("history", history)
    step("dark_mode", dark_mode)
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
