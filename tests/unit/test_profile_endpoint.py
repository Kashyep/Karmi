"""Unit tests for GET /v1/user/profile and PATCH /v1/user/profile.

Covers:
- Auth required (401 without token)
- 422 on whitespace-only name
- 422 on name exceeding max length
- Successful round-trip (PATCH persists, GET returns updated value)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import create_identity

# ---------------------------------------------------------------------------
# GET /v1/user/profile
# ---------------------------------------------------------------------------


def test_get_profile_requires_auth(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    resp = client.get("/v1/user/profile")
    assert resp.status_code == 401


def test_get_profile_returns_display_name(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    client: TestClient = test_context["client"]  # type: ignore[assignment]

    with factory() as session:  # type: ignore[operator]
        _, _, token = create_identity(session, settings, name="GetTester")  # type: ignore[arg-type]

    resp = client.get("/v1/user/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "GetTester"
    assert "id" in data


# ---------------------------------------------------------------------------
# PATCH /v1/user/profile
# ---------------------------------------------------------------------------


def test_patch_profile_requires_auth(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    resp = client.patch("/v1/user/profile", json={"display_name": "NoAuth"})
    assert resp.status_code == 401

@pytest.mark.parametrize(
    "bad_name",
    [
        "",           # empty string
        " ",          # single space
        "   ",        # all whitespace
        "\t\n",       # tabs + newlines
    ],
)
def test_patch_profile_rejects_blank_or_too_short(
    test_context: dict[str, object], bad_name: str
) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    client: TestClient = test_context["client"]  # type: ignore[assignment]

    with factory() as session:  # type: ignore[operator]
        _, _, token = create_identity(session, settings, name="ValidationTarget")  # type: ignore[arg-type]

    resp = client.patch(
        "/v1/user/profile",
        json={"display_name": bad_name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, f"Expected 422 for name={bad_name!r}, got {resp.status_code}"
def test_patch_profile_accepts_single_character_name(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    with factory() as session:  # type: ignore[operator]
        _, _, token = create_identity(session, settings, name="SingleCharTarget")  # type: ignore[arg-type]
    response = client.patch(
        "/v1/user/profile",
        json={"display_name": " A "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "A"



def test_patch_profile_rejects_too_long_name(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    client: TestClient = test_context["client"]  # type: ignore[assignment]

    with factory() as session:  # type: ignore[operator]
        _, _, token = create_identity(session, settings, name="LongNameTarget")  # type: ignore[arg-type]

    too_long = "A" * 121
    resp = client.patch(
        "/v1/user/profile",
        json={"display_name": too_long},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_patch_profile_strips_and_persists(test_context: dict[str, object]) -> None:
    """PATCH strips surrounding whitespace and persists via GET."""
    factory = test_context["factory"]
    settings = test_context["settings"]
    client: TestClient = test_context["client"]  # type: ignore[assignment]

    with factory() as session:  # type: ignore[operator]
        _, _, token = create_identity(session, settings, name="Original")  # type: ignore[arg-type]

    # PATCH with whitespace-padded name
    resp = client.patch(
        "/v1/user/profile",
        json={"display_name": "  Alice Liddell  "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Alice Liddell"

    # GET must return the same stripped value
    resp2 = client.get("/v1/user/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp2.status_code == 200
    assert resp2.json()["display_name"] == "Alice Liddell"


def test_patch_profile_updates_display_name(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    client: TestClient = test_context["client"]  # type: ignore[assignment]

    with factory() as session:  # type: ignore[operator]
        _, _, token = create_identity(session, settings, name="BeforeUpdate")  # type: ignore[arg-type]

    resp = client.patch(
        "/v1/user/profile",
        json={"display_name": "AfterUpdate"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "AfterUpdate"

    # Persist check
    resp2 = client.get("/v1/user/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp2.json()["display_name"] == "AfterUpdate"


def test_profile_does_not_create_missing_user_row(test_context: dict[str, object]) -> None:
    """A principal missing its provisioned user row is not repaired by profile reads."""
    from daily_agent.models import Account, User
    from daily_agent.security import Principal, require_principal

    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    with factory() as session:  # type: ignore[operator]
        account = Account(name="Fresh Clerk account")
        session.add(account)
        session.commit()
        principal = Principal(user_id="fresh-clerk-user", account_id=account.id, role="customer")
    client.app.dependency_overrides[require_principal] = lambda: principal
    try:
        response = client.get("/v1/user/profile")
        assert response.status_code == 404
        with factory() as session:  # type: ignore[operator]
            assert session.get(User, principal.user_id) is None
    finally:
        client.app.dependency_overrides.pop(require_principal, None)
