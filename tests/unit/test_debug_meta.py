"""Serving metadata: recorded for every reply, exposed only to principals flagged as testers."""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from daily_agent import HARNESS_VERSION
from daily_agent.api import create_app
from daily_agent.config import Settings, get_settings
from daily_agent.db import Base, get_session
from daily_agent.deps import gateway_dependency
from daily_agent.gateway.service import GatewayResult
from daily_agent.gateway.types import StreamChunk
from daily_agent.models import Run, User
from daily_agent.providers import ProviderCall
from daily_agent.schemas import Outcome
from daily_agent.services import served_debug
from tests.conftest import create_identity

IDEM_KEY = "debug-meta-idempotency-key"


def _call(**overrides: Any) -> ProviderCall:
    fields: dict[str, Any] = {
        "provider": "openrouter",
        "model_id": "vendor/requested:free",
        "operation": "generate",
        "input_tokens": 7,
        "output_tokens": 2,
        "cost_micro": 0,
        "measurement": "registry-free-model",
        "rate_version": "registry-x",
        "served_model": "vendor/served:free",
        "served_provider": None,
    }
    fields.update(overrides)
    return ProviderCall(**fields)


def test_served_debug_reads_the_accepted_generate_call_and_falls_back_to_gateway_provider() -> None:
    routing = _call(operation="classify", served_model="router/model")
    view = served_debug((routing, _call()), attempts=2, latency_ms=12.6)
    assert view.served_model == "vendor/served:free"
    assert view.served_provider == "openrouter"
    assert view.attempt_count == 2
    assert view.fallback_used is True
    assert view.latency_ms == 13
    assert (view.input_tokens, view.output_tokens) == (7, 2)
    assert view.harness_version == HARNESS_VERSION


def test_served_debug_without_a_provider_call_reports_nothing_served() -> None:
    view = served_debug((), attempts=0, latency_ms=None)
    assert view.served_model is None
    assert view.attempt_count == 0
    assert view.fallback_used is False
    assert view.latency_ms is None


class _ServingGateway:
    """Replies whose provider call reports a served model different from the requested one."""

    live = True

    def eligible_actions(self, plan: object) -> list[str]:
        return ["vendor/m:free"]

    def generate(self, **kwargs: object) -> GatewayResult:
        return GatewayResult(
            text="Hello there",
            calls=(_call(served_provider="Upstream"),),
            action="vendor/m:free",
            failed=False,
            attempts=1,
        )

    async def stream(self, **kwargs: object) -> Any:
        yield StreamChunk(text="Hello")
        yield StreamChunk(
            text="", finish_reason="stop", call=_call(served_provider="Upstream")
        )


def _app(tmp_path: Path, *, tester: bool, gateway: Any) -> tuple[TestClient, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / "debug_meta.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=f"sqlite+pysqlite:///{db_path}",
        auth_secret="test-secret-with-enough-entropy-1234",
    )
    with factory() as session:
        _account, user, token = create_identity(session, settings, name="Debug")
        user.tester = tester
        session.commit()

    app = create_app()

    def session_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[gateway_dependency] = lambda: gateway
    return TestClient(app), token


def test_message_debug_is_omitted_for_ordinary_principals(tmp_path: Path) -> None:
    client, token = _app(tmp_path / "plain", tester=False, gateway=_ServingGateway())
    response = client.post(
        "/v1/messages",
        json={"text": "hello there", "idempotency_key": IDEM_KEY},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert "debug" not in response.json()


def test_message_debug_is_returned_to_testers(tmp_path: Path) -> None:
    client, token = _app(tmp_path / "tester", tester=True, gateway=_ServingGateway())
    response = client.post(
        "/v1/messages",
        json={"text": "hello there", "idempotency_key": IDEM_KEY},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["debug"]["served_model"] == "vendor/served:free"
    assert body["debug"]["served_provider"] == "Upstream"
    assert body["debug"]["attempt_count"] == 1
    assert body["debug"]["harness_version"] == HARNESS_VERSION
    # The idempotent replay serves the same stored metadata.
    replay = client.post(
        "/v1/messages",
        json={"text": "hello there", "idempotency_key": IDEM_KEY},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replay.json()["debug"] == body["debug"]


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in raw.strip().split("\n\n"):
        name = None
        data: Any = None
        for line in block.strip().split("\n"):
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if name is not None:
            events.append({"event": name, "data": data})
    return events


def test_stream_run_finished_carries_debug_only_for_testers(tmp_path: Path) -> None:
    def finished_payload(tester: bool) -> dict[str, Any]:
        client, token = _app(tmp_path / str(tester), tester=tester, gateway=_ServingGateway())
        with client.stream(
            "POST",
            "/v1/chat/stream",
            json={"text": "hello there", "clientMessageId": IDEM_KEY},
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            raw = "".join(response.iter_text())
        events = [e for e in _parse_sse(raw) if e["event"] == "run.finished"]
        assert len(events) == 1, raw
        data: dict[str, Any] = events[0]["data"]
        return data

    plain = finished_payload(False)
    assert "debug" not in plain
    tester = finished_payload(True)
    assert tester["debug"]["served_provider"] == "Upstream"
    assert tester["debug"]["attempt_count"] == 1
    assert tester["debug"]["fallback_used"] is False
    assert tester["debug"]["input_tokens"] == 7


def test_persisted_run_records_the_serving_metadata(tmp_path: Path) -> None:
    client, token = _app(tmp_path / "persist", tester=False, gateway=_ServingGateway())
    response = client.post(
        "/v1/messages",
        json={"text": "hello there", "idempotency_key": IDEM_KEY},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'persist' / 'debug_meta.db'}")
    factory = sessionmaker(bind=engine)
    with factory() as session:
        run = session.scalar(select(Run))
        assert run is not None
        assert run.outcome in {Outcome.ACCEPT.value, Outcome.DEFERRED.value}
        assert run.harness_version == HARNESS_VERSION
        user = session.scalar(select(User))
        assert user is not None and user.tester is False
