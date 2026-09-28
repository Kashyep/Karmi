"""Drive the 13-step phone smoke journey on one USB-connected Android device.

Every observation comes from the live device: the uiautomator accessibility hierarchy,
screenshots, scoped logcat and the access log of a disposable backend owned by this driver.
Synthetic development only: temporary SQLite, development sign-in, no live models, payments
or WhatsApp. The backend listens on 127.0.0.1:8000 and reaches the phone only through
`adb reverse` over USB; nothing is exposed on the LAN.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "ai.karmi.app"
LAUNCHER = f"{PACKAGE}/.LauncherAnanta"
PORT = 8000
BASE = f"http://127.0.0.1:{PORT}"
STEPS = (
    "launch", "initial_screen", "configuration", "backend_reachable", "authentication",
    "primary_user_flow", "api_request", "api_error", "logout_expiration", "app_restart",
    "backend_restart", "offline_handling", "network_recovery",
)
REVIEWER = "automated: Karmi mobile/tool/device_driver.py (uiautomator hierarchy, screenshots, backend access log)"
# Internal details that must never reach the screen when the API fails.
LEAK = re.compile(r"(?i)traceback|exception|sqlalchemy|daily_agent|stack ?trace|\{\s*\"(code|detail)\"")
ACCESS = re.compile(r'"(?P<method>[A-Z]+) (?P<path>/[^ ?"]*)[^"]* HTTP/[0-9.]+" (?P<status>\d{3})')


class StepFailed(Exception):
    """A step's observable expectation did not hold."""


class Blocked(Exception):
    """The environment cannot host the run; the evidence stays BLOCKED."""


@dataclass(frozen=True)
class Node:
    label: str
    kind: str
    bounds: tuple[int, int, int, int]

    @property
    def centre(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2


def utc() -> str:
    return datetime.now(UTC).isoformat()


class Device:
    def __init__(self, serial: str, shots: Path) -> None:
        self.serial = serial
        self.shots = shots
        self.shot_count = 0
        self.pids: set[str] = set()  # every app process seen, for pid-scoped logcat

    def adb(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        # Fixed adb argv built in this module; no shell on the host side.
        return subprocess.run(["adb", "-s", self.serial, *args], capture_output=True,  # noqa: S603, S607
                              text=True, errors="replace", timeout=timeout, check=False)

    def nodes(self) -> list[Node]:
        raw = self.adb("exec-out", "uiautomator", "dump", "/dev/tty").stdout
        start, end = raw.find("<?xml"), raw.rfind(">")
        if start < 0 or end < start:
            return []
        try:
            # uiautomator XML from the attached test device; no external entities are resolved.
            tree = ET.fromstring(raw[start:end + 1])  # noqa: S314
        except ET.ParseError:
            return []
        found: list[Node] = []
        for node in tree.iter("node"):
            label = node.get("content-desc") or node.get("text") or ""
            numbers = [int(value) for value in re.findall(r"\d+", node.get("bounds", ""))]
            if len(numbers) == 4:
                found.append(Node(label, (node.get("class") or "").rsplit(".", 1)[-1],
                                  (numbers[0], numbers[1], numbers[2], numbers[3])))
        return found

    def wait(self, predicate: Callable[[list[Node]], bool], what: str, timeout: float = 25) -> list[Node]:
        deadline = time.monotonic() + timeout
        while True:
            current = self.nodes()
            if predicate(current):
                return current
            if time.monotonic() > deadline:
                raise StepFailed(f"timed out after {timeout:.0f}s waiting for {what}")
            time.sleep(0.4)

    def wait_label(self, prefix: str, timeout: float = 25) -> Node:
        found = self.wait(lambda nodes: any(n.label.startswith(prefix) for n in nodes), repr(prefix), timeout)
        return next(n for n in found if n.label.startswith(prefix))

    def tap(self, node: Node) -> None:
        x, y = node.centre
        self.adb("shell", "input", "tap", str(x), str(y))

    def tap_label(self, prefix: str, timeout: float = 25) -> None:
        self.tap(self.wait_label(prefix, timeout))

    def send_message(self, text: str) -> None:
        assert re.fullmatch(r"[A-Za-z ]+", text), "adb input text only carries plain words here"
        field = self.wait(lambda nodes: any(n.kind == "EditText" for n in nodes), "message field")
        self.tap(next(n for n in field if n.kind == "EditText"))
        time.sleep(0.6)
        self.adb("shell", "input", "text", text.replace(" ", "%s"))
        time.sleep(0.4)
        self.tap_label("Send message")
        time.sleep(0.5)
        # BACK only while the keyboard is up; otherwise it would leave the app.
        if "mInputShown=true" in self.adb("shell", "dumpsys", "input_method").stdout:
            self.adb("shell", "input", "keyevent", "KEYCODE_BACK")

    def screenshot(self, name: str) -> str:
        self.shot_count += 1
        target = self.shots / f"{self.shot_count:02d}-{name}.png"
        with target.open("wb") as sink:
            subprocess.run(["adb", "-s", self.serial, "exec-out", "screencap", "-p"],  # noqa: S603, S607
                           stdout=sink, timeout=30, check=False)
        return target.name

    def pid(self, timeout: float = 8) -> str | None:
        """Newest app pid; polls briefly because the process can lag the activity report."""
        deadline = time.monotonic() + timeout
        while True:
            values = self.adb("shell", "pidof", PACKAGE).stdout.split()
            if values and all(value.isdigit() for value in values):
                self.pids.update(values)
                return max(values, key=int)
            if time.monotonic() > deadline:
                return None
            time.sleep(0.3)

    def launch(self) -> int:
        result = self.adb("shell", "am", "start", "-W", "-n", LAUNCHER)
        match = re.search(r"TotalTime: (\d+)", result.stdout)
        if result.returncode != 0 or "Status: ok" not in result.stdout or not match:
            raise StepFailed("activity manager did not report a completed launch")
        return int(match.group(1))

    def reverse(self, enabled: bool) -> None:
        if enabled:
            self.adb("reverse", f"tcp:{PORT}", f"tcp:{PORT}")
        else:
            self.adb("reverse", "--remove", f"tcp:{PORT}")
        listed = f"tcp:{PORT} tcp:{PORT}" in self.adb("reverse", "--list").stdout
        if listed != enabled:
            raise StepFailed(f"adb reverse state did not change to {'present' if enabled else 'absent'}")


class Backend:
    """Disposable Karmi API; the auth secret lives only in this process and the child's env."""

    def __init__(self, karmi: Path, workdir: Path, log: Path) -> None:
        self.karmi = karmi
        self.database = workdir / "device.db"
        self.log = log
        self.process: subprocess.Popen[bytes] | None = None
        self.secret = secrets.token_hex(32)

    def start(self, *, rotate_secret: bool = False) -> None:
        if rotate_secret:
            self.secret = secrets.token_hex(32)
        env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TMPDIR") if key in os.environ}
        env.update(PYTHONPATH=str(self.karmi / "src"), DAILY_AGENT_ENVIRONMENT="test",
                   DAILY_AGENT_DATABASE_URL=f"sqlite+pysqlite:///{self.database}",
                   DAILY_AGENT_AUTH_SECRET=self.secret, DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH="true",
                   DAILY_AGENT_LIVE_MODELS_ENABLED="false", DAILY_AGENT_PAID_CHECKOUT_ENABLED="false",
                   DAILY_AGENT_WHATSAPP_ENABLED="false")
        with self.log.open("ab") as sink:
            self.process = subprocess.Popen(  # noqa: S603
                [str(self.karmi / ".venv/bin/python"), "-m", "uvicorn", "daily_agent.api:app",
                 "--host", "127.0.0.1", "--port", str(PORT)],
                cwd=self.karmi, env=env, stdout=sink, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and self.process.poll() is None:
            if request("GET", "/ready")[0] == 200:
                return
            time.sleep(0.1)
        raise StepFailed("disposable backend did not become ready")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None

    def mark(self) -> int:
        return len(self.log.read_text(errors="replace").splitlines()) if self.log.exists() else 0

    def requests_since(self, mark: int, method: str, path: str) -> list[int]:
        lines = self.log.read_text(errors="replace").splitlines()[mark:]
        return [int(m["status"]) for line in lines if (m := ACCESS.search(line))
                and m["method"] == method and m["path"] == path]

    def wait_request(self, mark: int, method: str, path: str, timeout: float = 20) -> list[int]:
        deadline = time.monotonic() + timeout
        while not (seen := self.requests_since(mark, method, path)) and time.monotonic() < deadline:
            time.sleep(0.2)
        return seen


def request(method: str, path: str, *, token: str | None = None,
            body: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        # Fixed loopback URL of the disposable backend.
        with urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=headers,  # noqa: S310
                                                           method=method), timeout=10) as response:
            payload = json.loads(response.read() or b"{}")
            return response.status, payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as error:
        error.close()
        return error.code, {}
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return 0, {}


class Journey:
    def __init__(self) -> None:
        self.steps: dict[str, dict[str, str]] = {
            step: {"id": step, "status": "NOT_RUN", "observation": "", "observed_at": utc()} for step in STEPS}

    def record(self, step: str, status: str, observation: str) -> None:
        self.steps[step] = {"id": step, "status": status, "observation": observation[:480], "observed_at": utc()}

    def passed(self, *steps: str) -> bool:
        return all(self.steps[step]["status"] == "PASS" for step in steps)

    def attempt(self, name: str, requires: tuple[str, ...], action: Callable[[list[str]], None]) -> None:
        """Unmet prerequisites make a step BLOCKED without touching the device; never PASS."""
        missing = [step for step in requires if self.steps[step]["status"] != "PASS"]
        if missing:
            self.record(name, "BLOCKED", f"prerequisite not passed: {', '.join(missing)}")
            return
        notes: list[str] = []
        try:
            action(notes)
        except (StepFailed, subprocess.TimeoutExpired) as failure:
            self.record(name, "FAIL", "; ".join([*notes, str(failure)]))
        else:
            self.record(name, "PASS", "; ".join(notes))


def run(journey: Journey, device: Device, backend: Backend, extended: bool) -> dict[str, object]:
    extras: dict[str, object] = {}

    def body(name: str, *requires: str) -> Callable[[Callable[[list[str]], None]], None]:
        def decorate(action: Callable[[list[str]], None]) -> None:
            journey.attempt(name, requires, action)
        return decorate

    @body("launch")
    def launch(notes: list[str]) -> None:
        # Clean app data: the journey always starts signed out with synthetic state only.
        device.adb("shell", "am", "force-stop", PACKAGE)
        if device.adb("shell", "pm", "clear", PACKAGE).stdout.strip() != "Success":
            raise StepFailed("could not reset app data")
        total = device.launch()
        if not device.pid():
            raise StepFailed("no app process after launch")
        notes.append(f"launcher alias started, activity drawn in {total} ms, process running")

    @body("initial_screen", "launch")
    def initial(notes: list[str]) -> None:
        device.wait_label("One assistant for your drafts, tasks and notes.")
        device.wait_label("Karmi")
        notes.append(f"welcome screen rendered; screenshot {device.screenshot('welcome')}")

    mark = backend.mark()

    @body("backend_reachable", "initial_screen")
    def reachable(notes: list[str]) -> None:
        device.tap_label("Continue (development sign-in)")
        statuses = backend.wait_request(mark, "POST", "/dev/token")
        if statuses != [200]:
            raise StepFailed(f"backend saw development sign-in statuses {statuses or 'none'}")
        notes.append("phone request reached the disposable backend over adb reverse: POST /dev/token 200")

    @body("configuration", "initial_screen")
    def configuration(notes: list[str]) -> None:
        if not backend.requests_since(mark, "POST", "/dev/token"):
            raise StepFailed("no request from the app reached 127.0.0.1:8000; API_BASE_URL is not the local backend")
        notes.append("build configuration loaded: development sign-in enabled (KARMI_DEV_AUTH) and "
                     "API_BASE_URL resolved to the device loopback forwarded to the laptop backend")

    @body("authentication", "backend_reachable")
    def authentication(notes: list[str]) -> None:
        device.wait(lambda nodes: {"Chat tab", "Send message"} <= {n.label for n in nodes}, "signed-in chat screen")
        notes.append(f"development session established; chat screen shown; screenshot {device.screenshot('signed-in')}")

    send_mark = backend.mark()

    @body("primary_user_flow", "authentication")
    def primary(notes: list[str]) -> None:
        device.send_message("Draft a short status note")
        reply = device.wait_label("Karmi replied")
        if "Draft a short status note" not in reply.label or "Completed" not in reply.label:
            raise StepFailed("reply bubble did not show a completed draft")
        notes.append(f"sent a draft request, completed reply rendered; screenshot {device.screenshot('reply')}")

    @body("api_request", "primary_user_flow")
    def api(notes: list[str]) -> None:
        statuses = backend.requests_since(send_mark, "POST", "/v1/messages")
        if statuses != [200]:
            raise StepFailed(f"expected one POST /v1/messages 200, saw {statuses}")
        notes.append("backend access log: POST /v1/messages 200 for the phone request")

    @body("app_restart", "authentication")
    def restart(notes: list[str]) -> None:
        before = device.pid()
        device.adb("shell", "am", "force-stop", PACKAGE)
        total = device.launch()
        device.wait(lambda nodes: "Chat tab" in {n.label for n in nodes}, "chat screen after restart")
        if device.pid() in (None, before):
            raise StepFailed("process was not replaced by the restart")
        notes.append(f"force-stopped and relaunched in {total} ms; stored session reopened the chat screen "
                     "without signing in (conversation transcript is not persisted locally)")

    @body("offline_handling", "authentication")
    def offline(notes: list[str]) -> None:
        device.reverse(False)
        before = backend.mark()
        device.send_message("Offline probe")
        device.wait_label("You're offline")
        device.wait_label("Status: Not sent: offline")
        if backend.requests_since(before, "POST", "/v1/messages"):
            raise StepFailed("backend received the request while the transport was removed")
        notes.append("USB transport to the backend removed; app kept the message and showed "
                     f"\"You're offline\" with Retry; screenshot {device.screenshot('offline')}")

    @body("network_recovery", "offline_handling")
    def recovery(notes: list[str]) -> None:
        device.reverse(True)
        before = backend.mark()
        device.tap_label("Retry")
        device.wait(lambda nodes: any(n.label.startswith("Karmi replied") and "Offline probe" in n.label
                                      for n in nodes), "reply to the retried message")
        if backend.requests_since(before, "POST", "/v1/messages") != [200]:
            raise StepFailed("retry did not produce exactly one accepted request")
        notes.append(f"transport restored; Retry delivered the kept message (POST /v1/messages 200); "
                     f"screenshot {device.screenshot('recovered')}")

    @body("backend_restart", "authentication")
    def backend_restart(notes: list[str]) -> None:
        backend.stop()
        if request("GET", "/ready")[0] != 0:
            raise StepFailed("backend still answering after stop")
        backend.start()
        before = backend.mark()
        device.send_message("Restart probe")
        device.wait(lambda nodes: any(n.label.startswith("Karmi replied") and "Restart probe" in n.label
                                      for n in nodes), "reply after backend restart")
        if backend.requests_since(before, "POST", "/v1/messages") != [200]:
            raise StepFailed("request after restart was not accepted")
        notes.append("backend process stopped and restarted on the same database; the existing phone session "
                     "sent a message and received a completed reply")

    @body("api_error", "authentication")
    def api_error(notes: list[str]) -> None:
        # Use up the synthetic account's everyday allowance from the laptop, then observe the phone.
        status, payload = request("POST", "/dev/token?role=customer")
        token = payload.get("token")
        if status != 200 or not isinstance(token, str):
            raise StepFailed("could not obtain a laptop-side development session")
        for index in range(60):
            code, _ = request("POST", "/v1/messages", token=token,
                              body={"text": "Allowance filler", "idempotency_key": f"device-fill-{index:04d}"})
            if code == 429:
                break
            if code != 200:
                raise StepFailed(f"unexpected status {code} while using up the allowance")
        else:
            raise StepFailed("allowance was not exhausted after 60 requests")
        before = backend.mark()
        device.send_message("Allowance probe")
        device.wait_label("Allowance reached")
        screen = " ".join(n.label for n in device.nodes())
        if LEAK.search(screen):
            raise StepFailed("error screen exposes internal details")
        if backend.requests_since(before, "POST", "/v1/messages") != [429]:
            raise StepFailed("phone request was not the backend's 429 allowance response")
        notes.append("backend answered 429 ALLOWANCE_EXHAUSTED; app showed \"Allowance reached\" guidance without "
                     f"internal details; screenshot {device.screenshot('api-error')}")

    @body("logout_expiration", "authentication")
    def logout(notes: list[str]) -> None:
        # Server-side invalidation: restarting with a rotated signing key voids every issued session.
        backend.stop()
        backend.start(rotate_secret=True)
        before = backend.mark()
        # Tabs are built once at sign-in, so the next authenticated call is a chat send.
        device.tap_label("Chat tab")
        device.send_message("Expiry probe")
        device.wait_label("Session ended")
        if 401 not in backend.wait_request(before, "POST", "/v1/messages"):
            raise StepFailed("invalidated session was not rejected with 401")
        notes.append(f"invalidated session got 401 and the app returned to sign-in with \"Session ended\"; "
                     f"screenshot {device.screenshot('session-ended')}")
        device.tap_label("Continue (development sign-in)")
        device.tap_label("Settings tab")
        device.tap_label("Sign out")
        device.wait_label("Continue (development sign-in)")
        device.adb("shell", "am", "force-stop", PACKAGE)
        device.launch()
        device.wait_label("Continue (development sign-in)")
        notes.append("signed in again, signed out from Settings, and a cold start stayed signed out")

    if extended:
        # mobile-e2e: every primary tab finishes loading for a signed-in session without an error banner.
        # Nav buttons are labelled "<Name> tab", so an exact "<Name>" label is the selected page header.
        tour: dict[str, dict[str, str]] = {}
        for tab, header, content in (("Tasks tab", "Tasks", ""), ("Usage tab", "Usage", " of 20 used"),
                                     ("Memory tab", "Memory", "")):
            if journey.steps["logout_expiration"]["status"] != "PASS":
                tour[tab] = {"status": "BLOCKED", "observation": "prerequisite not passed: logout_expiration"}
                continue
            try:
                if "Continue (development sign-in)" in {n.label for n in device.nodes()}:
                    device.tap_label("Continue (development sign-in)")
                    device.wait_label("Chat tab")
                device.tap_label(tab)
                def loaded(nodes: list[Node], header: str = header, content: str = content) -> bool:
                    labels = [n.label for n in nodes]
                    return (header in labels and not any(label.startswith("Loading") for label in labels)
                            and any(content in label for label in labels))
                shown = [n.label.replace("\n", " ") for n in device.wait(loaded, f"{tab} loaded")]
                errors = [label for label in shown if re.search(r"(?i)could not|couldn't", label)]
                if errors:
                    raise StepFailed(f"error banner: {errors[0][:100]}")
                summary = next((label for label in shown if content and content in label), f"{header} page loaded")
                tour[tab] = {"status": "PASS", "observation": summary[:120]}
            except (StepFailed, subprocess.TimeoutExpired) as failure:
                tour[tab] = {"status": "FAIL", "observation": str(failure)}
        extras["extended_navigation"] = tour
    return extras


def collect_logs(device: Device, since: str, output: Path, sensitive: list[str]) -> list[str]:
    """Only this app's processes (logcat can hold other apps' private data) plus crash-buffer lines."""
    app = device.adb("logcat", "-d", "-v", "threadtime", "-T", since, timeout=60).stdout.splitlines()
    crash = device.adb("logcat", "-d", "-b", "crash", "-v", "threadtime", "-T", since, timeout=60).stdout.splitlines()
    def scoped(line: str) -> bool:
        fields = line.split(maxsplit=3)
        return (len(fields) > 2 and fields[2] in device.pids) or PACKAGE in line
    crashes = [line for line in crash if PACKAGE in line or scoped(line)]
    for name, lines in (("logcat-app.txt", [line for line in app if scoped(line)]), ("logcat-crash.txt", crashes)):
        text = "\n".join(lines)
        for value in sensitive:
            text = text.replace(value, "[REDACTED]")
        text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
        (output / name).write_text(text + "\n", encoding="utf-8")
    return crashes


def drive(karmi: Path, output: Path, serial: str, apk_sha256: str | None, candidate: str,
          extended: bool, before_shutdown: Callable[[Path], None]) -> Path:
    """Run the journey, write driver evidence, then call `before_shutdown` while the backend is live."""
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    shots = output / "screenshots"
    shots.mkdir(exist_ok=True)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise Blocked(f"127.0.0.1:{PORT} is in use; stop the local Karmi server before the device run")
    device = Device(serial, shots)
    since = device.adb("shell", "date", "+%m-%d %H:%M:%S.000").stdout.strip()
    workdir = Path(tempfile.mkdtemp(prefix="karmi-device-"))
    backend = Backend(karmi, workdir, output / "backend-access.log")
    journey = Journey()
    extras: dict[str, object] = {}
    try:
        device.reverse(True)
        device.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        backend.start()
        extras = run(journey, device, backend, extended)
        crashes = collect_logs(device, since, output, [backend.secret])
        if crashes:
            journey.record("launch", "FAIL", f"app crash recorded in logcat crash buffer ({len(crashes)} lines)")
        steps_file = output / "steps.json"
        steps_file.write_text(json.dumps({
            "schema_version": 1, "method": "automated-uiautomator", "reviewer": REVIEWER,
            "karmi_sha": candidate, "apk_sha256": apk_sha256, "serial": serial, "captured_at": utc(),
            "steps": [journey.steps[step] for step in STEPS], **extras,
        }, indent=2) + "\n", encoding="utf-8")
        before_shutdown(steps_file)
        return steps_file
    finally:
        backend.stop()
        device.reverse(True)
        shutil.rmtree(workdir, ignore_errors=True)
