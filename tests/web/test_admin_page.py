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
FORBIDDEN_JS = (
    "innerHTML",
    "insertAdjacentHTML",
    "document.write",
    "localStorage",
    "sessionStorage",
    "document.cookie",
)


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
    assert "sessionInvalid" not in source
    assert "detail.message" in source
    assert "$('detail-profile').replaceChildren()" in source
    assert "$('edit-admin-notes').value = ''" in source
    assert "$('edit-bug-notes').value = ''" in source
    assert "$('edit-bug-reason').value = ''" in source
    assert "summary: result.summary" in source
    assert "function wireDetailActions()" in source


def test_admin_js_user_patch_sends_empty_string_for_cleared_notes_and_tester_label() -> None:
    source = (STATIC / "admin.js").read_text(encoding="utf-8")
    assert "tester_label: $('edit-tester-label').value.trim()," in source
    assert "admin_notes: $('edit-admin-notes').value.trim()," in source
    assert "display_name: $('edit-display-name').value.trim() || null," in source
    assert "tester_label: $('edit-tester-label').value.trim() || null" not in source
    assert "admin_notes: $('edit-admin-notes').value.trim() || null" not in source


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
    assert directives["default-src"] == ["'self'"]
    assert directives["style-src"] == ["'self'", "'unsafe-inline'"]
    assert "'self'" in directives["script-src"]
    assert "https://clerk.example.test" in directives["script-src"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert directives["object-src"] == ["'none'"]
    assert directives["base-uri"] == ["'none'"]

    # Minimum directive allowed: no unsafe-eval, no wildcard origins
    assert "'unsafe-eval'" not in response.headers["content-security-policy"]
    assert "*" not in directives["style-src"]
    assert "*" not in directives["script-src"]

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
    directives = _csp_directives(policy)
    assert directives["default-src"] == ["'self'"]
    assert directives["style-src"] == ["'self'"]
    assert directives["script-src"] == ["'self'"]
    assert "'unsafe-inline'" not in directives["style-src"]
    assert "'unsafe-eval'" not in policy
    assert "*" not in directives["style-src"]
    assert "*" not in directives["script-src"]


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


def test_admin_static_traversal_returns_404_when_admin_disabled(client_factory) -> None:
    client_disabled = client_factory(None, admin_ui_enabled=False)
    assert client_disabled.get("/static/icons%2F..%2Fadmin.js").status_code == 404
    assert client_disabled.get("/static/icons%2F..%2Fadmin.css").status_code == 404
    assert client_disabled.get("/static/karmi-tokens.css").status_code == 200


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
    """Verify admin.js INR formatting and DOM XSS safety in a Node VM sandbox.

    Node.js is required for the admin.js VM tests. If node is absent from PATH,
    this test fails loudly.
    """
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.fail("node is required for the admin.js VM tests; install Node.js (CI must have it)")

    js_code = """
    const fs = require('fs');
    const path = require('path');
    const vm = require('vm');
    const assert = require('assert');

    const recordedInnerHTML = [];
    const createdElements = [];
    const recordedTextNodes = [];

    class MockNode {
      constructor(type, text = '') {
        this.nodeType = type;
        this.children = [];
        this.attrs = {};
        if (type === 3) {
          this._textContent = String(text);
          recordedTextNodes.push(String(text));
        }
      }
      get textContent() {
        if (this.nodeType === 3) return this._textContent;
        return this.children.map(c => c.textContent).join('');
      }
      set textContent(text) {
        if (this.nodeType === 3) {
          this._textContent = String(text);
          recordedTextNodes.push(String(text));
        } else {
          this.children = [];
          if (text !== '') {
            const tn = new MockTextNode(String(text));
            this.children.push(tn);
          }
        }
      }
      append(...children) {
        for (const c of children) {
          if (c instanceof MockNode) this.children.push(c);
          else if (c !== null && c !== undefined && c !== false) {
            this.children.push(new MockTextNode(String(c)));
          }
        }
      }
      setAttribute(k, v) { this.attrs[k] = String(v); }
      getAttribute(k) { return this.attrs[k]; }
      removeAttribute(k) { delete this.attrs[k]; }
    }

    class MockElement extends MockNode {
      constructor(tag) {
        super(1);
        this.tagName = tag.toUpperCase();
        this.dataset = {};
        this.value = '';
        this.hidden = false;
        this.className = '';
        this.classList = {
          add: (c) => { this.className = (this.className ? this.className + ' ' : '') + c; },
          remove: (c) => {},
          toggle: (c, force) => {},
        };
        createdElements.push(this);
      }
      get innerHTML() { return ''; }
      set innerHTML(val) { recordedInnerHTML.push(String(val)); }
      insertAdjacentHTML() { throw new Error('insertAdjacentHTML is forbidden'); }
      addEventListener() {}
      focus() {}
      querySelector() { return new MockElement('input'); }
      querySelectorAll() { return []; }
      closest() { return null; }
      replaceChildren(...children) {
        this.children = [];
        for (const c of children) {
          if (c instanceof MockNode) this.children.push(c);
          else if (c !== null && c !== undefined && c !== false) {
            this.children.push(new MockTextNode(String(c)));
          }
        }
      }
    }

    class MockTextNode extends MockNode {
      constructor(text) {
        super(3, text);
      }
    }

    const elements = new Map();
    function getOrCreate(id) {
      if (!elements.has(id)) {
        const el = new MockElement('div');
        el.id = id;
        elements.set(id, el);
      }
      return elements.get(id);
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
        getElementById: (id) => getOrCreate(id),
        addEventListener: () => {},
      },
      Node: MockNode,
      URL: { createObjectURL: () => 'blob:mock', revokeObjectURL: () => {} },
      console: console,
      clearTimeout: () => {},
      setTimeout: () => {},
      clearInterval: () => {},
      setInterval: () => {},
    };
    sandbox.globalThis = sandbox;
    sandbox.self = sandbox;

    // Read admin.js and execute in sandbox
    const adminSrc = fs.readFileSync(process.argv[1], 'utf-8');
    vm.createContext(sandbox);
    vm.runInContext(adminSrc, sandbox);

    const {
      formatInr,
      formatInrRupees,
      bugRow,
      renderBugDetail,
      renderMonitor,
      renderAuditDetail,
      setMessage,
      renderDetail,
      clearDetail,
      clearBugDetail,
      endAdminSession,
    } = sandbox.window.KarmiAdmin;

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

    // Behavioural XSS check driving actual render paths
    const xssTicket = '<img src=x onerror=alert(1)>';
    const xssDescPreview = '<svg onload=alert(2)>';
    const xssUser = '<img src=x onerror=alert(3)>';
    const xssDesc = '<svg onload=alert(4)>';
    const xssAdminNotes = '<img src=x onerror=alert(5)>';
    const xssModel = '<svg onload=alert(6)>';
    const xssProvider = '<img src=x onerror=alert(7)>';
    const xssAuditKey = '<img src=x onerror=alert(8)>';
    const xssAuditVal = '<svg onload=alert(9)>';
    const xssMsg = '<img src=x onerror=alert(10)>';

    // 1. Bug inbox list row
    const row = bugRow({
      id: 'br_xss_1',
      ticket: xssTicket,
      category: 'ui',
      status: 'new',
      description_preview: xssDescPreview,
      user_display_name: xssUser,
      created_at: '2026-11-07T12:00:00Z',
    });
    assert.strictEqual(row.tagName, 'TR');
    assert(row.textContent.includes(xssTicket), 'row must contain ticket as text');
    assert(row.textContent.includes(xssDescPreview), 'row must contain description_preview as text');
    assert(row.textContent.includes(xssUser), 'row must contain user_display_name as text');

    // 2. Bug detail
    renderBugDetail({
      id: 'br_xss_2',
      ticket: xssTicket,
      category: 'ui',
      status: 'new',
      user: { id: 'usr_1', display_name: xssUser, plan: 'parth' },
      description: xssDesc,
      admin_notes: xssAdminNotes,
      created_at: '2026-11-07T12:00:00Z',
      updated_at: '2026-11-07T12:00:00Z',
      has_screenshot: false,
    });
    const detailDesc = getOrCreate('bug-detail-description');
    assert.strictEqual(detailDesc.textContent, xssDesc);
    const detailNotes = getOrCreate('edit-bug-notes');
    assert.strictEqual(detailNotes.value, xssAdminNotes);
    const detailMeta = getOrCreate('bug-detail-meta');
    assert(detailMeta.textContent.includes(xssTicket));
    assert(detailMeta.textContent.includes(xssUser));

    // 3. Overview model_health table
    renderMonitor({
      generated_at: '2026-11-07T12:00:00Z',
      requests_today: 100,
      daily_request_cap: 1000,
      model_health: [
        {
          model: xssModel,
          provider: xssProvider,
          last_success_at: '2026-11-07T11:59:00Z',
          error_rate: 0.01,
          p50_latency_ms: 150,
          runs: 42,
        }
      ],
    });
    const modelHealthBody = getOrCreate('model-health-body');
    assert(modelHealthBody.textContent.includes(xssModel));
    assert(modelHealthBody.textContent.includes(xssProvider));

    // 4. Audit detail rows
    const auditDiv = renderAuditDetail({ [xssAuditKey]: xssAuditVal });
    assert.strictEqual(auditDiv.tagName, 'DIV');
    assert(auditDiv.textContent.includes(xssAuditKey));
    assert(auditDiv.textContent.includes(xssAuditVal));

    // 5. Error/notice message display
    setMessage('test-notice', xssMsg, 'error');
    const msgNode = getOrCreate('test-notice');
    assert.strictEqual(msgNode.textContent, xssMsg);

    // Safety assertions
    assert.strictEqual(recordedInnerHTML.length, 0, 'No innerHTML assignments must occur');

    // Check that no element was created from markup
    for (const el of createdElements) {
      assert(!el.tagName.includes('<'), 'Element tag must not contain markup: ' + el.tagName);
      assert(el.tagName !== 'IMG', 'No IMG element should be created from strings');
      assert(el.tagName !== 'SVG', 'No SVG element should be created from strings');
      assert(el.tagName !== 'SCRIPT', 'No SCRIPT element should be created');
    }

    // All malicious strings must be present in recorded text/value
    const allMalicious = [
      xssTicket, xssDescPreview, xssUser, xssDesc, xssAdminNotes,
      xssModel, xssProvider, xssAuditKey, xssAuditVal, xssMsg
    ];
    for (const str of allMalicious) {
      const foundInText = recordedTextNodes.some(t => t.includes(str));
      const foundInValues = [detailNotes.value].some(v => v.includes(str));
      assert(foundInText || foundInValues, 'String must be passed as text/value: ' + str);
    }

    // 6. DOM clearing on clearDetail, clearBugDetail, and endAdminSession (P2-2)
    renderDetail({
      id: 'usr_123',
      email: 'customer@example.com',
      display_name: 'Customer Name',
      tier: 'trika',
      tester: true,
      tester_label: 'beta-team',
      admin_notes: 'confidential customer notes',
      usage: { requests_today: 42 },
    });
    assert(getOrCreate('detail-profile').children.length > 0, 'profile dl should be populated');
    assert.strictEqual(getOrCreate('edit-display-name').value, 'Customer Name');
    assert.strictEqual(getOrCreate('edit-tester-label').value, 'beta-team');
    assert.strictEqual(getOrCreate('edit-admin-notes').value, 'confidential customer notes');

    clearDetail();
    assert.strictEqual(getOrCreate('detail-profile').children.length, 0, 'detail-profile dl must be cleared');
    assert.strictEqual(getOrCreate('detail-usage').children.length, 0, 'detail-usage dl must be cleared');
    assert.strictEqual(getOrCreate('detail-plan').textContent, '', 'detail-plan text must be cleared');
    assert.strictEqual(getOrCreate('edit-display-name').value, '', 'edit-display-name must be empty');
    assert.strictEqual(getOrCreate('edit-tester-label').value, '', 'edit-tester-label must be empty');
    assert.strictEqual(getOrCreate('edit-admin-notes').value, '', 'edit-admin-notes must be empty');

    renderBugDetail({
      id: 'bug_456',
      ticket: 'BUG-456',
      status: 'triaged',
      admin_notes: 'internal bug note',
      description: 'bug desc',
    });
    getOrCreate('edit-bug-reason').value = 'fixing bug';
    assert.strictEqual(getOrCreate('edit-bug-notes').value, 'internal bug note');
    assert.strictEqual(getOrCreate('edit-bug-reason').value, 'fixing bug');

    clearBugDetail();
    assert.strictEqual(getOrCreate('edit-bug-notes').value, '', 'edit-bug-notes must be cleared');
    assert.strictEqual(getOrCreate('edit-bug-reason').value, '', 'edit-bug-reason must be cleared');
    assert.strictEqual(getOrCreate('bug-detail-meta').children.length, 0, 'bug-detail-meta must be cleared');

    // Populate both and verify endAdminSession clears all
    renderDetail({
      id: 'usr_789',
      display_name: 'Sensitive User',
      tester_label: 'vip',
      admin_notes: 'secret note',
    });
    renderBugDetail({
      id: 'bug_789',
      admin_notes: 'secret bug note',
    });
    getOrCreate('edit-bug-reason').value = 'secret reason';
    endAdminSession();
    assert.strictEqual(getOrCreate('detail-profile').children.length, 0);
    assert.strictEqual(getOrCreate('detail-usage').children.length, 0);
    assert.strictEqual(getOrCreate('edit-display-name').value, '');
    assert.strictEqual(getOrCreate('edit-tester-label').value, '');
    assert.strictEqual(getOrCreate('edit-admin-notes').value, '');
    assert.strictEqual(getOrCreate('edit-bug-notes').value, '');
    assert.strictEqual(getOrCreate('edit-bug-reason').value, '');
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
