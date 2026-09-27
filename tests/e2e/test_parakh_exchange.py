"""TelemetryBatchV1 export and PolicyBundleV1 shadow slots through the real HTTP flow."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.config import Settings
from daily_agent.models import PolicyBundleEvent, RoutingDecision, Subscription
from daily_agent.parakh import receiver
from daily_agent.parakh.bundle import BundleRejected
from daily_agent.parakh.telemetry import build_telemetry_batch
from tests.conftest import create_identity
from tests.parakh_helpers import TEST_PUBLIC_KEY, make_karmi_bundle, sign_directory

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "docs/contracts/parakh/telemetry_batch_v1.schema.json").read_text(
        encoding="utf-8"
    )
)
SECRET_TEXT = "remember Bearer abcdefghijklmnop and my card 4111 1111 1111 1111"  # noqa: S105
OPERATOR = {"actor": "ops-test", "reason": "e2e shadow check"}


@pytest.fixture
def exchange(test_context: dict[str, object], tmp_path: Path) -> dict[str, Any]:
    settings = test_context["settings"]
    assert isinstance(settings, Settings)
    settings.data_dir = tmp_path / "data"
    settings.parakh_trusted_public_keys = [TEST_PUBLIC_KEY]
    factory = test_context["factory"]
    assert isinstance(factory, sessionmaker)
    with factory() as session:
        account, _user, token = create_identity(session, settings, name="Trika user")
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        subscription.plan_id = "trika"
        session.commit()
    return {"settings": settings, "factory": factory, "client": test_context["client"],
            "headers": {"Authorization": f"Bearer {token}"}, "tmp": tmp_path}


def _send(ex: dict[str, Any], key: str, text: str = "Draft a note to the landlord") -> Any:
    client = ex["client"]
    assert isinstance(client, TestClient)
    response = client.post(
        "/v1/messages", json={"text": text, "idempotency_key": key}, headers=ex["headers"]
    )
    assert response.status_code == 200, response.text
    return response.json()


WINDOW_START = datetime.now(UTC) - timedelta(days=1)
WINDOW_END = datetime.now(UTC) + timedelta(days=1)


def _export(ex: dict[str, Any]) -> dict[str, Any]:
    session: Session
    with ex["factory"]() as session:
        return build_telemetry_batch(session, start=WINDOW_START, end=WINDOW_END)


def _missing_required(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    missing = [f"{path}.{name}" for name in schema.get("required", []) if name not in value]
    for name, sub in schema.get("properties", {}).items():
        if isinstance(value, dict) and isinstance(value.get(name), dict):
            missing += _missing_required(value[name], sub, f"{path}.{name}")
        if isinstance(value, dict) and isinstance(value.get(name), list) and "items" in sub:
            for i, item in enumerate(value[name]):
                if isinstance(item, dict):
                    missing += _missing_required(item, sub["items"], f"{path}.{name}[{i}]")
    return missing


def test_messages_export_propensity_logged_telemetry_without_content(
    exchange: dict[str, Any],
) -> None:
    _send(exchange, "msg-0001")
    _send(exchange, "msg-0002", SECRET_TEXT)
    batch = _export(exchange)
    assert _missing_required(batch, SCHEMA) == []
    assert batch == _export(exchange)  # deterministic, so Parakh re-imports idempotently
    assert len(batch["runs"]) == 2
    for run in batch["runs"]:
        assert run["tier"] == "trika"
        [decision] = run["decisions"]
        assert decision["shadow"] is False
        assert decision["selection_probability"] == 1.0
        assert decision["exploration"] is False
        assert decision["eligible_models"] == ["karmi/fake-economy"]
        assert (decision["selected_provider"], decision["selected_model"]) == ("karmi", "fake-economy")
        assert run["outcome"]["currency"] == "XTS"
    text = json.dumps(batch)
    for fragment in ("landlord", "Bearer", "4111", "Trika user", "msg-0001", "msg-0002"):
        assert fragment not in text


def test_verified_bundle_shadows_without_changing_the_live_route(exchange: dict[str, Any]) -> None:
    settings: Settings = exchange["settings"]
    bundle = make_karmi_bundle(exchange["tmp"] / "incoming", "policy-karmi.1",
                               bias={"karmi/fake-economy": 1.0})
    with exchange["factory"]() as session:
        record = receiver.receive_bundle(session, settings, bundle, **OPERATOR)
        assert receiver.receive_bundle(session, settings, bundle, **OPERATOR).id == record.id
        with pytest.raises(receiver.BundleStateError, match="cannot move"):
            receiver.transition(session, settings, "policy-karmi.1", receiver.SHADOW, **OPERATOR)
        receiver.transition(session, settings, "policy-karmi.1", receiver.STAGED, **OPERATOR)
        receiver.transition(session, settings, "policy-karmi.1", receiver.SHADOW, **OPERATOR)
        for live_state in ("canary", "production"):
            with pytest.raises(receiver.BundleStateError, match="not implemented"):
                receiver.transition(session, settings, "policy-karmi.1", live_state, **OPERATOR)
        session.commit()
    stored = Path(record.storage_path)
    assert stored.parent == settings.data_dir / "policy_bundles"
    assert all(not (p.stat().st_mode & 0o222) for p in stored.iterdir())

    reply = _send(exchange, "msg-shadow")
    assert reply["route"] == "fake-economy"
    [run] = _export(exchange)["runs"]
    live, shadow = sorted(run["decisions"], key=lambda d: d["shadow"])
    assert live["policy_version"] == "karmi-static-v1"
    assert live["selection_probability"] == 1.0
    assert shadow["shadow"] is True
    assert shadow["policy_version"] == "policy-karmi.1"
    assert shadow["selection_probability"] == 1.0
    assert shadow["eligible_models"] == live["eligible_models"]

    with exchange["factory"]() as session:
        history = receiver.list_bundles(session)
    assert [(e["from"], e["to"]) for e in history[0]["events"]] == [
        (None, "received"), ("received", "staged"), ("staged", "shadow"),
    ]


def test_newer_shadow_bundle_retires_the_previous_one(exchange: dict[str, Any]) -> None:
    settings: Settings = exchange["settings"]
    with exchange["factory"]() as session:
        for version in ("policy-karmi.1", "policy-karmi.2"):
            path = make_karmi_bundle(exchange["tmp"] / "in", version,
                                     bias={"karmi/fake-economy": 1.0})
            receiver.receive_bundle(session, settings, path, **OPERATOR)
            receiver.transition(session, settings, version, receiver.STAGED, **OPERATOR)
            receiver.transition(session, settings, version, receiver.SHADOW, **OPERATOR)
        session.commit()
        states = {b["artifact_version"]: b["state"] for b in receiver.list_bundles(session)}
        assert states == {"policy-karmi.1": "retired", "policy-karmi.2": "shadow"}
        assert session.scalar(select(func.count()).select_from(PolicyBundleEvent)) == 7


def test_rejected_and_tampered_bundles_never_reach_shadow(exchange: dict[str, Any]) -> None:
    settings: Settings = exchange["settings"]
    tmp: Path = exchange["tmp"]
    foreign = make_karmi_bundle(tmp / "a", "policy-foreign.1", bias={"karmi/fake-economy": 1.0},
                                secret=bytes([7]) * 32)
    unknown = make_karmi_bundle(tmp / "b", "policy-unknown.1", bias={"openai/gpt-x": 1.0})
    reused = make_karmi_bundle(tmp / "c", "policy-karmi.1", bias={"karmi/fake-economy": 1.0})
    changed = make_karmi_bundle(tmp / "d", "policy-karmi.1", bias={"karmi/fake-economy": 2.0})
    with exchange["factory"]() as session:
        with pytest.raises(BundleRejected, match="untrusted"):
            receiver.receive_bundle(session, settings, foreign, **OPERATOR)
        with pytest.raises(BundleRejected, match="unknown models"):
            receiver.receive_bundle(session, settings, unknown, **OPERATOR)
        with pytest.raises(receiver.BundleStateError, match="actor and reason"):
            receiver.receive_bundle(session, settings, reused, actor=" ", reason="x")
        record = receiver.receive_bundle(session, settings, reused, **OPERATOR)
        session.commit()
        with pytest.raises(BundleRejected, match="different contents"):
            receiver.receive_bundle(session, settings, changed, **OPERATOR)
        stored = Path(record.storage_path) / "routing_policy.json"
        stored.chmod(0o644)
        stored.write_text(stored.read_text(encoding="utf-8").replace("1.0", "9.0", 1),
                          encoding="utf-8")
        with pytest.raises(BundleRejected, match="checksum mismatch"):
            receiver.transition(session, settings, "policy-karmi.1", receiver.STAGED, **OPERATOR)
        session.rollback()
        assert receiver.list_bundles(session)[0]["state"] == "received"


def test_broken_shadow_policy_cannot_fail_a_live_request(exchange: dict[str, Any]) -> None:
    settings: Settings = exchange["settings"]
    bundle = make_karmi_bundle(exchange["tmp"] / "in", "policy-karmi.1",
                               bias={"karmi/fake-economy": 1.0})
    with exchange["factory"]() as session:
        receiver.receive_bundle(session, settings, bundle, **OPERATOR)
        receiver.transition(session, settings, "policy-karmi.1", receiver.STAGED, **OPERATOR)
        receiver.transition(session, settings, "policy-karmi.1", receiver.SHADOW, **OPERATOR)
        session.commit()
    receiver._loaded.clear()
    settings.parakh_trusted_public_keys = []  # trust revoked: stored copy no longer verifies
    reply = _send(exchange, "msg-after-revoke")
    assert reply["route"] == "fake-economy"
    with exchange["factory"]() as session:
        decisions = list(session.scalars(select(RoutingDecision)))
    assert [d.shadow for d in decisions] == [False]


def test_signed_bundle_requiring_newer_karmi_is_rejected(exchange: dict[str, Any]) -> None:
    bundle = make_karmi_bundle(exchange["tmp"] / "in", "policy-future.1",
                               bias={"karmi/fake-economy": 1.0}, minimum_karmi_version="9.0.0")
    sign_directory(bundle)
    with exchange["factory"]() as session, pytest.raises(BundleRejected, match="too old"):
        receiver.receive_bundle(session, exchange["settings"], bundle, **OPERATOR)
