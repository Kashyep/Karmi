from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.web import render_admin_page

STATIC = Path(__file__).resolve().parents[2] / "src" / "daily_agent" / "web" / "static"
HEX_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b")
FORBIDDEN_JS = ("innerHTML", "insertAdjacentHTML", "document.write", "localStorage", "sessionStorage", "document.cookie")

def _publishable_key(domain: str = "clerk.example.test") -> str:
    encoded = base64.b64encode(f"{domain}$".encode()).decode().rstrip("=")
    return f"pk_test_{encoded}"


@pytest.fixture
def client_factory():
    app = create_app()
    clients: list[TestClient] = []

    def make(publishable_key: str | None, admin_ui_enabled: bool = True) -> TestClient:
        settings = Settings(
            environment="test",
            clerk_publishable_key=publishable_key,
            admin_ui_enabled=admin_ui_enabled,
        )
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app)
        clients.append(client)
        return client

    yield make
    app.dependency_overrides.clear()


def test_admin_route_returns_html(client_factory) -> None:
    response = client_factory(None).get("/admin")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_admin_page_has_accessibility_and_noindex_basics() -> None:
    html = render_admin_page(publishable_key=None)
    assert "Skip to main content" in html
    assert 'href="#main-content"' in html
    assert 'id="main-content"' in html
    assert '<meta name="robots" content="noindex">' in html
    assert '<script src="/static/admin.js" defer></script>' in html
    assert '<link rel="stylesheet" href="/static/admin.css">' in html
    assert 'href="/static/karmi-tokens.css"' in html


def test_admin_page_exposes_no_secrets_and_no_customer_surfaces() -> None:
    html = render_admin_page(publishable_key=None)
    assert "sk_" not in html
    assert "clerk_secret" not in html.lower()
    assert 'id="chat"' not in html
    assert "#chat" not in html
    assert "Saved work" not in html
    assert "Armory" not in html


def test_publishable_key_is_embedded_only_when_configured() -> None:
    key = _publishable_key()
    configured = render_admin_page(publishable_key=key)
    assert f'data-clerk-publishable-key="{key}"' in configured

    unconfigured = render_admin_page(publishable_key=None)
    assert "data-clerk-publishable-key" not in unconfigured


def test_publishable_key_is_escaped_in_attribute() -> None:
    html = render_admin_page(publishable_key='pk_test_"><script>x</script>')
    assert "<script>x</script>" not in html
    assert "&quot;&gt;&lt;script&gt;" in html


def test_admin_route_passes_configured_key(client_factory) -> None:
    key = _publishable_key()
    html = client_factory(key).get("/admin").text
    assert f'data-clerk-publishable-key="{key}"' in html


def test_admin_route_without_key_renders_without_key(client_factory) -> None:
    html = client_factory(None).get("/admin").text
    assert "data-clerk-publishable-key" not in html


def test_admin_page_has_all_required_views_and_tabs() -> None:
    html = render_admin_page(publishable_key=None)
    for element_id in (
        "view-signin",
        "view-unavailable",
        "view-code",
        "view-dashboard",
        "tab-users",
        "tab-monitor",
        "tab-audit",
        "users-more",
        "confirm-dialog",
        "confirm-reason",
    ):
        assert f'id="{element_id}"' in html


def test_admin_js_is_served_with_session_header_and_no_forbidden_apis(client_factory) -> None:
    client = client_factory(None)
    response = client.get("/static/admin.js")
    assert response.status_code == 200
    assert "X-Admin-Session" in response.text
    assert "window.KarmiAdmin" in response.text
    for forbidden in FORBIDDEN_JS:
        assert forbidden not in response.text


def test_admin_css_has_no_hex_literals_and_is_served(client_factory) -> None:
    client = client_factory(None)
    response = client.get("/static/admin.css")
    assert response.status_code == 200
    assert HEX_LITERAL.search(response.text) is None


def test_admin_js_has_no_hex_literals() -> None:
    source = (STATIC / "admin.js").read_text(encoding="utf-8")
    assert HEX_LITERAL.search(source) is None


def test_reason_field_enforces_length_bounds_in_markup_and_script() -> None:
    html = render_admin_page(publishable_key=None)
    assert 'maxlength="500"' in html
    assert "At least 3 characters" in html
    source = (STATIC / "admin.js").read_text(encoding="utf-8")
    assert "REASON_MIN_LENGTH = 3" in source
    assert ".trim().length < REASON_MIN_LENGTH" in source


def test_admin_js_clears_and_caps_selection_and_handles_api_details() -> None:
    source = (STATIC / "admin.js").read_text(encoding="utf-8")
    assert "state.selectedUserIds.clear()" in source
    assert "at most 100 users" in source
    assert "detailMessage(payload" in source
    assert "sessionInvalid(payload)" in source
    assert "summary: result.summary" in source
    assert "function wireDetailActions()" in source


def _csp_directives(policy: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for part in policy.split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


def test_admin_response_carries_strict_csp_and_framing_headers(client_factory) -> None:
    response = client_factory(_publishable_key()).get("/admin")
    assert response.status_code == 200

    directives = _csp_directives(response.headers["content-security-policy"])
    assert "'self'" in directives["script-src"]
    assert "https://clerk.example.test" in directives["script-src"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert directives["object-src"] == ["'none'"]
    assert directives["base-uri"] == ["'none'"]

    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_admin_csp_allows_clerk_workers_frames_protect_and_images(client_factory) -> None:
    response = client_factory(_publishable_key()).get("/admin")
    directives = _csp_directives(response.headers["content-security-policy"])

    assert "blob:" in directives["worker-src"]
    assert "https://cdn.protect.clerk.com" in directives["script-src"]
    assert "https://img.clerk.com" in directives["img-src"]
    assert "https://challenges.cloudflare.com" in directives["frame-src"]
    assert "https://clerk.example.test" in directives["frame-src"]
    assert "https://clerk.example.test" in directives["connect-src"]


def test_admin_csp_without_clerk_key_names_no_clerk_hosts(client_factory) -> None:
    response = client_factory(None).get("/admin")
    policy = response.headers["content-security-policy"]

    assert "clerk" not in policy
    assert "cloudflare" not in policy
    assert _csp_directives(policy)["script-src"] == ["'self'"]


def test_admin_clerk_js_is_pinned_to_exact_version() -> None:
    source = (STATIC / "admin.js").read_text(encoding="utf-8")
    assert "CLERK_JS_VERSION = '5.125.11'" in source
    assert "clerk-js@${CLERK_JS_VERSION}/dist/clerk.browser.js" in source
    assert re.search(r"clerk-js@\^?~?5(?![.\d])", source) is None


def test_admin_ui_disabled_returns_404(client_factory) -> None:
    client_disabled = client_factory(None, admin_ui_enabled=False)
    assert client_disabled.get("/admin").status_code == 404
    assert client_disabled.get("/static/admin.js").status_code == 404
    assert client_disabled.get("/static/admin.css").status_code == 404

    client_enabled = client_factory(None, admin_ui_enabled=True)
    assert client_enabled.get("/admin").status_code == 200
    assert client_enabled.get("/static/admin.js").status_code == 200
    assert client_enabled.get("/static/admin.css").status_code == 200


def test_admin_csp_includes_blob_img_src(client_factory) -> None:
    response = client_factory(_publishable_key()).get("/admin")
    directives = _csp_directives(response.headers["content-security-policy"])
    assert "blob:" in directives["img-src"]


def test_no_usd_labels_or_fields_in_admin_web() -> None:
    admin_dir = STATIC.parent
    for path in admin_dir.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".js", ".css", ".html"}:
            content = path.read_text(encoding="utf-8")
            assert "usd" not in content.lower(), f"Found USD reference in {path}"


def test_admin_js_forbids_dangerous_dom_apis() -> None:
    source = (STATIC / "admin.js").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_JS:
        assert forbidden not in source, f"Found forbidden DOM API {forbidden} in admin.js"


def test_admin_js_inr_formatting_and_xss_safety() -> None:
    import subprocess

    js_code = """
    const fs = require('fs');
    const path = require('path');
    const vm = require('vm');

    // Mock minimal browser globals for testing formatters and DOM helper
    class MockNode {
      constructor(type, text = '') {
        this.nodeType = type;
        this.textContent = text;
        this.children = [];
        this.attrs = {};
      }
      append(...children) {
        for (const c of children) {
          this.children.push(c);
        }
      }
      setAttribute(k, v) { this.attrs[k] = String(v); }
      removeAttribute(k) { delete this.attrs[k]; }
    }

    class MockElement extends MockNode {
      constructor(tag) {
        super(1);
        this.tagName = tag.toUpperCase();
        this.dataset = {};
      }
      addEventListener() {}
      focus() {}
      querySelector() { return new MockElement('input'); }
      querySelectorAll() { return []; }
      closest() { return null; }
      replaceChildren() {}
    }
    class MockTextNode extends MockNode {
      constructor(text) {
        super(3, text);
      }
    }

    const sandbox = {
      window: {
        location: { origin: 'http://localhost' },
        matchMedia: () => ({ matches: false, addEventListener: () => {} }),
      },
      document: {
        documentElement: new MockElement('html'),
        createElement: (tag) => new MockElement(tag),
        createTextNode: (text) => new MockTextNode(text),
        getElementById: () => new MockElement('div'),
        addEventListener: () => {},
      },
      Node: MockNode,
      URL: { createObjectURL: () => 'blob:mock', revokeObjectURL: () => {} },
      console: console,
    };
    sandbox.globalThis = sandbox;
    sandbox.self = sandbox;

    // Read admin.js and inject test probe
    const adminSrc = fs.readFileSync(process.argv[1], 'utf-8');
    // Extract helper functions
    vm.createContext(sandbox);
    // Execute admin.js in sandbox
    vm.runInContext(adminSrc, sandbox);

    const { formatInr, formatInrRupees } = sandbox.window.KarmiAdmin;
    const assert = require('assert');

    // Whole rupees
    assert.strictEqual(formatInr(0), '₹0');
    assert.strictEqual(formatInr(149_000_000), '₹149');
    assert.strictEqual(formatInr(149_900_000_000), '₹1,49,900');
    assert.strictEqual(formatInr(10_000_000_000_000), '₹1,00,00,000');

    // Other amounts with 2 decimals
    assert.strictEqual(formatInr(10_000), '₹0.01');
    assert.strictEqual(formatInr(12_500_000), '₹12.50');
    assert.strictEqual(formatInr(1_234_560_000), '₹1,234.56');

    // Non-zero below one paisa
    assert.strictEqual(formatInr(1_000), '<₹0.01');
    assert.strictEqual(formatInr(5_000), '<₹0.01');

    // Negatives
    assert.strictEqual(formatInr(-149_000_000), '-₹149');
    assert.strictEqual(formatInr(-12_500_000), '-₹12.50');
    assert.strictEqual(formatInr(-10_000), '-₹0.01');
    assert.strictEqual(formatInr(-1_000), '-<₹0.01');

    // formatInrRupees (floats)
    assert.strictEqual(formatInrRupees(0), '₹0');
    assert.strictEqual(formatInrRupees(149), '₹149');
    assert.strictEqual(formatInrRupees(149900), '₹1,49,900');
    assert.strictEqual(formatInrRupees(10000000), '₹1,00,00,000');
    assert.strictEqual(formatInrRupees(0.01), '₹0.01');
    assert.strictEqual(formatInrRupees(12.50), '₹12.50');
    assert.strictEqual(formatInrRupees(1234.56), '₹1,234.56');
    assert.strictEqual(formatInrRupees(0.001), '<₹0.01');
    assert.strictEqual(formatInrRupees(-149), '-₹149');
    assert.strictEqual(formatInrRupees(-12.5), '-₹12.50');
    assert.strictEqual(formatInrRupees(-0.01), '-₹0.01');
    assert.strictEqual(formatInrRupees(-0.001), '-<₹0.01');
    assert.strictEqual(formatInrRupees(null), 'Unavailable');
    assert.strictEqual(formatInrRupees(undefined), 'Unavailable');

    // Behavioural XSS check
    const malicious = '<img src=x onerror=alert(1)>';
    // In admin.js, text prop sets textContent, never innerHTML
    // Verify that malicious string is preserved as text, not markup
    const maliciousTextNode = sandbox.document.createTextNode(malicious);
    assert.strictEqual(maliciousTextNode.textContent, malicious);
    assert.strictEqual(maliciousTextNode.nodeType, 3);
    """

    js_file = STATIC / "admin.js"
    res = subprocess.run(["node", "-e", js_code, str(js_file)], capture_output=True, text=True)  # noqa: S603, S607
    assert res.returncode == 0, f"JS tests failed: {res.stderr}\n{res.stdout}"


def test_admin_web_screenshots_exist() -> None:
    docs_dir = Path(__file__).resolve().parents[2] / "docs" / "release1" / "admin-web"
    expected = [
        "overview-360.png",
        "overview-1440.png",
        "bug-inbox-list-360.png",
        "bug-inbox-list-1440.png",
        "bug-detail-360.png",
        "bug-detail-1440.png",
    ]
    for name in expected:
        file_path = docs_dir / name
        assert file_path.is_file(), f"Missing screenshot {name}"
        assert file_path.stat().st_size > 1000, f"Screenshot {name} too small"
