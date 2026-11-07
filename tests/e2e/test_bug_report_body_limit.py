from __future__ import annotations

import base64
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from daily_agent.models import BugReport
from tests.conftest import create_identity

pytestmark = pytest.mark.e2e

VALID_PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode("ascii")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sample_diagnostics() -> dict[str, Any]:
    return {
        "app_version": "0.1.0",
        "build_number": "5",
        "git_sha": "abc1234",
        "os": "android",
        "os_version": "16",
        "device_model": "Pixel 9a",
        "locale": "en-IN",
        "text_scale": 1.0,
        "theme": "dark",
        "reduce_transparency": False,
        "plan": "ananta",
        "screen": "chat",
        "recent_request_ids": ["req-1", "req-2"],
        "recent_error_codes": ["timeout"],
        "run_id": "run-test-1",
        "error_code": "E_TIMEOUT",
    }


def test_content_length_over_limit_returns_413_and_no_db_row(
    test_context: dict[str, Any],
) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="body-limit-tester")  # type: ignore[arg-type]

    # Content-Length claiming 8 MB (> 7 MB limit)
    oversized_len = str(8 * 1024 * 1024)
    resp = client.post(
        "/v1/bug-reports",
        headers={**auth(token), "Content-Length": oversized_len},
        content=b"{}",
    )
    assert resp.status_code == 413
    assert resp.json()["detail"] == "screenshot exceeds 5 MB limit"

    # Handler was never reached: no bug report row created
    with factory() as session:  # type: ignore[operator]
        rows = session.scalars(select(BugReport)).all()
        assert len(rows) == 0


def test_chunked_streaming_body_over_limit_returns_413(
    test_context: dict[str, Any],
) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="chunked-limit-tester")  # type: ignore[arg-type]

    # Generator stream without Content-Length exceeding 7 MB limit (8 x 1 MB chunks)
    def chunk_stream() -> Any:
        chunk = b"A" * (1024 * 1024)
        for _ in range(8):
            yield chunk

    resp = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        content=chunk_stream(),
    )
    assert resp.status_code == 413
    assert resp.json()["detail"] == "screenshot exceeds 5 MB limit"

    with factory() as session:  # type: ignore[operator]
        rows = session.scalars(select(BugReport)).all()
        assert len(rows) == 0


def test_valid_small_request_still_returns_201(
    test_context: dict[str, Any],
) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="small-valid-tester")  # type: ignore[arg-type]

    payload = {
        "client_report_id": str(uuid.uuid4()),
        "category": "chat",
        "description": "Small valid bug report with normal payload.",
        "diagnostics": sample_diagnostics(),
        "screenshot": {"content_type": "image/png", "data_base64": VALID_PNG},
    }

    resp = client.post("/v1/bug-reports", headers=auth(token), json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "new"
    assert data["ticket"].startswith("KARMI-")

    with factory() as session:  # type: ignore[operator]
        rows = session.scalars(select(BugReport)).all()
        assert len(rows) == 1
        assert rows[0].id == data["id"]
