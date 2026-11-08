"""Release helpers: AltStore/SideStore source.json and CHANGELOG release notes.

Subcommands:
  notes   extract the CHANGELOG.md section for one version (fails if missing/empty)
  source  write the AltStore-format source.json for one released IPA

Source format: https://faq.altstore.io/developers/make-a-source (apps[].versions[];
SideStore reads the same format: https://docs.sidestore.io/docs/advanced/app-sources).
Deliberately omitted: `marketplaceID` and legacy top-level app fields (SideStore treats a
marketplaceID as a notarized source and refuses to add it).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO = "Ruud-en-Blauw/Karmi"
BUNDLE_ID = "ai.karmi.app"
APP_NAME = "Karmi"
DEVELOPER_NAME = "Ruud-en-Blauw"
MIN_OS_VERSION = "15.0"
ICON_PATH = "mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png"
DISCLAIMER = "Experimental, untested on device."

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z][0-9A-Za-z.]*)?$")
_BUILD_RE = re.compile(r"^\d+$")


def extract_notes(changelog: str, version: str) -> str:
    """Return the body of the `## [version]` section of a Keep-a-Changelog file."""
    lines = changelog.splitlines()
    heading = re.compile(r"^## \[" + re.escape(version) + r"\](\s|$)")
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ValueError(f"CHANGELOG has no '## [{version}]' section")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    body = "\n".join(lines[start + 1 : end]).strip()
    if not body:
        raise ValueError(f"CHANGELOG section '## [{version}]' is empty")
    return body


def build_source(
    *,
    version: str,
    build: str,
    tag: str,
    ipa_size: int,
    date: str,
    notes: str,
    repo: str = REPO,
) -> dict[str, Any]:
    """Build the source document for a single released IPA."""
    if not _VERSION_RE.match(version):
        raise ValueError(f"version {version!r} is not X.Y.Z[-prerelease]")
    if not _BUILD_RE.match(build):
        raise ValueError(f"build {build!r} is not a number")
    if ipa_size <= 0:
        raise ValueError("IPA size must be positive")
    if not notes.strip():
        raise ValueError("release notes are empty")
    icon_url = f"https://raw.githubusercontent.com/{repo}/{tag}/{ICON_PATH}"
    download_url = f"https://github.com/{repo}/releases/download/{tag}/karmi-{version}.ipa"
    return {
        "name": APP_NAME,
        "subtitle": f"{APP_NAME} for iPhone and iPad. {DISCLAIMER}",
        "description": (
            f"Unsigned {APP_NAME} builds for sideloading with SideStore or AltStore. "
            f"The iOS build is experimental and has not been tested on a device."
        ),
        "iconURL": icon_url,
        "website": f"https://github.com/{repo}",
        "nsfw": False,
        "featuredApps": [BUNDLE_ID],
        "apps": [
            {
                "name": APP_NAME,
                "bundleIdentifier": BUNDLE_ID,
                "developerName": DEVELOPER_NAME,
                "subtitle": DISCLAIMER,
                "localizedDescription": (
                    f"{APP_NAME}: a calm, accessible assistant for daily tasks. "
                    f"The iOS build is experimental and has not been tested on a device."
                ),
                "iconURL": icon_url,
                "versions": [
                    {
                        "version": version,
                        "buildVersion": build,
                        "date": date,
                        "localizedDescription": notes,
                        "downloadURL": download_url,
                        "size": ipa_size,
                        "minOSVersion": MIN_OS_VERSION,
                    }
                ],
                "appPermissions": {"entitlements": [], "privacy": {}},
            }
        ],
        "news": [],
    }


def _cmd_notes(args: argparse.Namespace) -> None:
    notes = extract_notes(Path(args.changelog).read_text(encoding="utf-8"), args.version)
    Path(args.output).write_text(notes + "\n", encoding="utf-8")


def _cmd_source(args: argparse.Namespace) -> None:
    ipa = Path(args.ipa)
    source = build_source(
        version=args.version,
        build=args.build,
        tag=args.tag,
        ipa_size=ipa.stat().st_size,
        date=args.date,
        notes=Path(args.notes).read_text(encoding="utf-8").strip(),
        repo=args.repo,
    )
    Path(args.output).write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = parser.add_subparsers(dest="command", required=True)

    notes = sub.add_parser("notes", help="extract the CHANGELOG section for a version")
    notes.add_argument("--changelog", required=True)
    notes.add_argument("--version", required=True)
    notes.add_argument("--output", required=True)
    notes.set_defaults(func=_cmd_notes)

    source = sub.add_parser("source", help="write source.json")
    source.add_argument("--version", required=True, help="pubspec version without +build")
    source.add_argument("--build", required=True, help="pubspec build number (after +)")
    source.add_argument("--tag", required=True, help="git tag, e.g. v0.1.0")
    source.add_argument("--ipa", required=True, help="path to the built .ipa (for its size)")
    source.add_argument("--notes", required=True, help="file with the release notes")
    source.add_argument("--date", required=True, help="ISO 8601 release date")
    source.add_argument("--output", required=True)
    source.add_argument("--repo", default=REPO)
    source.set_defaults(func=_cmd_source)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
