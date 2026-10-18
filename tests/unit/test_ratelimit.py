import logging

import pytest

from daily_agent.ratelimit import SlidingWindowLimiter, install_log_redaction, redact


class Clock:
    now = 100.0

    def __call__(self) -> float:
        return self.now


def test_limiter_blocks_after_the_limit_per_key_and_recovers() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60, clock=clock)
    assert limiter.check("a") is None
    clock.now += 10
    assert limiter.check("a") is None
    assert limiter.check("a") == 50
    assert limiter.check("b") is None, "keys are independent"
    clock.now += 51
    assert limiter.check("a") is None, "the oldest hit left the window"


@pytest.mark.parametrize(
    "secret",
    [
        "Bearer abcdefghijklmnopqrstuvwxyz",
        "sk-or-v1-abcdef0123456789",
        "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyXzEyMyJ9.c2lnbmF0dXJlMTIzNDU2",
        "OPENROUTER_API_KEY=hunter2hunter2",
        "postgresql+psycopg://app:s3cr3tpass@db.example/app",
    ],
)
def test_redact_removes_credentials(secret: str) -> None:
    out = redact(f"call failed: {secret} end")
    assert "abcdefghijkl" not in out
    assert "0123456789" not in out
    assert "hunter2" not in out
    assert "s3cr3tpass" not in out
    assert "c2lnbmF0" not in out
    assert out.startswith("call failed:") and out.endswith("end")


def test_installed_redaction_applies_to_every_logger(caplog: pytest.LogCaptureFixture) -> None:
    install_log_redaction()
    with caplog.at_level(logging.INFO):
        logging.getLogger("any.module").info("token=%s", "Bearer abcdefghijklmnop")
    assert "abcdefghijklmnop" not in caplog.text
    assert "[REDACTED]" in caplog.text
