"""Search helpers for conversation and message content."""

from __future__ import annotations


def escape_like(term: str) -> str:
    """Escape backslash, %, and _ for SQL LIKE / ILIKE with backslash escape."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def make_snippet(text: str, term: str, radius: int = 40) -> str:
    """Return a window of text around the first case-insensitive match with ellipsis at truncated ends.

    If term is not found or empty, return the text's first 80 chars.
    """
    if not term:
        return text[:80]
    idx = text.lower().find(term.lower())
    if idx == -1:
        return text[:80]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(term) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"
