"""Beta access codes: a secret code unlocks a higher plan tier for the account that enters it.

Only SHA-256 hashes of the codes are stored (``data/access_codes.json`` or
``DAILY_AGENT_ACCESS_CODES_PATH``). The codes themselves carry ~60 bits of randomness, so the
hashes are not practically reversible. Codes never downgrade a plan.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path

from daily_agent.plans import SYNTHETIC_POLICIES

PLAN_RANK = {"ananta": 0, "yanta": 1, "trika": 2, "parth": 3}


class AccessCodeConfigError(ValueError):
    """The access-code file is malformed."""


def normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _digest(code: str) -> str:
    return hashlib.sha256(normalize(code).encode("utf-8")).hexdigest()


def load_access_code_hashes(path: Path | None = None) -> dict[str, str]:
    try:
        text = (
            path.read_text(encoding="utf-8")
            if path is not None
            else resources.files("daily_agent").joinpath("data/access_codes.json").read_text(encoding="utf-8")
        )
        document = json.loads(text)
    except (OSError, ValueError) as exc:
        raise AccessCodeConfigError(f"access codes cannot be read: {exc}") from exc
    hashes = document.get("hashes") if isinstance(document, dict) else None
    if not isinstance(hashes, dict):
        raise AccessCodeConfigError("access codes file needs a 'hashes' object")
    for digest, plan in hashes.items():
        if plan not in SYNTHETIC_POLICIES or plan == "ananta" or len(digest) != 64:
            raise AccessCodeConfigError("access codes must map sha256 digests to paid plan ids")
    return dict(hashes)


def plan_for_code(code: str, hashes: dict[str, str]) -> str | None:
    return hashes.get(_digest(code))
