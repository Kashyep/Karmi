"""source.json / release-notes generation (scripts/release/make_altstore_source.py)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.release.make_altstore_source import extract_notes, main

CHANGELOG = """# Changelog

## [Unreleased]

### Changed
- not released yet

## [0.1.0] - 2026-01-02 (build 5)

### Added
- First thing

### Fixed
- Second thing

## [0.0.9] - 2025-12-01

- older
"""

REPO = "Ruud-en-Blauw/Karmi"


def _run_source(tmp_path: Path, *, version: str = "0.1.0", build: str = "5") -> dict[str, Any]:
    ipa = tmp_path / f"karmi-{version}.ipa"
    ipa.write_bytes(b"\0" * 1234)
    notes = tmp_path / "notes.md"
    notes.write_text("### Added\n- First thing\n", encoding="utf-8")
    out = tmp_path / "source.json"
    code = main(
        [
            "source",
            "--version", version,
            "--build", build,
            "--tag", f"v{version}",
            "--ipa", str(ipa),
            "--notes", str(notes),
            "--date", "2026-01-02T00:00:00+00:00",
            "--output", str(out),
        ]
    )  # fmt: skip
    assert code == 0
    loaded: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return loaded


def test_extract_notes_returns_only_requested_section() -> None:
    notes = extract_notes(CHANGELOG, "0.1.0")
    assert notes.startswith("### Added")
    assert "Second thing" in notes
    assert "older" not in notes
    assert "not released yet" not in notes


def test_extract_notes_missing_version_fails() -> None:
    with pytest.raises(ValueError, match=r"no '## \[0.2.0\]' section"):
        extract_notes(CHANGELOG, "0.2.0")


def test_extract_notes_empty_section_fails() -> None:
    with pytest.raises(ValueError, match="empty"):
        extract_notes("## [1.0.0] - x\n\n## [0.9.0]\n- a\n", "1.0.0")


def test_notes_cli_reports_missing_version(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    argv = ["notes", "--changelog", str(changelog), "--version", "9.9.9"]
    assert main([*argv, "--output", str(tmp_path / "n.md")]) == 1


def test_source_has_documented_required_fields(tmp_path: Path) -> None:
    # Required keys per https://faq.altstore.io/developers/make-a-source
    source = _run_source(tmp_path)
    assert source["name"] == "Karmi"
    assert isinstance(source["apps"], list) and isinstance(source["news"], list)
    assert source["nsfw"] is False
    (app,) = source["apps"]
    for key in ("name", "bundleIdentifier", "developerName", "localizedDescription", "iconURL"):
        assert isinstance(app[key], str) and app[key]
    assert app["bundleIdentifier"] == "ai.karmi.app"
    assert app["developerName"] == "Ruud-en-Blauw"
    assert app["appPermissions"] == {"entitlements": [], "privacy": {}}
    # SideStore refuses sources that carry a marketplaceID (treated as notarized).
    assert "marketplaceID" not in app
    (version,) = app["versions"]
    for key in ("version", "buildVersion", "date", "downloadURL"):
        assert isinstance(version[key], str) and version[key]
    assert version["version"] == "0.1.0"
    assert version["buildVersion"] == "5"
    assert version["size"] == 1234
    assert version["minOSVersion"] == "15.0"
    assert version["downloadURL"] == (
        f"https://github.com/{REPO}/releases/download/v0.1.0/karmi-0.1.0.ipa"
    )
    assert app["iconURL"] == (
        f"https://raw.githubusercontent.com/{REPO}/v0.1.0/"
        "mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png"
    )


def test_source_prerelease_version_is_accepted(tmp_path: Path) -> None:
    source = _run_source(tmp_path, version="0.2.0-beta.1", build="7")
    (version,) = source["apps"][0]["versions"]
    assert version["version"] == "0.2.0-beta.1"
    assert version["downloadURL"].endswith("/v0.2.0-beta.1/karmi-0.2.0-beta.1.ipa")


@pytest.mark.parametrize(("version", "build"), [("v0.1.0", "5"), ("0.1", "5"), ("0.1.0", "x")])
def test_source_rejects_malformed_version_or_build(
    tmp_path: Path, version: str, build: str
) -> None:
    ipa = tmp_path / "a.ipa"
    ipa.write_bytes(b"x")
    notes = tmp_path / "n.md"
    notes.write_text("n", encoding="utf-8")
    argv = [
        "source", "--version", version, "--build", build, "--tag", "t", "--ipa", str(ipa),
        "--notes", str(notes), "--date", "2026-01-02", "--output", str(tmp_path / "s.json"),
    ]  # fmt: skip
    assert main(argv) == 1
