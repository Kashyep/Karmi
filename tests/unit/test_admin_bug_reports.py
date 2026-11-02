from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from daily_agent.models import (
    AdminAuditLog,
    BugReport,
    GatewayRequestDay,
    Run,
    RunStatus,
    UsageWindow,
)
from tests.conftest import create_identity
from tests.unit.test_admin_api import Env

VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def env(test_context: dict[str, object]) -> Iterator[Env]:
    yield Env(test_context)  # type: ignore[arg-type]


def test_customers_get_403_on_every_new_admin_route(env: Env) -> None:
    _uid, _acc, customer_bearer = env.customer("customer-intruder")
    rep_id = "test-bug-id-403"

    # GET /v1/admin/bug-reports
    assert (
        env.client.get("/v1/admin/bug-reports", headers=customer_bearer).status_code == 403
    )

    # GET /v1/admin/bug-reports/{id}
    assert (
        env.client.get(f"/v1/admin/bug-reports/{rep_id}", headers=customer_bearer).status_code
        == 403
    )

    # GET /v1/admin/bug-reports/{id}/screenshot
    assert (
        env.client.get(
            f"/v1/admin/bug-reports/{rep_id}/screenshot", headers=customer_bearer
        ).status_code
        == 403
    )

    # PATCH /v1/admin/bug-reports/{id}
    assert (
        env.client.patch(
            f"/v1/admin/bug-reports/{rep_id}",
            headers=customer_bearer,
            json={"status": "triaged", "reason": "attempted unauthorized update"},
        ).status_code
        == 403
    )


def test_admin_bug_report_detail_and_screenshot_and_audited(env: Env) -> None:
    c_uid, c_acc, _b = env.customer("reporter-customer")
    headers = env.headers()

    with env.factory() as session:
        report = BugReport(
            id="bug-detail-01",
            account_id=c_acc,
            user_id=c_uid,
            ticket_number=42,
            client_report_id="client-rep-01",
            request_hash="hash01",
            category="crash",
            description="Detail test description text.",
            diagnostics={"os": "android", "app_version": "1.0"},
            screenshot=VALID_PNG,
            screenshot_content_type="image/png",
            status="new",
        )
        session.add(report)
        session.commit()

    # GET detail
    resp = env.client.get("/v1/admin/bug-reports/bug-detail-01", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "bug-detail-01"
    assert data["ticket"] == "KARMI-0042"
    assert data["category"] == "crash"
    assert data["status"] == "new"
    assert data["has_screenshot"] is True
    assert data["user"]["id"] == c_uid
    assert data["user"]["display_name"] == "reporter-customer"

    # Detail writes audit row: action="bug_report.read"
    audit_read = env.audit("bug_report.read")
    assert len(audit_read) == 1
    assert audit_read[0].target_user_id == c_uid
    assert audit_read[0].admin_user_id == env.root_id

    # GET screenshot
    s_resp = env.client.get("/v1/admin/bug-reports/bug-detail-01/screenshot", headers=headers)
    assert s_resp.status_code == 200
    assert s_resp.content == VALID_PNG
    assert s_resp.headers["Content-Type"].startswith("image/png")
    assert s_resp.headers["Cache-Control"] == "no-store"
    assert s_resp.headers["X-Content-Type-Options"] == "nosniff"

    # Screenshot writes audit row: action="bug_report.screenshot"
    audit_shot = env.audit("bug_report.screenshot")
    assert len(audit_shot) == 1
    assert audit_shot[0].target_user_id == c_uid
    assert audit_shot[0].admin_user_id == env.root_id

    # 404 on missing report
    assert env.client.get("/v1/admin/bug-reports/nonexistent", headers=headers).status_code == 404
    assert (
        env.client.get("/v1/admin/bug-reports/nonexistent/screenshot", headers=headers).status_code
        == 404
    )


def test_admin_bug_report_patch_transitions_and_audit(env: Env) -> None:
    c_uid, c_acc, _b = env.customer("patch-customer")
    headers = env.headers()

    with env.factory() as session:
        report = BugReport(
            id="bug-patch-01",
            account_id=c_acc,
            user_id=c_uid,
            ticket_number=99,
            client_report_id="client-rep-patch",
            request_hash="hash-patch",
            category="ui",
            description="UI bug report to patch.",
            diagnostics={"os": "android"},
            status="new",
        )
        session.add(report)
        session.commit()

    # Reason is required: missing or short reason -> 422
    r_no_reason = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "triaged"},
    )
    assert r_no_reason.status_code == 422

    r_short_reason = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "triaged", "reason": "  x "},
    )
    assert r_short_reason.status_code == 422

    # At least one of status or admin_notes required -> 422
    r_empty_body = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"reason": "valid reason but no fields"},
    )
    assert r_empty_body.status_code == 422

    # Invalid transition: new -> fixed -> 409 Conflict
    r_invalid = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "fixed", "reason": "skipping triage"},
    )
    assert r_invalid.status_code == 409

    # Valid transition: new -> triaged -> 200
    r_triaged = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "triaged", "admin_notes": "Reviewed and triaged.", "reason": "First triage pass"},
    )
    assert r_triaged.status_code == 200
    assert r_triaged.json()["status"] == "triaged"
    assert r_triaged.json()["admin_notes"] == "Reviewed and triaged."
    assert r_triaged.json()["triaged_at"] is not None

    # Check audit row
    audit_update = env.audit("bug_report.update")
    assert len(audit_update) == 1
    assert audit_update[0].target_user_id == c_uid
    assert audit_update[0].reason == "First triage pass"

    # Valid transition: triaged -> in_progress -> 200
    r_progress = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "in_progress", "reason": "Engineer started working"},
    )
    assert r_progress.status_code == 200
    assert r_progress.json()["status"] == "in_progress"

    # Valid transition: in_progress -> fixed -> 200
    r_fixed = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "fixed", "reason": "Fix landed in main"},
    )
    assert r_fixed.status_code == 200
    assert r_fixed.json()["status"] == "fixed"
    assert r_fixed.json()["resolved_at"] is not None

    # Valid transition: fixed -> closed -> 200
    r_closed = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "closed", "reason": "Confirmed verified"},
    )
    assert r_closed.status_code == 200
    assert r_closed.json()["status"] == "closed"

    # Valid transition: closed -> triaged (reopen) -> 200
    r_reopen = env.client.patch(
        "/v1/admin/bug-reports/bug-patch-01",
        headers=headers,
        json={"status": "triaged", "reason": "Reopening issue"},
    )
    assert r_reopen.status_code == 200
    assert r_reopen.json()["status"] == "triaged"


def test_admin_bug_reports_pagination_stable_across_equal_timestamps(env: Env) -> None:
    c_uid, c_acc, _b = env.customer("pagination-customer")
    headers = env.headers()
    pinned_time = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)

    # Seed 5 bug reports with identical created_at
    with env.factory() as session:
        for i in range(1, 6):
            session.add(
                BugReport(
                    id=f"bug-page-{i:02d}",
                    account_id=c_acc,
                    user_id=c_uid,
                    ticket_number=100 + i,
                    client_report_id=f"client-page-{i}",
                    request_hash=f"hash-page-{i}",
                    category="other",
                    description=f"Pagination test description {i}.",
                    diagnostics={"os": "android"},
                    status="new",
                    created_at=pinned_time,
                    updated_at=pinned_time,
                )
            )
        session.commit()

    seen_ids: list[str] = []
    cursor: str | None = None

    while True:
        url = "/v1/admin/bug-reports?limit=2"
        if cursor:
            url += f"&cursor={cursor}"
        resp = env.client.get(url, headers=headers)
        assert resp.status_code == 200
        page = resp.json()
        items = page["items"]
        assert len(items) <= 2
        for item in items:
            seen_ids.append(item["id"])
        cursor = page["next_cursor"]
        if not cursor:
            break

    # All 5 unique reports retrieved with zero duplicates and zero skipped!
    assert len(seen_ids) == 5
    assert len(set(seen_ids)) == 5
    assert set(seen_ids) == {f"bug-page-{i:02d}" for i in range(1, 6)}


def test_monitor_new_keys_present_with_correct_values_on_seeded_db(env: Env) -> None:
    c_uid, c_acc, _b = env.customer("seeded-customer")
    headers = env.headers()
    now = datetime.now(UTC)
    day_key = now.strftime("%Y-%m-%d")

    with env.factory() as session:
        # Seed GatewayRequestDay
        session.add(GatewayRequestDay(day_key=day_key, requests_used=17))

        # Seed Runs today (3 completed, 1 failed)
        session.add(
            Run(
                id="run-seed-1",
                account_id=c_acc,
                user_id=c_uid,
                logical_request_id="seed-1",
                status=RunStatus.COMPLETED,
                served_model="fake-economy",
                served_provider="openrouter",
                latency_ms=120,
                created_at=now,
            )
        )
        session.add(
            Run(
                id="run-seed-2",
                account_id=c_acc,
                user_id=c_uid,
                logical_request_id="seed-2",
                status=RunStatus.COMPLETED,
                served_model="fake-economy",
                served_provider="openrouter",
                latency_ms=180,
                created_at=now,
            )
        )
        session.add(
            Run(
                id="run-seed-3",
                account_id=c_acc,
                user_id=c_uid,
                logical_request_id="seed-3",
                status=RunStatus.COMPLETED,
                served_model="fake-economy",
                served_provider="openrouter",
                latency_ms=150,
                created_at=now,
            )
        )
        session.add(
            Run(
                id="run-seed-4",
                account_id=c_acc,
                user_id=c_uid,
                logical_request_id="seed-4",
                status=RunStatus.FAILED,
                served_model="fake-economy",
                served_provider="openrouter",
                latency_ms=300,
                created_at=now,
            )
        )

        # Seed BugReports (2 open: new, triaged; 1 closed: fixed)
        session.add(
            BugReport(
                id="bug-open-1",
                account_id=c_acc,
                user_id=c_uid,
                ticket_number=201,
                client_report_id="c-201",
                request_hash="h-201",
                category="chat",
                description="Open report 1",
                diagnostics={},
                status="new",
            )
        )
        session.add(
            BugReport(
                id="bug-open-2",
                account_id=c_acc,
                user_id=c_uid,
                ticket_number=202,
                client_report_id="c-202",
                request_hash="h-202",
                category="ui",
                description="Open report 2",
                diagnostics={},
                status="triaged",
            )
        )
        session.add(
            BugReport(
                id="bug-closed-1",
                account_id=c_acc,
                user_id=c_uid,
                ticket_number=203,
                client_report_id="c-203",
                request_hash="h-203",
                category="crash",
                description="Closed report 1",
                diagnostics={},
                status="fixed",
            )
        )
        session.commit()

    # Clear monitor cache if any
    if hasattr(env.client.app.state, "admin_monitor_cache"):  # type: ignore[union-attr]
        env.client.app.state.admin_monitor_cache = None  # type: ignore[union-attr]

    resp = env.client.get("/v1/admin/monitor", headers=headers)
    assert resp.status_code == 200
    mon = resp.json()

    assert mon["requests_today"] == 17
    assert mon["daily_request_cap"] == env.settings.gateway_daily_request_limit
    # 3 completed out of 4 total -> 0.75 success rate
    assert mon["success_rate"] == 0.75
    # 2 open bug reports (new, triaged)
    assert mon["open_bug_reports"] == 2
    assert isinstance(mon["cost_today_inr"], float)
    assert isinstance(mon["model_health"], list)

    # Check model health entry for fake-economy
    economy_health = [m for m in mon["model_health"] if m["model"] == "fake-economy"]
    assert len(economy_health) == 1
    assert economy_health[0]["provider"] == "openrouter"
    assert economy_health[0]["runs"] == 4
    # 1 failed out of 4 -> error_rate 0.25
    assert economy_health[0]["error_rate"] == 0.25
    # latencies [120, 150, 180, 300] -> p50 is index 2 -> 180.0
    assert economy_health[0]["p50_latency_ms"] == 180.0
    assert economy_health[0]["last_success_at"] is not None

    # Check user detail has open_bug_reports
    u_detail = env.client.get(f"/v1/admin/users/{c_uid}", headers=headers).json()
    assert u_detail["open_bug_reports"] == 2

    # Check users list items have open_bug_reports
    u_list = env.client.get(f"/v1/admin/users?q={c_uid}", headers=headers).json()
    assert len(u_list["items"]) == 1
    assert u_list["items"][0]["open_bug_reports"] == 2
