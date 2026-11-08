"""Optional Idempotency-Key header on continue/regenerate: a sequential repeat replays its run."""

from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from daily_agent.models import ChatMessage
from daily_agent.streaming.registry import get_stream_registry
from tests.unit.test_stream_routes import _parse_sse, _setup_app
from tests.unit.test_stream_scale import _first_chat, _reservation_count


def _started(resp: Any) -> dict[str, Any]:
    assert resp.status_code == 200, resp.text
    return next(e for e in _parse_sse(resp.text) if e["event"] == "run.started")["data"]


def _assistant_count(factory: Any, parent_id: str) -> int:
    with factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(
                    ChatMessage.parent_message_id == parent_id,
                    ChatMessage.role == "assistant",
                )
            )
            or 0
        )


def test_regenerate_same_key_replays_completed_run(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, account_id, _ = _setup_app(tmp_path)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "regen-key-0001"}
    started = _first_chat(client, {"Authorization": f"Bearer {token}"}, "client-msg-idem-regen")
    assistant_id = started["assistant_message_id"]
    user_id = started["user_message_id"]

    first = _started(client.post(f"/v1/messages/{assistant_id}/regenerate", headers=headers))
    reservations = _reservation_count(factory, account_id)
    variants = _assistant_count(factory, user_id)

    # The first run has completed; a sequential repeat must replay it without new work.
    get_stream_registry().clear()
    second = _started(client.post(f"/v1/messages/{assistant_id}/regenerate", headers=headers))
    assert second["run_id"] == first["run_id"]
    assert _reservation_count(factory, account_id) == reservations
    assert _assistant_count(factory, user_id) == variants


def test_regenerate_different_keys_make_separate_variants(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, _account_id, _ = _setup_app(tmp_path)
    auth = {"Authorization": f"Bearer {token}"}
    started = _first_chat(client, auth, "client-msg-idem-regen-two")
    assistant_id = started["assistant_message_id"]
    user_id = started["user_message_id"]

    a = _started(
        client.post(
            f"/v1/messages/{assistant_id}/regenerate",
            headers={**auth, "Idempotency-Key": "regen-key-000A"},
        )
    )
    b = _started(
        client.post(
            f"/v1/messages/{assistant_id}/regenerate",
            headers={**auth, "Idempotency-Key": "regen-key-000B"},
        )
    )
    assert a["run_id"] != b["run_id"]
    assert _assistant_count(factory, user_id) == 3  # original + two variants


def test_continue_same_key_replays_completed_run(tmp_path: Path) -> None:
    get_stream_registry().clear()
    client, factory, token, account_id, _ = _setup_app(tmp_path)
    auth = {"Authorization": f"Bearer {token}"}
    started = _first_chat(client, auth, "client-msg-idem-cont")
    assistant_id = started["assistant_message_id"]
    # Make the completed reply continuable (as if it had hit the length limit).
    with factory() as session:
        msg = session.get(ChatMessage, assistant_id)
        assert msg is not None
        msg.finish_reason = "length"
        session.commit()

    headers = {**auth, "Idempotency-Key": "cont-key-0001"}
    first = _started(client.post(f"/v1/messages/{assistant_id}/continue", headers=headers))
    reservations = _reservation_count(factory, account_id)

    get_stream_registry().clear()
    second = _started(client.post(f"/v1/messages/{assistant_id}/continue", headers=headers))
    assert second["run_id"] == first["run_id"]
    assert _reservation_count(factory, account_id) == reservations
