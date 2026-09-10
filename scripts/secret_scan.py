from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
)
EXCLUDED = {".git", ".venv", "data", "artifacts", "reports"}


def main() -> None:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".toml", ".yaml", ".yml", ".json", ".md", ".env"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in PATTERNS):
            findings.append(str(path.relative_to(ROOT)))
    if findings:
        raise SystemExit("possible secrets found in: " + ", ".join(sorted(findings)))
    print("secret scan: no matching credential material")


if __name__ == "__main__":
    main()

