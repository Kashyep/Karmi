"""Local OpenAI/OpenRouter-compatible fake provider plus a device-test backend launcher.

Development only. Nothing here talks to a real model provider.

    python scripts/dev_fake_provider.py fake            # fake OpenRouter on 127.0.0.1:8900
    python scripts/dev_fake_provider.py serve-backend   # Karmi API, fake provider, fresh SQLite

``serve-backend`` points the adapter's OpenRouter URL constants at the fake BEFORE the app is
imported, refuses to start if they still name openrouter.ai, and installs an httpx transport
guard that refuses any outbound request to openrouter.ai (logged to the backend's stderr).

Canned replies are chosen by keyword in the last user message, in this priority order:
``fail`` (HTTP 503), ``slow`` (12 s before the first token), ``long`` (~3000 words with
headings), ``render`` (markdown rendering probe), ``hindi`` (long Devanagari), otherwise an echo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FAKE_HOST = "127.0.0.1"
FAKE_PORT = 8900
FAKE_BASE_URL = f"http://{FAKE_HOST}:{FAKE_PORT}/api/v1"
FAKE_CHAT_URL = f"{FAKE_BASE_URL}/chat/completions"
FAKE_KEY = "fake-local-key"
REAL_HOST_SUFFIX = "openrouter.ai"
TOKEN_DELAY_S = float(os.environ.get("FAKE_TOKEN_DELAY", "0.012"))
SLOW_DELAY_S = 12.0

RENDER_TEXT = (
    "**What is hashing?**\n"
    "It maps arbitrary input to a fixed-size value.\n"
    "\n"
    "> A quoted line of text\n"
    "\n"
    "After the quote, a line with a break.\n"
    "\n"
    "```python\n"
    'if a < b and c & d:\n'
    '    print("ok")\n'
    "```\n"
    "\n"
    "Scale check: 2³² → x\n"
)

_SENTENCES = [
    "Hashing turns a key of any length into a value of fixed size, which makes lookups cheap.",
    "A good hash spreads inputs evenly so that buckets stay short and collisions stay rare.",
    "Cryptographic hashes add preimage resistance, so the input cannot be recovered from the digest.",
    "Checksums and hash tables solve different problems, even though both reduce data to a number.",
    "When the table grows, the load factor rises and the structure is rebuilt with more buckets.",
    "Open addressing keeps everything in one array, while chaining stores a list in each bucket.",
    "Salts make identical passwords hash differently, which defeats precomputed lookup tables.",
    "Rolling hashes let a search slide a window across text without recomputing the whole digest.",
]
_TOPICS = [
    "Foundations", "Collisions", "Hash tables", "Cryptographic digests",
    "Password storage", "Practical choices",
]


def _long_reply() -> str:
    parts = [
        "# Hashing in depth\n",
        "This reply is generated for layout testing. It has headings, long paragraphs and lists.\n",
    ]
    index = 0
    for number, topic in enumerate(_TOPICS, start=1):
        parts.append(f"\n## {number}. {topic}\n")
        for _ in range(4):
            sentences = [_SENTENCES[(index + k) % len(_SENTENCES)] for k in range(6)]
            index += 3
            parts.append(" ".join(sentences) + "\n")
        parts.append("\n- First point about " + topic.lower() + ".\n- Second point, with detail.\n")
    parts.append("\n## Summary\n" + " ".join(_SENTENCES) + "\n")
    return "".join(parts)


_HINDI_PARAGRAPH = (
    "हैशिंग एक ऐसी तकनीक है जिसमें किसी भी आकार के इनपुट को एक निश्चित आकार के मान में बदला जाता है। "
    "इससे खोज तेज़ होती है और डेटा को संक्षिप्त रूप में संग्रहीत किया जा सकता है। "
)


def _hindi_reply() -> str:
    parts = ["## हैशिंग का परिचय\n"]
    for number in range(1, 13):
        parts.append(f"\n### भाग {number}\n" + _HINDI_PARAGRAPH * 3 + "\n")
    return "".join(parts)


def _last_user_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            return ""
    return ""


def _choose(user_text: str, model: str) -> tuple[int, str, float]:
    """Return (status, reply text, pre-token delay seconds)."""
    lowered = user_text.lower()
    if "fail" in lowered:
        return 503, "", 0.0
    if "slow" in lowered:
        return 200, "Slow reply finished after a long wait.", SLOW_DELAY_S
    if "long" in lowered:
        return 200, _long_reply(), 0.0
    if "render" in lowered:
        return 200, RENDER_TEXT, 0.0
    if "hindi" in lowered:
        return 200, _hindi_reply(), 0.0
    return 200, f"Fake echo from {model}: {user_text.strip()}", 0.0


def _pieces(text: str) -> list[str]:
    # Word plus trailing whitespace, so newlines survive as separate tokens.
    return re.findall(r"\S+\s*|\s+", text)


class FakeHandler(BaseHTTPRequestHandler):
    server_version = "FakeOpenRouter/1"
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        sys.stderr.write(f"[fake] {self.address_string()} {format % args}\n")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") in {"", "/health"}:
            self._json(200, {"status": "fake-openrouter-ok"})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        if not self.headers.get("Authorization", "").startswith("Bearer "):
            self._json(401, {"error": {"message": "missing bearer token"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid json"}})
            return
        model = str(body.get("model", "unknown"))
        status, text, delay = _choose(_last_user_text(body.get("messages", [])), model)
        if status != 200:
            self._json(status, {"error": {"message": "fake upstream unavailable", "code": status}})
            return
        if delay:
            time.sleep(delay)
        usage = {"prompt_tokens": 42, "completion_tokens": max(1, len(text) // 4), "cost": 0}
        completion_id = f"fake-{int(time.time() * 1000)}"
        if body.get("stream") is True:
            self._stream(completion_id, model, text, usage)
        else:
            self._json(
                200,
                {
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": text},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": usage,
                },
            )

    def _stream(self, completion_id: str, model: str, text: str, usage: dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit(payload: dict[str, Any]) -> None:
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        base = {"id": completion_id, "object": "chat.completion.chunk", "model": model}
        for piece in _pieces(text):
            emit({**base, "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]})
            time.sleep(TOKEN_DELAY_S)
        emit({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": usage})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


def serve_fake(args: argparse.Namespace) -> int:
    server = ThreadingHTTPServer((args.host, args.port), FakeHandler)
    print(f"fake OpenRouter-compatible provider on {FAKE_CHAT_URL}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _install_url_guard(httpx: Any) -> list[str]:
    blocked: list[str] = []
    original = httpx.HTTPTransport.handle_request

    def guarded(self: Any, request: Any) -> Any:
        host = request.url.host or ""
        if host == REAL_HOST_SUFFIX or host.endswith("." + REAL_HOST_SUFFIX):
            blocked.append(str(request.url))
            sys.stderr.write(f"[guard] BLOCKED outbound request to {host}\n")
            raise httpx.ConnectError("blocked by dev_fake_provider URL guard")
        return original(self, request)

    httpx.HTTPTransport.handle_request = guarded
    return blocked


def serve_backend(args: argparse.Namespace) -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / f"device-test-{stamp}.db"
    # Env vars take precedence over the .env files Settings would otherwise read.
    os.environ.update(
        {
            "DAILY_AGENT_ENVIRONMENT": "development",
            "DAILY_AGENT_DATABASE_URL": f"sqlite+pysqlite:///{db_path}",
            "DAILY_AGENT_DATA_DIR": str(data_dir),
            "DAILY_AGENT_LIVE_MODELS_ENABLED": "true",
            "DAILY_AGENT_OPENROUTER_ENABLED": "true",
            "DAILY_AGENT_OPENROUTER_API_KEY": FAKE_KEY,
            "DAILY_AGENT_GATEWAY_DAILY_REQUEST_LIMIT": "100000",
            "DAILY_AGENT_RATE_LIMIT_PER_MINUTE": "600",
        }
    )
    # Imported before the app so the patched constants are the ones the app uses.
    import httpx

    from daily_agent.gateway import adapters

    adapters.OPENROUTER_BASE_URL = FAKE_BASE_URL
    adapters.OPENROUTER_CHAT_URL = FAKE_CHAT_URL
    if REAL_HOST_SUFFIX in adapters.OPENROUTER_CHAT_URL or REAL_HOST_SUFFIX in adapters.OPENROUTER_BASE_URL:
        sys.stderr.write("refusing to start: OpenRouter URL still points at openrouter.ai\n")
        return 2
    blocked = _install_url_guard(httpx)

    import uvicorn

    from daily_agent.api import app

    print(
        json.dumps(
            {
                "backend": f"http://127.0.0.1:{args.port}",
                "database": str(db_path),
                "openrouter_chat_url": adapters.OPENROUTER_CHAT_URL,
                "live_models": True,
                "provider_key": "fake-local-key (fake)",
                "outbound_openrouter_blocked_so_far": len(blocked),
            },
            indent=2,
        ),
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    fake = sub.add_parser("fake", help="run the fake provider")
    fake.add_argument("--host", default=FAKE_HOST)
    fake.add_argument("--port", type=int, default=FAKE_PORT)
    fake.set_defaults(func=serve_fake)
    backend = sub.add_parser("serve-backend", help="run the Karmi API wired to the fake provider")
    backend.add_argument("--port", type=int, default=8000)
    backend.set_defaults(func=serve_backend)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
