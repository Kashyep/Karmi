from __future__ import annotations

import base64
import http.server
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from daily_agent.web.admin_page import admin_page_headers, render_admin_page

ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "src" / "daily_agent" / "web" / "static"
OUT_DIR = ROOT / "docs" / "release1" / "admin-web"

# 1x1 transparent PNG
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class MockAdminHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/admin":
            html = render_admin_page(publishable_key=None)
            headers = admin_page_headers(publishable_key=None)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        if path.startswith("/static/"):
            file_name = path.removeprefix("/static/")
            file_path = STATIC_DIR / file_name
            if file_path.is_file():
                content = file_path.read_bytes()
                media_type = "text/javascript" if file_name.endswith(".js") else "text/css"
                self.send_response(200)
                self.send_header("Content-Type", f"{media_type}; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
        if path == "/v1/admin/session":
            self.send_response(404)
            self.end_headers()
            return

        if path == "/v1/admin/dev-candidates":
            self._send_json({"items": [{"user_id": "usr_dev_admin", "email": "admin@example.com"}]})
            return
        if path == "/v1/admin/monitor":
            self._send_json({
                "generated_at": "2026-11-07T12:00:00Z",
                "requests_today": 1420,
                "daily_request_cap": 5000,
                "success_rate": 0.998,
                "open_bug_reports": 7,
                "cost_today_inr": 12450.50,
                "spend_today_inr": 12450.50,
                "platform_budget_inr": 100000.00,
                "active_users": 182,
                "active_streams": 3,
                "req_per_min": 24,
                "error_rate": 0.002,
                "p95_latency_ms": 320,
                "model_health": [
                    {
                        "model": "claude-3-5-sonnet",
                        "provider": "anthropic",
                        "last_success_at": "2026-11-07T11:59:00Z",
                        "error_rate": 0.001,
                        "p50_latency_ms": 280,
                        "runs": 850,
                    },
                    {
                        "model": "gemini-1.5-pro",
                        "provider": "google",
                        "last_success_at": "2026-11-07T11:58:30Z",
                        "error_rate": 0.003,
                        "p50_latency_ms": 310,
                        "runs": 570,
                    },
                ],
                "provider_health": [
                    {"provider": "anthropic", "status": "ok"},
                    {"provider": "google", "status": "ok"},
                ],
            })
            return

        if path == "/v1/admin/users":
            self._send_json({
                "items": [
                    {
                        "id": "usr_1",
                        "email": "user1@example.com",
                        "display_name": "Aarav Sharma",
                        "tier": "parth",
                        "effective_plan": "parth",
                        "disabled": False,
                        "open_bug_reports": 1,
                        "created_at": "2026-10-01T00:00:00Z",
                    }
                ],
                "next_cursor": None,
            })
            return

        if path == "/v1/admin/bug-reports":
            self._send_json({
                "items": [
                    {
                        "id": "br_001",
                        "ticket": "TICK-101",
                        "category": "ui",
                        "status": "new",
                        "description_preview": "Header bar misaligned on mobile viewport after rotation",
                        "user_id": "usr_99",
                        "user_display_name": "Aarav Sharma",
                        "has_screenshot": True,
                        "created_at": "2026-11-07T08:30:00Z",
                        "updated_at": "2026-11-07T08:30:00Z",
                    },
                    {
                        "id": "br_002",
                        "ticket": "TICK-102",
                        "category": "latency",
                        "status": "in_progress",
                        "description_preview": "High latency during peak evening hours in stream session",
                        "user_id": "usr_88",
                        "user_display_name": "Priya Patel",
                        "has_screenshot": False,
                        "created_at": "2026-11-07T07:15:00Z",
                        "updated_at": "2026-11-07T09:00:00Z",
                    },
                ],
                "next_cursor": None,
            })
            return

        if path == "/v1/admin/bug-reports/br_001":
            self._send_json({
                "id": "br_001",
                "ticket": "TICK-101",
                "category": "ui",
                "status": "new",
                "description": "Header bar misaligned on mobile viewport after rotation. The header overlaps the first message in the chat thread.",
                "diagnostics": {
                    "device": "Pixel 8",
                    "os": "Android 14",
                    "app_version": "1.4.0",
                    "screen_density": 2.75,
                },
                "user": {
                    "id": "usr_99",
                    "display_name": "Aarav Sharma",
                    "plan": "yanta",
                },
                "has_screenshot": True,
                "admin_notes": "Needs reproduction on emulator.",
                "created_at": "2026-11-07T08:30:00Z",
                "updated_at": "2026-11-07T08:30:00Z",
                "triaged_at": None,
                "resolved_at": None,
            })
            return

        if path == "/v1/admin/bug-reports/br_001/screenshot":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(TINY_PNG)))
            self.end_headers()
            self.wfile.write(TINY_PNG)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/dev/token":
            self._send_json({"token": "dev_jwt_123"})
            return
        if path == "/v1/admin/dev-token":
            self._send_json({"token": "dev_token_123"})
            return
        if path == "/v1/admin/session":
            self._send_json({"admin_session_token": "sess_123", "expires_at": "2035-01-01T00:00:00Z"})
            return
        self.send_response(404)
        self.end_headers()

    def _send_json(self, data: object) -> None:
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_screenshots(port: int = 8917) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    server = http.server.HTTPServer(("127.0.0.1", port), MockAdminHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)

    js_runner = f"""
    const pw = require('playwright');
    (async () => {{
      const browser = await pw.chromium.launch({{
        executablePath: '/home/rosso/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',
        args: ['--no-sandbox', '--disable-gpu']
      }});

      for (const width of [1440, 360]) {{
        const height = width === 360 ? 780 : 900;
        const context = await browser.newContext({{
          viewport: {{ width, height }},
          deviceScaleFactor: 1
        }});
        const page = await context.newPage();
        page.on('console', msg => console.log('PAGE LOG:', msg.text()));
        page.on('pageerror', err => console.log('PAGE ERROR:', err.message));
        await page.goto('http://127.0.0.1:{port}/admin');
        // Click dev sign-in
        await page.waitForSelector('#dev-signin-button', {{ state: 'visible' }});
        await page.click('#dev-signin-button');

        // Enter code
        await page.waitForSelector('#code-input', {{ state: 'visible' }});
        await page.fill('#code-input', 'mock-code');
        await page.click('#code-submit');

        // Wait for dashboard
        await page.waitForSelector('#dashboard-heading', {{ state: 'visible' }});

        // 1. Overview screenshot (Monitor tab)
        await page.click('#tab-monitor');
        await page.waitForSelector('#monitor-metrics dt', {{ state: 'visible' }});
        await page.waitForTimeout(300);
        await page.screenshot({{ path: '{OUT_DIR}/overview-' + width + '.png', fullPage: false }});

        // 2. Bug inbox list screenshot
        await page.click('#tab-bugs');
        await page.waitForSelector('.bug-row', {{ state: 'visible' }});
        await page.waitForTimeout(300);
        await page.screenshot({{ path: '{OUT_DIR}/bug-inbox-list-' + width + '.png', fullPage: false }});

        // 3. Bug detail screenshot
        await page.click('.bug-row button.link-button');
        await page.waitForSelector('#bug-detail-body:not([hidden])', {{ state: 'visible' }});
        await page.waitForTimeout(300);
        await page.screenshot({{ path: '{OUT_DIR}/bug-detail-' + width + '.png', fullPage: false }});

        await context.close();
      }}

      await browser.close();
    }})();
    """

    env = dict(os.environ)
    env["NODE_PATH"] = "/home/rosso/Projects/AxiomFrontend/node_modules"
    res = subprocess.run(  # noqa: S603
        ["node", "-e", js_runner], env=env, capture_output=True, text=True  # noqa: S607
    )
    if res.returncode != 0:
        raise RuntimeError(f"Playwright screenshot failed: {res.stderr}\n{res.stdout}")
    print("Screenshots captured successfully!")


if __name__ == "__main__":
    run_screenshots()
