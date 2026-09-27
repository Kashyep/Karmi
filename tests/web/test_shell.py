from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from daily_agent.api import create_app
from daily_agent.web.manifest import DEFAULT_TIER, TIER_PALETTES, build_manifest
from daily_agent.web.shell import (
    _STYLES,
    PLAN_LABELS,
    TaskState,
    WebTask,
    render_shell,
)

# The third tier is "Trika" (single k); this matches the double-k misspelling.
MISSPELT_TIER = re.compile(r"trik{2}a", re.IGNORECASE)


def test_shell_has_accessible_navigation_and_pwa_metadata() -> None:
    html = render_shell()
    assert '<main id="main-content" tabindex="-1">' in html
    assert "Skip to main content" in html
    assert 'aria-label="Primary navigation"' in html
    assert 'rel="manifest"' in html
    assert 'href="#armory"' in html
    assert "provider" not in html.lower()
    assert "model picker" not in html.lower()


def test_shell_root_has_data_attributes_and_tokens_stylesheet() -> None:
    html = render_shell()
    assert '<html lang="en" data-tier="ananta" data-theme="light">' in html
    assert '<link rel="stylesheet" href="/static/karmi-tokens.css">' in html


def test_shell_has_no_hex_literals_in_styles() -> None:
    matches = re.findall(r"#[0-9a-fA-F]{3,8}\b", _STYLES)
    assert not matches, f"Hex literals found in _STYLES: {matches}"


def test_shell_shows_all_four_plan_labels_without_fake_balances() -> None:
    html = render_shell()
    assert PLAN_LABELS == ("Ananta", "Yanta", "Trika", "Parth")
    assert "Parth" in PLAN_LABELS
    assert not MISSPELT_TIER.search(html)
    for label in PLAN_LABELS:
        assert f"<h3>{label}</h3>" in html
    assert "No balance shown without server data." in html


def test_armory_markup_structure_and_hooks() -> None:
    html = render_shell()
    assert '<section id="armory"' in html
    assert 'aria-labelledby="armory-heading"' in html
    # 4 cards
    assert 'class="armory-card tier-ananta"' in html
    assert 'class="armory-card tier-yanta is-locked"' in html
    assert 'class="armory-card tier-trika is-locked"' in html
    assert 'class="armory-card tier-parth is-locked"' in html
    # Locked styling hooks
    assert "is-locked" in html
    assert "padlock-badge" in html
    assert "armory-card-visual" in html
    # Preview controls
    assert "Preview 10 s" in html
    assert "End preview" in html
    assert 'id="armory-preview-banner"' in html
    assert "glass-panel" in html
    # Live region
    assert 'id="armory-countdown"' in html
    assert 'aria-live="polite"' in html
    # PWA icon explainer
    assert "Installed PWAs retain their home screen icon until reinstalled" in html


def test_theme_mode_control_in_settings() -> None:
    html = render_shell()
    assert '<fieldset class="theme-mode-fieldset">' in html
    assert 'name="theme-mode"' in html
    assert 'value="system"' in html
    assert 'value="light"' in html
    assert 'value="dark"' in html


def test_glass_panel_utility_and_fallbacks() -> None:
    assert ".glass-panel" in _STYLES
    assert "backdrop-filter:blur(16px)" in _STYLES
    assert "--color-glass-base" in _STYLES
    assert "--color-glass-border" in _STYLES
    assert "--color-glass-highlight" in _STYLES
    assert "--color-glass-fallback" in _STYLES
    # @supports fallback
    assert "@supports not (backdrop-filter:blur(16px))" in _STYLES
    # prefers-reduced-transparency fallback
    assert "@media (prefers-reduced-transparency:reduce)" in _STYLES
    # forced-colors fallback
    assert "@media (forced-colors:active)" in _STYLES


def test_manifest_per_tier_and_disk_icons() -> None:
    static_root = Path(__file__).resolve().parents[2] / "src" / "daily_agent" / "web" / "static"
    for tier in ("ananta", "yanta", "trika", "parth"):
        manifest = build_manifest(tier)
        assert manifest["name"] == "Karmi"
        assert manifest["short_name"] == "Karmi"
        assert manifest["theme_color"] == TIER_PALETTES[tier]["theme_color"]
        assert manifest["background_color"] == TIER_PALETTES[tier]["background_color"]
        assert len(manifest["icons"]) == 3
        for icon in manifest["icons"]:
            src = icon["src"]
            assert src.startswith("/static/")
            rel_path = src.removeprefix("/static/")
            file_on_disk = static_root / rel_path
            assert file_on_disk.is_file(), f"Missing icon on disk: {file_on_disk}"


def test_manifest_fallback_on_unknown_tier() -> None:
    default_manifest = build_manifest(DEFAULT_TIER)
    assert build_manifest(None) == default_manifest
    assert build_manifest("") == default_manifest
    assert build_manifest("unknown") == default_manifest
    assert build_manifest("tri" + "kka") == default_manifest  # misspelt key falls back


def test_task_states_are_truthful_and_escaped() -> None:
    html = render_shell(tasks=(WebTask(TaskState.COMPLETED, "<unsafe>", "Done & checked"),))
    assert "Task status: Completed" in html
    assert "&lt;unsafe&gt;" in html
    assert "Done &amp; checked" in html
    for state in TaskState:
        assert f"state-{state.value}" in render_shell(tasks=(WebTask(state),))


def test_web_routes_and_static_assets() -> None:
    client = TestClient(create_app())
    # GET / returns new markup
    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "data-tier=" in root_res.text
    assert "/static/karmi-tokens.css" in root_res.text
    assert not MISSPELT_TIER.search(root_res.text)

    # GET /static/karmi-tokens.css
    css_res = client.get("/static/karmi-tokens.css")
    assert css_res.status_code == 200
    assert "text/css" in css_res.headers["content-type"]
    assert "--color-glass-base" in css_res.text

    # GET /manifest.webmanifest?tier=trika returns trika colours
    trika_res = client.get("/manifest.webmanifest?tier=trika")
    assert trika_res.status_code == 200
    assert "application/manifest+json" in trika_res.headers["content-type"]
    trika_manifest = trika_res.json()
    assert trika_manifest["theme_color"] == "#FF5722"
    assert trika_manifest["background_color"] == "#FCF8F5"

    # GET /manifest.webmanifest?tier=parth returns parth colours
    parth_res = client.get("/manifest.webmanifest?tier=parth")
    assert parth_res.status_code == 200
    parth_manifest = parth_res.json()
    assert parth_manifest["theme_color"] == "#D4AF37"
    assert parth_manifest["background_color"] == "#FFFFFF"

    # Static path traversal / 404 checks
    assert client.get("/static/nonexistent-file.css").status_code == 404
    assert client.get("/static/../api.py").status_code == 404
