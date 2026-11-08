from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from daily_agent.admin_service import inr_to_micro, micro_to_inr
from daily_agent.plans import MICRO_PER_INR, SYNTHETIC_POLICIES
from tests.conftest import create_identity


def test_inr_micro_conversions() -> None:
    assert MICRO_PER_INR == 1_000_000
    assert inr_to_micro(1.0) == 1_000_000
    assert inr_to_micro(0.5) == 500_000
    assert inr_to_micro(149.0) == 149_000_000
    assert inr_to_micro(0.000001) == 1
    assert inr_to_micro(0.0) == 0

    assert micro_to_inr(1_000_000) == 1.0
    assert micro_to_inr(500_000) == 0.5
    assert micro_to_inr(149_000_000) == 149.0
    assert micro_to_inr(1) == 0.000001
    assert micro_to_inr(0) == 0.0


def test_get_plans_requires_auth(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    resp = client.get("/v1/plans")
    assert resp.status_code == 401


def test_get_plans_returns_catalog_with_price_inr(test_context: dict[str, Any]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _acc, _user, token = create_identity(session, settings, name="plans-tester")  # type: ignore[arg-type]

    resp = client.get("/v1/plans", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == len(SYNTHETIC_POLICIES)

    plans_by_id = {p["id"]: p for p in data}
    assert set(plans_by_id.keys()) == {"ananta", "yanta", "trika", "parth"}

    for plan_id, policy in SYNTHETIC_POLICIES.items():
        plan = plans_by_id[plan_id]
        assert plan["label"] == policy.display_name
        assert plan["price_inr"] == policy.price_inr
        assert plan["everyday_limit"] == policy.everyday_limit
        assert plan["daily_token_limit"] == policy.daily_token_limit
        assert plan["input_tokens"] == policy.input_tokens
        assert plan["output_tokens"] == policy.output_tokens
        assert plan["request_cost_cap_micro"] == policy.request_cost_cap_micro
        assert plan["period_cost_cap_micro"] == policy.period_cost_cap_micro
        assert plan["model_classes"] == list(policy.model_classes)
        assert plan["min_class"] == policy.min_class
