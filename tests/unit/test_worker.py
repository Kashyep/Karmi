from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from daily_agent.models import OutboxEvent, Reminder
from daily_agent.schemas import Outcome
from daily_agent.services import persist_completed_run
from daily_agent.worker import LEASE_SECONDS, MAX_ATTEMPTS, run_once
from tests.conftest import create_identity

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
AFTER_LEASE = timedelta(seconds=LEASE_SECONDS + 1)


def seed(test_context: dict[str, object]) -> None:
    """One queued outbox row, one due reminder, one future reminder."""
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _token = create_identity(session, settings, name="Worker")  # type: ignore[arg-type]
        persist_completed_run(
            session,
            account_id=account.id,
            user_id=user.id,
            logical_request_id="req-worker-1",
            response="hello",
            outcome=Outcome.ACCEPT,
        )
        for key, due in (("due-reminder", NOW - timedelta(minutes=1)), ("later-reminder", NOW + timedelta(hours=1))):
            session.add(
                Reminder(
                    account_id=account.id,
                    owner_user_id=user.id,
                    text=key,
                    due_at_utc=due,
                    timezone="Asia/Kolkata",
                    idempotency_key=key,
                )
            )
        session.commit()


def states(test_context: dict[str, object]) -> dict[str, tuple[str, int]]:
    with test_context["factory"]() as session:  # type: ignore[operator]
        out = {e.logical_key: (e.status, e.attempts) for e in session.scalars(select(OutboxEvent))}
        out |= {r.text: (r.state, r.attempts) for r in session.scalars(select(Reminder))}
        return out


def fail(_key: str, _payload: str) -> None:
    raise RuntimeError("adapter down")


def test_delivers_queued_and_due_rows_exactly_once(test_context: dict[str, object]) -> None:
    seed(test_context)
    factory = test_context["factory"]
    sent: list[str] = []

    def record(key: str, _payload: str) -> None:
        sent.append(key)

    assert run_once(factory, now=NOW, deliver=record) == 2  # type: ignore[arg-type]
    assert sent[0].startswith("response:") and sent[1].startswith("reminder:")
    assert run_once(factory, now=NOW, deliver=record) == 0  # type: ignore[arg-type]
    current = states(test_context)
    assert current["due-reminder"] == ("delivered", 1)
    assert current["later-reminder"] == ("scheduled", 0)
    assert run_once(factory, now=NOW + timedelta(hours=2), deliver=record) == 1  # type: ignore[arg-type]
    assert len(sent) == 3


def test_failed_delivery_is_retried_only_after_lease_expires(test_context: dict[str, object]) -> None:
    seed(test_context)
    factory = test_context["factory"]
    sent: list[str] = []
    assert run_once(factory, now=NOW, deliver=fail) == 0  # type: ignore[arg-type]
    assert states(test_context)["due-reminder"] == ("delivering", 1)
    # Still leased by the (crashed) first attempt: nobody may take it yet.
    assert run_once(factory, now=NOW + timedelta(seconds=LEASE_SECONDS - 1), deliver=lambda k, _p: sent.append(k)) == 0  # type: ignore[arg-type]
    assert run_once(factory, now=NOW + AFTER_LEASE, deliver=lambda k, _p: sent.append(k)) == 2  # type: ignore[arg-type]
    assert states(test_context)["due-reminder"] == ("delivered", 2)


def test_row_is_marked_failed_after_max_attempts(test_context: dict[str, object]) -> None:
    seed(test_context)
    factory = test_context["factory"]
    at = NOW
    for _ in range(MAX_ATTEMPTS):
        run_once(factory, now=at, deliver=fail)  # type: ignore[arg-type]
        at += AFTER_LEASE
    assert run_once(factory, now=at, deliver=lambda _k, _p: None) == 0  # type: ignore[arg-type]
    assert states(test_context)["due-reminder"] == ("failed", MAX_ATTEMPTS)


def test_stalled_worker_overtaken_after_lease_does_not_double_count(test_context: dict[str, object]) -> None:
    seed(test_context)
    factory = test_context["factory"]
    takeover: list[int] = []

    def stall_then_get_overtaken(_key: str, _payload: str) -> None:
        # While worker A is stuck on its first row, its lease expires and worker B
        # reclaims and delivers both rows. A must not count or re-mark them.
        if not takeover:
            takeover.append(run_once(factory, now=NOW + AFTER_LEASE, deliver=lambda _k, _p: None))  # type: ignore[arg-type]

    assert run_once(factory, now=NOW, deliver=stall_then_get_overtaken) == 0  # type: ignore[arg-type]
    assert takeover == [2]
    assert {state for state, _attempts in states(test_context).values() if state != "scheduled"} == {"delivered"}
