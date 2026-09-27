"""Cryptographic pseudonym derivation and request fingerprinting (ADR-0003).

Pseudonyms are deterministic keyed HMACs using a domain-separated key derived from the
application auth secret. No separate production secret is required.
"""

from __future__ import annotations

import hashlib
import hmac


def telemetry_key(auth_secret: str) -> bytes:
    """Derive the 32-byte telemetry pseudonym key from the application auth secret."""
    return hmac.new(
        auth_secret.encode(),
        b"karmi-telemetry-pseudonym-v1",
        hashlib.sha256,
    ).digest()


def actor_id(key: bytes, account_id: str, user_id: str) -> str:
    """Compute a stable 64-char hex pseudonym for an account/user identity."""
    msg = f"actor:{account_id}:{user_id}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def request_fingerprint(key: bytes, text: str) -> str:
    """Compute a 64-char hex HMAC of casefolded, whitespace-collapsed request text.

    Used strictly for in-Karmi retry attribution. Never exported.
    """
    normalized = " ".join(text.casefold().split())
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()


def value_hash(key: bytes, text: str) -> str:
    """Compute a 64-char hex HMAC for an arbitrary string value."""
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()
