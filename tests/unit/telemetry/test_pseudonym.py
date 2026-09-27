"""Unit tests for cryptographic pseudonym derivation (ADR-0003)."""

from __future__ import annotations

import re

from daily_agent.telemetry.pseudonym import (
    actor_id,
    request_fingerprint,
    telemetry_key,
    value_hash,
)

_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


def test_telemetry_key_derivation() -> None:
    secret1 = "super-secret-auth-key-1"
    secret2 = "super-secret-auth-key-2"
    key1 = telemetry_key(secret1)
    key2 = telemetry_key(secret2)

    assert isinstance(key1, bytes)
    assert len(key1) == 32
    assert key1 == telemetry_key(secret1)
    assert key1 != key2


def test_actor_id_format_and_properties() -> None:
    key = telemetry_key("auth-secret-test")
    aid1 = actor_id(key, "acc_1", "usr_1")
    aid2 = actor_id(key, "acc_1", "usr_1")
    aid3 = actor_id(key, "acc_1", "usr_2")

    assert _HEX_64_RE.match(aid1) is not None
    assert aid1 == aid2
    assert aid1 != aid3


def test_request_fingerprint_casefold_and_whitespace_collapse() -> None:
    key = telemetry_key("auth-secret-test")
    raw1 = "  Please Remind   Me To  Buy Milk!  \n"
    raw2 = "please remind me to buy milk!"
    raw3 = "Please remind me to buy coffee!"

    fp1 = request_fingerprint(key, raw1)
    fp2 = request_fingerprint(key, raw2)
    fp3 = request_fingerprint(key, raw3)

    assert _HEX_64_RE.match(fp1) is not None
    assert fp1 == fp2
    assert fp1 != fp3


def test_value_hash_properties() -> None:
    key = telemetry_key("auth-secret-test")
    h1 = value_hash(key, "correction text")
    h2 = value_hash(key, "correction text")
    h3 = value_hash(key, "other text")

    assert _HEX_64_RE.match(h1) is not None
    assert h1 == h2
    assert h1 != h3
