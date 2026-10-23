from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from daily_agent.models import (
    Account,
    BudgetReservation,
    ChatMessage,
    Conversation,
    CostLedger,
    InboxEvent,
    OutboxEvent,
    ReservationStatus,
    RoutingRecord,
    Run,
    UsageWindow,
)
from daily_agent.retention import purge_expired
from daily_agent.services import reserve_budget, settle_budget
from tests.conftest import create_identity

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
requires_run_created_at = pytest.mark.skipif(
    not hasattr(Run, "created_at"), reason="Run.created_at lands with the runs timestamp migration"
)
# Tables whose purge does not depend on Run.created_at.
_NON_RUN_TABLES = (
    "inbox_events",
    "routing_records",
    "routing_decisions",
    "cost_ledger",
    "budget_reservations",
)


def _settings(test_context: dict[str, object], **updates: object):  # type: ignore[no-untyped-def]
    settings = test_context["settings"]
    return settings.model_copy(update=updates)  # type: ignore[attr-defined]


def _count(session, model) -> int:  # type: ignore[no-untyped-def]
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _routing_record(run_id: str, completed_at: datetime) -> RoutingRecord:
    return RoutingRecord(
        run_id=run_id,
        tier="economy",
        task_domain="general",
        routing_context="{}",
        attempts="[]",
        harness_version="h",
        prompt_version="p",
        policy_version="pol",
        feature_schema_version="f",
        executed_action="act",
        latency_ms=1.0,
        cost_micro=None,
        started_at=completed_at,
        completed_at=completed_at,
    )


def test_inbox_routing_and_batching_delete_only_expired_rows(
    test_context: dict[str, object],
) -> None:
    factory = test_context["factory"]
    settings = _settings(test_context, retention_batch_size=2)
    old = NOW - timedelta(days=45)
    fresh = NOW - timedelta(days=1)
    with factory() as session:  # type: ignore[operator]
        for i in range(5):
            session.add(
                InboxEvent(
                    channel="web",
                    source_event_id=f"old-{i}",
                    payload_hash="0" * 64,
                    accepted_at=old,
                )
            )
        for i in range(2):
            session.add(
                InboxEvent(
                    channel="web",
                    source_event_id=f"new-{i}",
                    payload_hash="0" * 64,
                    accepted_at=fresh,
                )
            )
        session.add(_routing_record("run-old", NOW - timedelta(days=200)))
        session.add(_routing_record("run-new", fresh))
        session.commit()

    deleted = purge_expired(factory, settings, now=NOW, only=_NON_RUN_TABLES)  # type: ignore[arg-type]

    assert deleted["inbox_events"] == 5
    assert deleted["routing_records"] == 1
    with factory() as session:  # type: ignore[operator]
        remaining = session.scalars(select(InboxEvent.source_event_id)).all()
        assert sorted(remaining) == ["new-0", "new-1"]
        assert session.scalars(select(RoutingRecord.run_id)).all() == ["run-new"]


def test_ledger_and_reservations_purge_only_final_expired_chain(
    test_context: dict[str, object],
) -> None:
    factory = test_context["factory"]
    settings = _settings(test_context, retention_batch_size=1)
    ancient = NOW - timedelta(days=500)
    with factory() as session:  # type: ignore[operator]
        account, _user, _token = create_identity(session, settings, name="A")  # type: ignore[arg-type]
        old_settled = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="old-settled",
            stage="execution",
            amount_micro=100,
        )
        settle_budget(session, old_settled, attempt_id="a:1", actual_micro=50)
        old_reserved = reserve_budget(
            session,
            settings=settings,  # type: ignore[arg-type]
            account_id=account.id,
            logical_request_id="old-reserved",
            stage="execution",
            amount_micro=100,
        )
        session.commit()
        old_settled.created_at = ancient
        old_reserved.created_at = ancient
        session.execute(
            CostLedger.__table__.update().values(created_at=ancient)  # type: ignore[attr-defined]
        )
        session.commit()
        settled_id = old_settled.id
        reserved_id = old_reserved.id
        messages_before = _count(session, ChatMessage)
        windows_before = _count(session, UsageWindow)

    deleted = purge_expired(factory, settings, now=NOW, only=_NON_RUN_TABLES)  # type: ignore[arg-type]

    assert deleted["cost_ledger"] == 1
    assert deleted["budget_reservations"] == 1
    with factory() as session:  # type: ignore[operator]
        assert session.get(BudgetReservation, settled_id) is None
        still_reserved = session.get(BudgetReservation, reserved_id)
        assert still_reserved is not None
        assert still_reserved.status == ReservationStatus.RESERVED
        assert _count(session, CostLedger) == 0
        assert _count(session, ChatMessage) == messages_before
        assert _count(session, UsageWindow) == windows_before
        assert _count(session, Account) >= 1


def test_protected_tables_are_never_purged(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = _settings(test_context)
    ancient = NOW - timedelta(days=3000)
    with factory() as session:  # type: ignore[operator]
        account, user, _token = create_identity(session, settings, name="P")  # type: ignore[arg-type]
        conversation = Conversation(
            account_id=account.id,
            user_id=user.id,
            title="keep me",
            created_at=ancient,
            updated_at=ancient,
        )
        session.add(conversation)
        session.flush()
        session.add(
            ChatMessage(
                conversation_id=conversation.id,
                account_id=account.id,
                role="user",
                status="completed",
                content="ancient message",
                created_at=ancient,
            )
        )
        session.commit()

    purge_expired(factory, settings, now=NOW, only=_NON_RUN_TABLES)  # type: ignore[arg-type]

    with factory() as session:  # type: ignore[operator]
        assert _count(session, Conversation) == 1
        assert _count(session, ChatMessage) == 1


@requires_run_created_at
def test_runs_and_outbox_purge_by_run_age_and_skip_active(
    test_context: dict[str, object],
) -> None:
    factory = test_context["factory"]
    settings = _settings(test_context, retention_batch_size=1)
    old = NOW - timedelta(days=200)
    with factory() as session:  # type: ignore[operator]
        account, user, _token = create_identity(session, settings, name="R")  # type: ignore[arg-type]

        def run(logical: str, status: str, created: datetime) -> Run:
            return Run(
                account_id=account.id,
                user_id=user.id,
                logical_request_id=logical,
                status=status,
                created_at=created,
            )

        done_old = run("done-old", "completed", old)
        active_old = run("active-old", "queued", old)
        done_new = run("done-new", "completed", NOW)
        session.add_all([done_old, active_old, done_new])
        session.flush()
        session.add(
            OutboxEvent(
                logical_key="k-old", run_id=done_old.id, payload="{}", status="sent"
            )
        )
        session.add(
            OutboxEvent(
                logical_key="k-queued", run_id=done_old.id, payload="{}", status="queued"
            )
        )
        session.commit()
        kept_id = active_old.id

    deleted = purge_expired(factory, settings, now=NOW, only=("outbox_events", "runs"))  # type: ignore[arg-type]

    assert deleted["outbox_events"] == 1
    assert deleted["runs"] == 1
    with factory() as session:  # type: ignore[operator]
        assert session.get(Run, kept_id) is not None
        assert _count(session, Run) == 2
        assert _count(session, OutboxEvent) == 1
