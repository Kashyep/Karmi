import logging

import pytest
from uvicorn.logging import AccessFormatter

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
        "sk_" + "live_" + "1234567890abcdef12345678",
        "sk_" + "test_" + "1234567890abcdef12345678",
        "AIza" + "A" * 35,
        "api-key=hunter2hunter2",
        "apikey=hunter2hunter2",
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


def test_redaction_keeps_uvicorn_access_args_formattable() -> None:
    install_log_redaction()
    factory = logging.getLogRecordFactory()
    record = factory(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/api/v1/x?token=SECRETVALUE123456&q=1", "1.1", 200),
        None,
    )
    assert len(record.args) == 5
    formatter = AccessFormatter(
        "%(client_addr)s - %(request_line)s %(status_code)s", use_colors=False
    )
    out = formatter.format(record)
    assert "GET" in out
    assert "200" in out
    assert "SECRETVALUE" not in out
    assert "[REDACTED]" in out


def test_redact_leaves_non_matching_messages_unchanged() -> None:
    message = "Request completed in 42ms for user_id=usr_123 status=200 session=active"
    assert redact(message) == message


@pytest.mark.parametrize(
    ("secret", "canary"),
    [
        ("Bearer abcdefghijklmnopqrstuvwxyz", "abcdefghijkl"),
        ("sk-or-v1-abcdef0123456789", "abcdef0123456789"),
        ("sk_" + "live_" + "1234567890abcdef12345678", "abcdef12345678"),
        ("sk_" + "test_" + "1234567890abcdef12345678", "abcdef12345678"),
        ("AIza" + "A" * 35, "A" * 20),
        ("api-key=supersecretapikey123", "supersecretapikey123"),
        ("apikey=supersecretapikey456", "supersecretapikey456"),
        ("OPENROUTER_API_KEY=hunter2hunter2", "hunter2hunter2"),
        ("postgresql+psycopg://app:s3cr3tpass@db.example/app", "s3cr3tpass"),
    ],
)
def test_redaction_in_formatted_traceback(secret: str, canary: str) -> None:
    install_log_redaction()
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    try:
        raise ValueError(f"failure detail with {secret}")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "test.traceback", logging.ERROR, "test.py", 42, "operation failed", (), sys.exc_info()
        )
        out = formatter.format(record)
        assert canary not in out
        assert record.exc_text is not None
        assert canary not in record.exc_text
        assert "[REDACTED]" in out or "[REDACTED_KEY]" in out


def test_formatter_without_exception_leaves_exc_text_none() -> None:
    install_log_redaction()
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    record = logging.LogRecord(
        "test.normal", logging.INFO, "test.py", 10, "normal log message", (), None
    )
    out = formatter.format(record)
    assert out == "INFO - normal log message"
    assert record.exc_text is None
