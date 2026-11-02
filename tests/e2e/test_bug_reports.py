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
VALID_JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 32).decode("ascii")


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


def test_create_bug_report_and_replay_and_conflict(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="reporter1")  # type: ignore[arg-type]

    report_id = str(uuid.uuid4())
    payload = {
        "client_report_id": report_id,
        "category": "chat",
        "description": "The assistant response stopped abruptly mid-sentence.",
        "diagnostics": sample_diagnostics(),
        "screenshot": {"content_type": "image/png", "data_base64": VALID_PNG},
    }

    # 1. First submission -> 201 Created
    resp = client.post("/v1/bug-reports", headers=auth(token), json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert set(data.keys()) == {"id", "ticket", "status", "created_at"}
    assert data["status"] == "new"
    assert data["ticket"].startswith("KARMI-")
    bug_id = data["id"]

    # 2. Replay with identical payload -> 200 OK same body
    replay = client.post("/v1/bug-reports", headers=auth(token), json=payload)
    assert replay.status_code == 200
    assert replay.json() == data

    # 3. Conflict: same client_report_id, different description -> 409 Conflict
    conflict_payload = dict(payload)
    conflict_payload["description"] = "A completely different description for conflict test."
    conflict = client.post("/v1/bug-reports", headers=auth(token), json=conflict_payload)
    assert conflict.status_code == 409

    # 4. GET /v1/bug-reports/{id} returns caller's report without screenshot bytes
    get_resp = client.get(f"/v1/bug-reports/{bug_id}", headers=auth(token))
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["id"] == bug_id
    assert detail["ticket"] == data["ticket"]
    assert detail["category"] == "chat"
    assert detail["description"] == payload["description"]
    assert detail["status"] == "new"
    assert detail["has_screenshot"] is True
    assert "screenshot" not in detail


def test_rate_limit_and_replay_exemption(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="ratelimit-user")  # type: ignore[arg-type]

    first_report_id = str(uuid.uuid4())
    first_payload = {
        "client_report_id": first_report_id,
        "category": "ui",
        "description": "First bug report description valid.",
        "diagnostics": sample_diagnostics(),
    }
    r1 = client.post("/v1/bug-reports", headers=auth(token), json=first_payload)
    assert r1.status_code == 201

    r2 = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "crash",
            "description": "Second bug report description valid.",
            "diagnostics": sample_diagnostics(),
        },
    )
    assert r2.status_code == 201

    r3 = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "account",
            "description": "Third bug report description valid.",
            "diagnostics": sample_diagnostics(),
        },
    )
    assert r3.status_code == 201

    # 4th new report -> 429 Too Many Requests with Retry-After header
    r4 = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "other",
            "description": "Fourth bug report description valid.",
            "diagnostics": sample_diagnostics(),
        },
    )
    assert r4.status_code == 429
    assert "Retry-After" in r4.headers
    retry_after = int(r4.headers["Retry-After"])
    assert retry_after > 0

    # Replay of an existing report still returns 200 (replays do not count against rate limit)
    replay = client.post("/v1/bug-reports", headers=auth(token), json=first_payload)
    assert replay.status_code == 200


def test_screenshot_size_413_and_type_415(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="media-tester")  # type: ignore[arg-type]

    # Size > 5MB -> 413
    oversized_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5_242_881 - 8)
    oversized_b64 = base64.b64encode(oversized_bytes).decode("ascii")
    r_size = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "ui",
            "description": "Testing oversized screenshot upload.",
            "diagnostics": sample_diagnostics(),
            "screenshot": {"content_type": "image/png", "data_base64": oversized_b64},
        },
    )
    assert r_size.status_code == 413

    # Unsupported content_type (image/webp) -> 415
    r_webp = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "ui",
            "description": "Testing unsupported webp content type.",
            "diagnostics": sample_diagnostics(),
            "screenshot": {"content_type": "image/webp", "data_base64": VALID_PNG},
        },
    )
    assert r_webp.status_code == 415

    # PNG content_type with JPEG bytes -> 415
    r_png_with_jpeg = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "ui",
            "description": "PNG declared but JPEG bytes provided.",
            "diagnostics": sample_diagnostics(),
            "screenshot": {"content_type": "image/png", "data_base64": VALID_JPEG},
        },
    )
    assert r_png_with_jpeg.status_code == 415

    # PNG content_type with garbage bytes -> 415
    garbage_b64 = base64.b64encode(b"random garbage text that is not an image").decode("ascii")
    r_garbage = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "ui",
            "description": "PNG declared but random garbage bytes provided.",
            "diagnostics": sample_diagnostics(),
            "screenshot": {"content_type": "image/png", "data_base64": garbage_b64},
        },
    )
    assert r_garbage.status_code == 415

    # JPEG content_type with PNG bytes -> 415
    r_jpeg_with_png = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "ui",
            "description": "JPEG declared but PNG bytes provided.",
            "diagnostics": sample_diagnostics(),
            "screenshot": {"content_type": "image/jpeg", "data_base64": VALID_PNG},
        },
    )
    assert r_jpeg_with_png.status_code == 415

    # Valid JPEG magic bytes succeeds -> 201
    r_jpeg = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "ui",
            "description": "JPEG declared with genuine JPEG magic bytes.",
            "diagnostics": sample_diagnostics(),
            "screenshot": {"content_type": "image/jpeg", "data_base64": VALID_JPEG},
        },
    )
    assert r_jpeg.status_code == 201


def test_diagnostics_validation_and_description_bounds(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="validator-tester")  # type: ignore[arg-type]

    # Unknown key in diagnostics -> 422
    bad_diag = sample_diagnostics()
    bad_diag["unexpected_custom_key"] = "malicious_or_unknown"
    r_unknown_key = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "crash",
            "description": "Testing unknown diagnostics key rejection.",
            "diagnostics": bad_diag,
        },
    )
    assert r_unknown_key.status_code == 422

    # String in diagnostics > 128 chars -> 422
    long_str_diag = sample_diagnostics()
    long_str_diag["os_version"] = "X" * 129
    r_long_str = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "crash",
            "description": "Testing too long string in diagnostics.",
            "diagnostics": long_str_diag,
        },
    )
    assert r_long_str.status_code == 422

    # List in diagnostics > 10 items -> 422
    long_list_diag = sample_diagnostics()
    long_list_diag["recent_request_ids"] = [f"req-{i}" for i in range(11)]
    r_long_list = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "crash",
            "description": "Testing too long list in diagnostics.",
            "diagnostics": long_list_diag,
        },
    )
    assert r_long_list.status_code == 422

    # Description < 10 chars after strip -> 422
    r_short_desc = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "crash",
            "description": "   short  ",
            "diagnostics": sample_diagnostics(),
        },
    )
    assert r_short_desc.status_code == 422

    # Description > 2000 chars -> 422
    r_long_desc = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "crash",
            "description": "A" * 2001,
            "diagnostics": sample_diagnostics(),
        },
    )
    assert r_long_desc.status_code == 422


def test_another_account_get_returns_404(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc1, _u1, token1 = create_identity(session, settings, name="user-one")  # type: ignore[arg-type]
        _acc2, _u2, token2 = create_identity(session, settings, name="user-two")  # type: ignore[arg-type]

    create_resp = client.post(
        "/v1/bug-reports",
        headers=auth(token1),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "chat",
            "description": "User one's confidential bug report.",
            "diagnostics": sample_diagnostics(),
        },
    )
    assert create_resp.status_code == 201
    bug_id = create_resp.json()["id"]

    # User two attempts to fetch user one's report -> 404
    foreign_resp = client.get(f"/v1/bug-reports/{bug_id}", headers=auth(token2))
    assert foreign_resp.status_code == 404


def test_sentinel_chat_string_never_appears_in_bug_report(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, _user, token = create_identity(session, settings, name="chat-privacy-user")  # type: ignore[arg-type]

    sentinel = "SENTINEL_PRIVACY_SECRET_987654321_DO_NOT_LEAK"

    # Send a chat message with the sentinel string
    chat_resp = client.post(
        "/v1/messages",
        headers=auth(token),
        json={"text": f"Here is my private info: {sentinel}", "idempotency_key": "msg-privacy-1"},
    )
    assert chat_resp.status_code == 200

    # Submit a bug report in the same account
    report_resp = client.post(
        "/v1/bug-reports",
        headers=auth(token),
        json={
            "client_report_id": str(uuid.uuid4()),
            "category": "chat",
            "description": "Reporting an issue after chat session.",
            "diagnostics": sample_diagnostics(),
        },
    )
    assert report_resp.status_code == 201
    report_data = report_resp.json()
    bug_id = report_data["id"]

    # Read back bug report via customer API
    get_resp = client.get(f"/v1/bug-reports/{bug_id}", headers=auth(token))
    assert get_resp.status_code == 200
    assert sentinel not in get_resp.text

    # Read back bug report directly from database
    with factory() as session:  # type: ignore[operator]
        stored_report = session.scalar(select(BugReport).where(BugReport.id == bug_id))
        assert stored_report is not None
        assert sentinel not in stored_report.description
        assert sentinel not in str(stored_report.diagnostics)
