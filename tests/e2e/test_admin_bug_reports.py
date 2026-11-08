from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.unit.test_admin_api import Env

pytestmark = pytest.mark.e2e

VALID_STATUSES = [
    "new",
    "triaged",
    "in_progress",
    "fixed",
    "closed",
    "duplicate",
    "wontfix",
]

VALID_CATEGORIES = [
    "crash",
    "chat",
    "ui",
    "account",
    "other",
]


@pytest.fixture
def env(test_context: dict[str, object]) -> Iterator[Env]:
    yield Env(test_context)  # type: ignore[arg-type]


def test_admin_bug_reports_rejects_unknown_status(env: Env) -> None:
    headers = env.headers()
    response = env.client.get("/v1/admin/bug-reports?status=unknown", headers=headers)
    assert response.status_code == 422


def test_admin_bug_reports_rejects_unknown_category(env: Env) -> None:
    headers = env.headers()
    response = env.client.get("/v1/admin/bug-reports?category=invalid", headers=headers)
    assert response.status_code == 422


@pytest.mark.parametrize("status_filter", VALID_STATUSES)
def test_admin_bug_reports_accepts_valid_statuses(env: Env, status_filter: str) -> None:
    headers = env.headers()
    response = env.client.get(f"/v1/admin/bug-reports?status={status_filter}", headers=headers)
    assert response.status_code == 200
    assert "items" in response.json()


@pytest.mark.parametrize("category_filter", VALID_CATEGORIES)
def test_admin_bug_reports_accepts_valid_categories(env: Env, category_filter: str) -> None:
    headers = env.headers()
    response = env.client.get(f"/v1/admin/bug-reports?category={category_filter}", headers=headers)
    assert response.status_code == 200
    assert "items" in response.json()


def test_admin_bug_reports_empty_and_absent_filters(env: Env) -> None:
    headers = env.headers()
    # Absent params -> 200
    r_absent = env.client.get("/v1/admin/bug-reports", headers=headers)
    assert r_absent.status_code == 200
    assert "items" in r_absent.json()

    # Empty params -> 200
    r_empty = env.client.get("/v1/admin/bug-reports?status=&category=", headers=headers)
    assert r_empty.status_code == 200
    assert "items" in r_empty.json()


def test_admin_bug_reports_cursor_length_bound(env: Env) -> None:
    headers = env.headers()
    oversized_cursor = "a" * 129
    r_toolong = env.client.get(f"/v1/admin/bug-reports?cursor={oversized_cursor}", headers=headers)
    assert r_toolong.status_code == 422

    valid_cursor = "2026-11-08T00:00:00.000000Z|test-id"
    r_valid = env.client.get(f"/v1/admin/bug-reports?cursor={valid_cursor}", headers=headers)
    assert r_valid.status_code == 200
    assert "items" in r_valid.json()
