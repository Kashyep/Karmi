"""High-risk text sanitization, PII detection, redaction and export validation (ADR-0003).

Detects sensitive classes (emails, phone numbers, API keys, tokens, credentials, payment cards,
government IDs, street addresses, and high-entropy secrets) to guarantee that no user PII
or raw secrets enter telemetry persistence or export batches.
"""

from __future__ import annotations

import math
import re
from typing import Final

HIGH_RISK_CLASSES: Final[frozenset[str]] = frozenset(
    {
        "email",
        "phone",
        "api_key",
        "bearer_token",
        "jwt",
        "private_key",
        "card_number",
        "secret_assignment",
        "aadhaar",
        "pan",
        "street_address",
        "high_entropy_token",
    }
)

_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{15,}\b")
_API_KEY_RE = re.compile(
    r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{20,}\b|"
    r"\bsk-[A-Za-z0-9_-]{20,}\b|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b|"
    r"\bgithub_pat_[A-Za-z0-9_]{30,}\b|"
    r"\bxox[abpr]-[0-9A-Za-z-]{10,}\b|"
    r"\bAIza[0-9A-Za-z-_]{35}\b"
)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)\b(?:password|passwd|secret|api_key|apikey|access_token|auth_token|client_secret)"
    r"\s*[:=]\s*['\"]?[^\s'\",;&]{4,}"
)
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR_RE = re.compile(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:(?:\+91|91)[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b|"
    r"(?:(?:\+91|91)[\s-]?)?[6-9]\d{2}[\s-]?\d{3}[\s-]?\d{4}\b|"
    r"\+(?:[1-9]\d{0,2})[\s-]?(?:\(?\d{1,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}\b|"
    r"(?:\+1[\s-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"
)
_STREET_RE = re.compile(
    r"(?i)\b\d{1,5}[A-Za-z]?(?:[/-]\d{1,5}[A-Za-z]?)?,?\s+"
    r"(?:[A-Za-z0-9.'-]+\s+){1,4}"
    r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|Ln\.?|Marg|Nagar|Drive|Dr\.?|Boulevard|Blvd\.?|Way|Court|Ct\.?)\b"
)
_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_TOKEN_CANDIDATE_RE = re.compile(r"\b[A-Za-z0-9+/_=-]{32,}\b")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_SKIP_KEYS: Final[frozenset[str]] = frozenset({"batch_id", "payload_sha256", "anonymous_actor_id"})
_SKIP_SUFFIXES: Final[tuple[str, ...]] = ("_id", "_hash", "_at", "_version")


class SanitizationError(ValueError):
    """Raised when an unredacted high-risk class is found during export validation."""

    def __init__(self, classes: frozenset[str], path: str) -> None:
        self.classes = classes
        self.path = path
        super().__init__(f"Sanitization violation at {path}: {', '.join(sorted(classes))}")


def luhn_check(digits: str) -> bool:
    """Validate digits against the Luhn mod-10 formula."""
    s = 0
    reverse_digits = digits[::-1]
    for i, c in enumerate(reverse_digits):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return s % 10 == 0


def shannon_entropy(s: str) -> float:
    """Compute Shannon entropy in bits per character."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = float(len(s))
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def _find_all_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []

    for match in _PRIVATE_KEY_RE.finditer(text):
        spans.append((match.start(), match.end(), "private_key"))
    for match in _JWT_RE.finditer(text):
        spans.append((match.start(), match.end(), "jwt"))
    for match in _BEARER_RE.finditer(text):
        spans.append((match.start(), match.end(), "bearer_token"))
    for match in _API_KEY_RE.finditer(text):
        spans.append((match.start(), match.end(), "api_key"))
    for match in _SECRET_ASSIGN_RE.finditer(text):
        spans.append((match.start(), match.end(), "secret_assignment"))
    for match in _PAN_RE.finditer(text):
        spans.append((match.start(), match.end(), "pan"))
    for match in _AADHAAR_RE.finditer(text):
        spans.append((match.start(), match.end(), "aadhaar"))
    for match in _EMAIL_RE.finditer(text):
        spans.append((match.start(), match.end(), "email"))
    for match in _PHONE_RE.finditer(text):
        spans.append((match.start(), match.end(), "phone"))
    for match in _STREET_RE.finditer(text):
        spans.append((match.start(), match.end(), "street_address"))

    for match in _CARD_CANDIDATE_RE.finditer(text):
        candidate = match.group(0)
        digits = re.sub(r"[ -]", "", candidate)
        if 13 <= len(digits) <= 19 and digits[0] in "23456" and luhn_check(digits):
            spans.append((match.start(), match.end(), "card_number"))

    for match in _TOKEN_CANDIDATE_RE.finditer(text):
        candidate = match.group(0)
        if _UUID_RE.match(candidate):
            continue
        if all(c in "0123456789abcdef" for c in candidate) or all(
            c in "0123456789ABCDEF" for c in candidate
        ):
            continue
        has_upper = any(c.isupper() for c in candidate)
        has_lower = any(c.islower() for c in candidate)
        has_digit = any(c.isdigit() for c in candidate)
        has_sym = any(c in "+/_=-" for c in candidate)
        classes_count = sum([has_upper, has_lower, has_digit, has_sym])
        if classes_count >= 3 and shannon_entropy(candidate) >= 3.0:
            spans.append((match.start(), match.end(), "high_entropy_token"))

    # Sort spans by start asc, length desc
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Discard overlapping spans
    filtered: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, cls in spans:
        if start >= last_end:
            filtered.append((start, end, cls))
            last_end = end
    return filtered


def scan(text: str) -> frozenset[str]:
    """Scan text for any sensitive high-risk classes."""
    return frozenset(cls for _, _, cls in _find_all_spans(text))


def redact(text: str) -> tuple[str, frozenset[str]]:
    """Redact sensitive high-risk matches with [REDACTED:<class>]."""
    spans = _find_all_spans(text)
    if not spans:
        return text, frozenset()
    classes: set[str] = set()
    parts: list[str] = []
    idx = 0
    for start, end, cls in spans:
        parts.append(text[idx:start])
        parts.append(f"[REDACTED:{cls}]")
        classes.add(cls)
        idx = end
    parts.append(text[idx:])
    return "".join(parts), frozenset(classes)


def sanitize_free_text(text: str, *, max_length: int = 2000) -> str | None:
    """Redact text, re-scan to guarantee no residual secrets, and truncate.

    Returns None if any high-risk class persists after redaction (fail-closed).
    """
    redacted, _ = redact(text)
    if scan(redacted):
        return None
    return redacted[:max_length]


def validate_export(payload: object) -> None:
    """Walk parsed JSON structure and scan free-text strings for high-risk data.

    Skips keys that represent identifiers, hashes, timestamps, versions, feature names,
    and model route IDs. Raises SanitizationError on any violation.
    """

    def _walk(obj: object, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key_str = str(k)
                child_path = f"{path}.{key_str}" if path else key_str
                if key_str in _SKIP_KEYS or key_str.endswith(_SKIP_SUFFIXES):
                    continue
                _walk(v, child_path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                child_path = f"{path}[{idx}]"
                _walk(item, child_path)
        elif isinstance(obj, str):
            findings = scan(obj)
            if findings:
                raise SanitizationError(findings, path)

    _walk(payload, "")
