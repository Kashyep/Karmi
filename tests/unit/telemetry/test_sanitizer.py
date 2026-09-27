"""Unit tests for the privacy sanitizer and export validation (ADR-0003)."""

from __future__ import annotations

import pytest

from daily_agent.telemetry.sanitizer import (
    SanitizationError,
    redact,
    sanitize_free_text,
    scan,
    validate_export,
)
from tests.unit.telemetry.conftest import build_synthetic_run_record


@pytest.mark.parametrize(
    ("sample", "expected_class"),
    [
        ("Contact me at researcher@example.com anytime.", "email"),
        ("Call my Mumbai mobile at +91 9876543210 please.", "phone"),
        ("Call my office number at +1 (555) 123-4567.", "phone"),
        ("Here is the key sk-live-1234567890abcdef1234567890 for API calls.", "api_key"),
        ("Use AWS key AKIAIOSFODNN7EXAMPLE to authenticate.", "api_key"),
        ("My github pat is ghp_123456789012345678901234567890123456.", "api_key"),
        ("Header: Bearer secret-token-value-here-123456 in request.", "bearer_token"),
        (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
            "jwt",
        ),
        (
            "-----BEGIN RSA PRIVATE " "KEY-----\nMIIEowIBAAKCAQEA0...\n"
            "-----END RSA PRIVATE " "KEY-----",
            "private_key",
        ),
        ("Pay with card 4111 1111 1111 1111 right away.", "card_number"),
        ("Config line password=my_secret_pass_123 in settings.", "secret_assignment"),
        ("Resident Aadhaar: 2345 6789 0123 on document.", "aadhaar"),
        ("Tax PAN is ABCDE1234F on the card.", "pan"),
        ("Meet me at 123 Main Street tomorrow.", "street_address"),
        ("Office is at 42 MG Road, Bengaluru.", "street_address"),
        (
            "Token is dGhpcy1pcy1hLXZlcnktc2VjcmV0LXRva2VuLTEyMzQ1Ng== for access.",
            "high_entropy_token",
        ),
    ],
)
def test_scan_and_redact_individual_classes(sample: str, expected_class: str) -> None:
    findings = scan(sample)
    assert expected_class in findings

    redacted_text, classes = redact(sample)
    assert expected_class in classes
    assert f"[REDACTED:{expected_class}]" in redacted_text


def test_clean_memory_text_passes_without_findings() -> None:
    text = "Please remind me that the quarterly sprint review starts at 10:00 AM on Monday."
    findings = scan(text)
    assert len(findings) == 0

    redacted, classes = redact(text)
    assert redacted == text
    assert len(classes) == 0

    sanitized = sanitize_free_text(text, max_length=100)
    assert sanitized == text


def test_sanitize_free_text_redacts_and_truncates() -> None:
    raw = "My email is test@example.com and please remember that."
    sanitized = sanitize_free_text(raw, max_length=200)
    assert sanitized is not None
    assert "[REDACTED:email]" in sanitized
    assert "test@example.com" not in sanitized

    # Test truncation
    short = sanitize_free_text(raw, max_length=10)
    assert short is not None
    assert len(short) <= 10


def test_validate_export_accepts_clean_batch() -> None:
    run = build_synthetic_run_record()
    payload = {
        "batch_id": "a" * 64,
        "runs": [run.model_dump(mode="json")],
        "late_signals": [],
        "late_feedback": [],
    }
    # Clean realistic payload must not raise
    validate_export(payload)


def test_validate_export_rejects_injected_secret() -> None:
    run = build_synthetic_run_record()
    run_dict = run.model_dump(mode="json")
    # Inject an API key into live_fallback_reason
    run_dict["live_fallback_reason"] = "failed due to sk-live-1234567890abcdef1234567890"

    payload = {
        "batch_id": "a" * 64,
        "runs": [run_dict],
        "late_signals": [],
        "late_feedback": [],
    }

    with pytest.raises(SanitizationError) as exc_info:
        validate_export(payload)
    assert "api_key" in exc_info.value.classes
