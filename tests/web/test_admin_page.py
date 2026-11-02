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
FORBIDDEN_JS = ("innerHTML", "localStorage", "sessionStorage", "document.cookie")


def _publishable_key(domain: str = "clerk.example.test") -> str:
    encoded = base64.b64encode(f"{domain}$".encode()).decode().rstrip("=")
    return f"pk_test_{encoded}"


@pytest.fixture
def client_factory():
    app = create_app()
    clients: list[TestClient] = []

    def make(publishable_key: str | None) -> TestClient:
        settings = Settings(environment="test", clerk_publishable_key=publishable_key)
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
