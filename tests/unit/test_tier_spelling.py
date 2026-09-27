"""The third Karmi tier is "Trika" (single k). Guard against the double-k misspelling anywhere
in source, config, tests and docs."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MISSPELT = re.compile(r"trik{2}a", re.IGNORECASE)
TEXT_SUFFIXES = {".py", ".dart", ".md", ".json", ".yaml", ".yml", ".toml", ".css", ".html",
                 ".kt", ".kts", ".swift", ".xml", ".plist", ".webmanifest", ".txt", ".cfg"}
SKIP_DIRS = {".git", ".dart_tool", "build", ".venv", "node_modules", "__pycache__", "data",
             ".mypy_cache", ".ruff_cache", ".pytest_cache", ".claude", ".codex", "Pods"}


def test_no_misspelt_tier_name_in_repository_text() -> None:
    offenders = []
    for path in ROOT.rglob("*"):
        if (
            path.suffix.lower() not in TEXT_SUFFIXES
            or not path.is_file()
            or SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders += [
            f"{path.relative_to(ROOT)}:{n}"
            for n, line in enumerate(text.splitlines(), 1)
            if MISSPELT.search(line)
        ]
    assert offenders == []
