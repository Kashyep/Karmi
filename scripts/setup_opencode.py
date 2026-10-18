"""Store an OpenCode Zen API key in an owner-only local file without echoing it."""
from __future__ import annotations

import getpass
import os
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_private_env(path: Path, api_key: str) -> None:
    if not api_key or any(character in api_key for character in "\r\n") or "${" in api_key:
        raise ValueError("Invalid API key format")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        escaped = api_key.replace("\\", "\\\\").replace("'", "\\'")
        stream.write("# Private OpenCode Zen API key. Never commit this file.\n")
        stream.write(f"DAILY_AGENT_OPENCODE_API_KEY='{escaped}'\n")


def main() -> int:
    path = ROOT / ".env.opencode"
    if path.exists() or path.is_symlink():
        print("Existing .env.opencode preserved. No changes made.")
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            api_key = getpass.getpass("Paste OpenCode Zen API key (hidden): ").strip()
        write_private_env(path, api_key)
    except (ValueError, OSError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("Setup stopped. Check terminal permissions; no key values displayed.")
        return 1
    print("Saved private .env.opencode with owner-only permissions.")
    print("No provider request was made. This checkout does not use the key until its AI adapter is enabled.")
    print("Do not paste the key into chat or commit this file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
