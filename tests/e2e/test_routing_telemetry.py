"""End-to-end: router + telemetry wired into /v1/messages (ADR-0003)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.config import Settings, get_settings
from daily_agent.models import (
    BudgetReservation,
    CostLedger,
    Note,
    PlatformBudget,
    Run,
    Subscription,
    TelemetryFeedback,
    TelemetryOutcomeSignal,
    TelemetryRouterDecision,
    TelemetryRun,
    TelemetryRunOutcome,
)
from daily_agent.policy_artifacts.schema import HARNESS_RECOVERY, ROUTING_POLICY
from daily_agent.policy_artifacts.store import PolicyStore
from daily_agent.providers import ProviderCall
from daily_agent.routing.registry import LOCAL_ROUTE, entitlement_map
from daily_agent.routing.runtime import RoutingRuntime
from daily_agent.telemetry import exporter, finalizer
from daily_agent.telemetry.collector import TelemetryCollector
from daily_agent.telemetry.events import TelemetryBatchV1
from tests.conftest import create_identity
from tests.support.policy_bundles import default_arms, generate_keypair, tamper_file, write_bundle

pytestmark = pytest.mark.e2e

PRIVATE_FIXTURE_TEXT = "my passport number is K1234567 and I live at 42 Hidden Lane"


def _client(ctx: dict[str, object]) -> TestClient:
    client = ctx["client"]
    assert isinstance(client, TestClient)
    return client


def _factory(ctx: dict[str, object]) -> sessionmaker[Session]:
    factory = ctx["factory"]
    assert isinstance(factory, sessionmaker)
    return factory


def _use_settings(ctx: dict[str, object], **changes: Any) -> Settings:
    base = ctx["settings"]
    assert isinstance(base, Settings)
    settings = base.model_copy(update={"router_reload_interval_seconds": 0.0, **changes})
    app: Any = ctx["app"]
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


def _simulate_live_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from daily_agent import providers, services

    # The router can exercise live-path accounting without authorizing SDK traffic.
    monkeypatch.setattr(providers, "LIVE_PROVIDER_SPEND_VERIFIED", True)
    monkeypatch.setattr(
        services,
        "score_notes_relevance",
        lambda _query, notes, **_kwargs: ([0.0] * len(notes), []),
    )


def _send_no_route(ctx: dict[str, object], token: str, text: str, key: str) -> TelemetryRun:
    """A no-route deferral is retryable: 503, nothing reserved, no Run under the key."""
    response = _client(ctx).post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": text, "idempotency_key": key},
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "NO_ELIGIBLE_ROUTE"
    assert int(response.headers["Retry-After"]) >= 1
    with _factory(ctx)() as session:
        assert session.scalar(select(Run).where(Run.logical_request_id == key)) is None
        assert session.scalar(
            select(BudgetReservation).where(BudgetReservation.logical_request_id == key)
        ) is None
    _flush(ctx)
    with _factory(ctx)() as session:
        (row,) = session.scalars(
            select(TelemetryRun)
            .where(TelemetryRun.status == "no_eligible_model")
            .order_by(TelemetryRun.completed_at.desc())
            .limit(1)
        ).all()
    return row


def _token(ctx: dict[str, object], name: str = "Asha") -> str:
    settings = ctx["settings"]
    assert isinstance(settings, Settings)
    with _factory(ctx)() as session:
        _account, _user, token = create_identity(session, settings, name=name)
    return token


def _send(ctx: dict[str, object], token: str, text: str, key: str) -> dict[str, Any]:
    response = _client(ctx).post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": text, "idempotency_key": key},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _flush(ctx: dict[str, object]) -> None:
    telemetry = ctx["telemetry"]
    assert isinstance(telemetry, TelemetryCollector)
    assert telemetry.flush(timeout=5.0)


def _decisions(ctx: dict[str, object], run_id: str) -> list[TelemetryRouterDecision]:
    with _factory(ctx)() as session:
        return list(
            session.scalars(
                select(TelemetryRouterDecision).where(TelemetryRouterDecision.run_id == run_id)
            )
        )


def _run(ctx: dict[str, object], run_id: str) -> TelemetryRun:
    with _factory(ctx)() as session:
        row = session.get(TelemetryRun, run_id)
    assert row is not None, "telemetry run row missing"
    return row


def _bundle_settings(
    ctx: dict[str, object], tmp_path: Path, *, mode: str, version: str = "lin-1", **bundle: Any
) -> tuple[Settings, PolicyStore, Path]:
    private_key, public_key = generate_keypair()
    settings = _use_settings(ctx, router_mode=mode, router_policy_public_key=public_key)
    source = write_bundle(tmp_path / f"src-{version}", private_key=private_key, version=version, **bundle)
    store = PolicyStore(
        settings.router_policy_dir,
        public_key_b64=public_key,
        known_models=entitlement_map(),
        karmi_version="0.1.0",
    )
    store.install(source)
    return settings, store, source


def test_static_route_is_unchanged_and_logs_its_propensity(
    test_context: dict[str, object],
) -> None:
    token = _token(test_context)
    body = _send(test_context, token, PRIVATE_FIXTURE_TEXT, "static-parity-1")
    assert body["route"] == LOCAL_ROUTE
    assert body["outcome"] == "ACCEPT"
    assert body["response"] == f"Draft ready: {PRIVATE_FIXTURE_TEXT}"

    _flush(test_context)
    run = _run(test_context, body["run_id"])
    assert run.policy_version == "static-v1"
    assert run.tier == "ananta"
    (decision,) = _decisions(test_context, body["run_id"])
    assert decision.shadow is False
    assert decision.algorithm == "static"
    assert decision.selected_model == LOCAL_ROUTE
    assert decision.selection_probability == 1.0

    # No raw request text is stored anywhere in the telemetry row.
    with _factory(test_context)() as session:
        stored = session.get(TelemetryRun, body["run_id"])
        assert stored is not None
        dumped = json.dumps(
            {c.name: str(getattr(stored, c.name)) for c in TelemetryRun.__table__.columns}
        )
    assert "K1234567" not in dumped and "Hidden Lane" not in dumped


def test_shadow_bundle_logs_a_shadow_decision_without_changing_the_live_route(
    test_context: dict[str, object], tmp_path: Path
) -> None:
    _settings, store, _source = _bundle_settings(test_context, tmp_path, mode="shadow")
    store.set_shadow("lin-1")
    token = _token(test_context)

    body = _send(test_context, token, "draft an email to my landlord", "shadow-1")
    assert body["route"] == LOCAL_ROUTE

    _flush(test_context)
    decisions = {row.shadow: row for row in _decisions(test_context, body["run_id"])}
    assert decisions[False].policy_version == "static-v1"
    assert decisions[True].policy_version == "lin-1"
    assert decisions[True].algorithm == "linucb"
    assert decisions[True].agreed_with_live is (decisions[True].selected_model == LOCAL_ROUTE)
    assert _run(test_context, body["run_id"]).shadow_error is None


def test_tampered_active_bundle_falls_back_to_static_with_a_reason(
    test_context: dict[str, object], tmp_path: Path
) -> None:
    settings, store, _source = _bundle_settings(test_context, tmp_path, mode="bandit")
    store.promote("lin-1")
    token = _token(test_context)
    trusted = _send(test_context, token, "what is on my list", "tampered-control-1")
    _flush(test_context)
    assert _run(test_context, trusted["run_id"]).policy_version == "lin-1"

    # Tamper a signed file after install. Serving keeps the bytes it verified in memory;
    # the next state change re-verifies from disk and must reject the tampered bundle.
    bundle_dir = settings.router_policy_dir / "bundles" / "lin-1"
    tampered = json.loads((bundle_dir / ROUTING_POLICY).read_text(encoding="utf-8"))
    tampered["alpha"] = 0.0
    tamper_file(bundle_dir, ROUTING_POLICY, json.dumps(tampered))
    store.set_shadow(None)

    body = _send(test_context, token, "what is on my list", "tampered-1")
    assert body["route"] == LOCAL_ROUTE
    _flush(test_context)
    run = _run(test_context, body["run_id"])
    assert run.policy_version == "static-v1"
    assert run.live_fallback_reason == "bundle_rejected_checksum_mismatch"


def test_routing_crash_serves_the_baseline_route(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(self: RoutingRuntime, **_kwargs: object) -> None:
        raise RuntimeError("router bug")

    monkeypatch.setattr(RoutingRuntime, "route", explode)
    token = _token(test_context)
    body = _send(test_context, token, "hello there", "router-crash-1")
    assert body["route"] == LOCAL_ROUTE and body["outcome"] == "ACCEPT"

    _flush(test_context)
    run = _run(test_context, body["run_id"])
    assert run.live_fallback_reason == "routing_error"
    (decision,) = _decisions(test_context, body["run_id"])
    assert decision.selection_probability == 1.0 and decision.algorithm == "static"


def test_feature_extractor_failure_keeps_static_eligibility(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from daily_agent import api

    def explode(**_kwargs: object) -> None:
        raise RuntimeError("feature extraction failed")

    monkeypatch.setattr(api, "build_routing_context", explode)
    token = _token(test_context)
    body = _send(test_context, token, "draft something", "feature-failure-1")
    assert body["outcome"] == "ACCEPT" and body["route"] == LOCAL_ROUTE
    _flush(test_context)
    run = _run(test_context, body["run_id"])
    assert run.live_fallback_reason == "routing_error"
    assert _decisions(test_context, body["run_id"])[0].selection_probability == 1.0


def test_oversized_message_is_rejected_before_budget_or_provider(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from daily_agent import services

    _use_settings(test_context, live_models_enabled=True)
    _simulate_live_provider(monkeypatch)
    monkeypatch.setattr(
        services,
        "score_notes_relevance",
        lambda *_args, **_kw: pytest.fail("provider scoring must not run"),
    )
    settings = test_context["settings"]
    assert isinstance(settings, Settings)
    with _factory(test_context)() as session:
        account, user, token = create_identity(session, settings, name="Oversize")
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == account.id)
        )
        assert subscription is not None
        subscription.plan_id = "part"
        session.add(Note(account_id=account.id, owner_user_id=user.id, content="saved note"))
        session.commit()
    response = _client(test_context).post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "x" * 20_001, "idempotency_key": "oversized-before-provider"},
    )
    assert response.status_code == 413
    with _factory(test_context)() as session:
        assert session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.logical_request_id == "oversized-before-provider"
            )
        ) is None


def test_live_setting_cannot_authorize_unverified_provider_spending(
    test_context: dict[str, object]
) -> None:
    _use_settings(
        test_context, live_models_enabled=True, router_disabled_models=[LOCAL_ROUTE]
    )
    run = _send_no_route(
        test_context, _token(test_context), "draft a short note", "unverified-live-1"
    )
    rejections = json.loads(run.eligibility_rejections_json)
    assert "provider_spend_unverified" in rejections["typesafe-system-one"]


def test_live_failure_keeps_provider_expense_and_replays_executed_route(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A measured paid call is never dropped just because local heuristics answered."""
    from daily_agent import services

    _use_settings(test_context, live_models_enabled=True)
    _simulate_live_provider(monkeypatch)
    call = ProviderCall("typesafe", "jev-latest", "choice", 50, 5, 300, "measured", "fixture")
    monkeypatch.setattr(services, "classify_intent", lambda *_args, **_kw: (None, [call]))
    token = _token(test_context)
    body = _send(test_context, token, "draft a short note", "live-fallback-1")
    assert body["route"] == LOCAL_ROUTE
    replay = _send(test_context, token, "draft a short note", "live-fallback-1")
    assert replay == body
    with _factory(test_context)() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.logical_request_id == "live-fallback-1"
            )
        )
        assert reservation is not None and reservation.actual_micro == 300
        ledger = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
    assert [(entry.provider, entry.cost_micro) for entry in ledger] == [("typesafe", 300)]
    _flush(test_context)
    (decision,) = _decisions(test_context, body["run_id"])
    assert decision.selected_model == "typesafe-system-one"
    assert decision.selection_probability == 1.0


def test_provider_fault_defers_without_customer_charge_but_keeps_expense(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from daily_agent import services

    _simulate_live_provider(monkeypatch)
    arms = default_arms()
    arms["typesafe-system-one"]["theta"][0] = 10.0

    def disable_local_recovery(docs: dict[str, Any]) -> None:
        docs[HARNESS_RECOVERY]["fallback_to_local"] = False

    settings, store, _ = _bundle_settings(
        test_context,
        tmp_path,
        mode="bandit",
        harness=True,
        arms=arms,
        mutate=disable_local_recovery,
    )
    _use_settings(
        test_context,
        router_mode="bandit",
        router_policy_public_key=settings.router_policy_public_key,
        live_models_enabled=True,
    )
    store.promote("lin-1")
    call = ProviderCall("typesafe", "jev-latest", "choice", 50, 5, 300, "measured", "fixture")
    monkeypatch.setattr(services, "classify_intent", lambda *_args, **_kw: (None, [call]))
    body = _send(test_context, _token(test_context), "draft a short note", "deferred-provider-1")
    assert body["outcome"] == "DEFERRED" and body["route"] == "typesafe-system-one"
    with _factory(test_context)() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.logical_request_id == "deferred-provider-1"
            )
        )
        assert reservation is not None and reservation.status == "released"
        platform = session.scalar(select(PlatformBudget))
        assert platform is not None and platform.settled_micro == 300
        ledger = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
    assert [(entry.provider, entry.cost_micro) for entry in ledger] == [("typesafe", 300)]


def test_unmeasured_provider_attempt_is_not_treated_as_free(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from daily_agent import services

    _use_settings(test_context, live_models_enabled=True)
    _simulate_live_provider(monkeypatch)
    monkeypatch.setattr(services, "classify_intent", lambda *_args, **_kw: (None, []))
    token = _token(test_context)
    body = _send(test_context, token, "draft a short note", "unknown-cost-1")
    assert body["route"] == LOCAL_ROUTE
    with _factory(test_context)() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.logical_request_id == "unknown-cost-1"
            )
        )
        assert reservation is not None and reservation.actual_micro is None
        assert reservation.status == "unknown"
        ledger = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
    assert len(ledger) == 1
    assert ledger[0].provider == "typesafe" and ledger[0].measurement == "unknown"
    assert ledger[0].cost_micro is None


def test_failed_tool_preserves_paid_provider_expense_without_customer_charge(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from daily_agent import api, services

    _use_settings(test_context, live_models_enabled=True)
    _simulate_live_provider(monkeypatch)
    call = ProviderCall("typesafe", "jev-latest", "choice", 50, 5, 300, "measured", "fixture")
    monkeypatch.setattr(
        services, "classify_intent", lambda *_args, **_kw: ("store_memory", [call])
    )
    token = _token(test_context)

    def failing_intent(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("tool failed")

    with monkeypatch.context() as transient:
        transient.setattr(api, "_apply_intent", failing_intent)
        with pytest.raises(RuntimeError, match="tool failed"):
            _send(test_context, token, "save this synthetic note", "failed-tool-1")

    with _factory(test_context)() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.logical_request_id == "failed-tool-1"
            )
        )
        assert reservation is not None and reservation.status == "released"
        platform = session.scalar(select(PlatformBudget))
        assert platform is not None and platform.settled_micro == 300
        costs = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
    assert [(entry.provider, entry.cost_micro) for entry in costs] == [("typesafe", 300)]
    _flush(test_context)
    with _factory(test_context)() as session:
        failed_run = session.scalar(
            select(TelemetryRun).where(TelemetryRun.status == "failed")
        )
        assert failed_run is not None
        failed_outcome = session.get(TelemetryRunOutcome, failed_run.run_id)
        assert failed_outcome is not None and failed_outcome.final_cost_micro == 300

    # Released customer reservation can be retried; the first provider expense persists.
    retry = _send(test_context, token, "save this synthetic note", "failed-tool-1")
    assert retry["outcome"] == "ACCEPT"
    with _factory(test_context)() as session:
        reservation = session.scalar(
            select(BudgetReservation).where(
                BudgetReservation.logical_request_id == "failed-tool-1"
            )
        )
        assert reservation is not None and reservation.status == "settled"
        costs = session.scalars(
            select(CostLedger).where(CostLedger.reservation_id == reservation.id)
        ).all()
    assert len(costs) == 2
    assert sum(entry.cost_micro or 0 for entry in costs) == 600


def test_routing_error_cannot_override_operator_model_disable(
    test_context: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(self: RoutingRuntime, **_kwargs: object) -> None:
        raise RuntimeError("router bug")

    _use_settings(test_context, router_disabled_models=[LOCAL_ROUTE])
    monkeypatch.setattr(RoutingRuntime, "route", explode)
    token = _token(test_context)
    run = _send_no_route(test_context, token, "hello", "disabled-on-error-1")
    assert json.loads(run.eligibility_rejections_json)[LOCAL_ROUTE] == ["model_disabled"]


def test_telemetry_database_outage_does_not_fail_requests(
    test_context: dict[str, object], tmp_path: Path
) -> None:
    def broken_factory() -> Session:
        raise RuntimeError("telemetry database unavailable")

    spool = tmp_path / "outage-spool.jsonl"
    broken = TelemetryCollector(
        session_factory=broken_factory,
        queue_size=10,
        batch_size=5,
        flush_interval_seconds=0.05,
        spool_path=spool,
        attribution_window_seconds=60,
    )
    app: Any = test_context["app"]
    original = app.state.telemetry
    app.state.telemetry = broken
    broken.start()
    try:
        token = _token(test_context)
        for index in range(3):
            body = _send(test_context, token, f"note number {index}", f"outage-{index}")
            assert body["outcome"] == "ACCEPT"
        broken.flush(timeout=2.0)
    finally:
        broken.stop(timeout=2.0)
        app.state.telemetry = original
    # Mandatory run records were spooled, not lost.
    assert spool.exists() and spool.read_text(encoding="utf-8").count('"kind":"run"') == 3


def test_no_eligible_model_defers_retryably_without_reserving_budget(
    test_context: dict[str, object],
) -> None:
    _use_settings(test_context, router_disabled_models=[LOCAL_ROUTE])
    token = _token(test_context)
    run = _send_no_route(test_context, token, "hello", "no-route-1")
    assert json.loads(run.eligibility_rejections_json)[LOCAL_ROUTE] == ["model_disabled"]

    # Once the operator re-enables the route, the same idempotency key is served.
    _use_settings(test_context, router_disabled_models=[])
    body = _send(test_context, token, "hello", "no-route-1")
    assert body["route"] == LOCAL_ROUTE and body["outcome"] != "DEFERRED"


def test_guardrail_breach_rolls_back_the_live_bundle(
    test_context: dict[str, object], tmp_path: Path
) -> None:
    settings, store, _source = _bundle_settings(test_context, tmp_path, mode="bandit")
    store.promote("lin-1")
    _use_settings(
        test_context,
        router_mode="bandit",
        router_policy_public_key=settings.router_policy_public_key,
        router_guardrail_min_samples=2,
        router_guardrail_window=2,
        # The local route costs 100 micro per request: any learned policy breaches this.
        router_guardrail_max_mean_cost_micro=1,
    )
    token = _token(test_context)
    first = _send(test_context, token, "draft a reply", "guardrail-1")
    second = _send(test_context, token, "draft a reply", "guardrail-2")
    third = _send(test_context, token, "draft a reply", "guardrail-3")

    assert store.read_state().active is None
    _flush(test_context)
    assert _run(test_context, first["run_id"]).policy_version == "lin-1"
    assert _run(test_context, second["run_id"]).policy_version == "lin-1"
    assert _run(test_context, third["run_id"]).policy_version == "static-v1"


def test_feedback_is_scoped_to_the_callers_run_and_stores_no_text(
    test_context: dict[str, object],
) -> None:
    owner = _token(test_context, "Owner")
    stranger = _token(test_context, "Stranger")
    body = _send(test_context, owner, "draft a note to the school", "feedback-1")
    url = f"/v1/runs/{body['run_id']}/feedback"
    correction = {"feedback_type": "correction", "corrected_text": "Draft a letter to school"}

    denied = _client(test_context).post(
        url, headers={"Authorization": f"Bearer {stranger}"}, json=correction
    )
    assert denied.status_code == 404

    accepted = _client(test_context).post(
        url, headers={"Authorization": f"Bearer {owner}"}, json=correction
    )
    assert accepted.status_code == 202

    _flush(test_context)
    with _factory(test_context)() as session:
        (row,) = session.scalars(
            select(TelemetryFeedback).where(TelemetryFeedback.run_id == body["run_id"])
        ).all()
    assert row.feedback_type == "correction"
    assert row.sanitized_corrected_value is None
    assert row.correction_distance is not None and 0.0 < row.correction_distance < 1.0


def test_repeated_feedback_cannot_multiply_strong_training_signals(
    test_context: dict[str, object],
) -> None:
    owner = _token(test_context, "Owner")
    body = _send(test_context, owner, "draft a note to the school", "feedback-flood-1")
    url = f"/v1/runs/{body['run_id']}/feedback"
    headers = {"Authorization": f"Bearer {owner}"}
    ids: set[str] = set()
    accepted: list[bool] = []
    # No flush between posts: repeats still in flight must not be emitted again.
    for kind in ("reject", "reject", "reject", "accept", "accept"):
        response = _client(test_context).post(url, headers=headers, json={"feedback_type": kind})
        assert response.status_code == 202
        ids.add(response.json()["feedback_id"])
        accepted.append(response.json()["accepted"])
    _flush(test_context)
    repeat = _client(test_context).post(url, headers=headers, json={"feedback_type": "reject"})
    accepted.append(repeat.json()["accepted"])

    assert len(ids) == 2
    assert accepted == [True, False, False, True, False, False]
    with _factory(test_context)() as session:
        feedback = session.scalars(
            select(TelemetryFeedback).where(TelemetryFeedback.run_id == body["run_id"])
        ).all()
        strong = session.scalars(
            select(TelemetryOutcomeSignal).where(
                TelemetryOutcomeSignal.run_id == body["run_id"],
                TelemetryOutcomeSignal.strength == "strong",
            )
        ).all()
    assert sorted(row.feedback_type for row in feedback) == ["accept", "reject"]
    assert sorted(row.signal_type for row in strong) == ["accept", "reject"]



def test_admin_observes_routing_and_telemetry_without_customer_access(
    test_context: dict[str, object],
) -> None:
    customer = _token(test_context, "Customer")
    # This identity must actually hold the admin role; a display name cannot grant it.
    settings = test_context["settings"]
    assert isinstance(settings, Settings)
    with _factory(test_context)() as session:
        _account, _user, admin = create_identity(
            session, settings, name="RealAdmin", role="admin"
        )
    client = _client(test_context)
    _send(test_context, customer, "hello", "admin-observes-1")
    for path in ("/admin/routing", "/admin/telemetry"):
        assert client.get(path, headers={"Authorization": f"Bearer {customer}"}).status_code == 403
        response = client.get(path, headers={"Authorization": f"Bearer {admin}"})
        assert response.status_code == 200
        assert "auth_secret" not in response.text
    routing = client.get("/admin/routing", headers={"Authorization": f"Bearer {admin}"}).json()
    assert "runtime" in routing and "metrics" in routing
    telemetry = client.get("/admin/telemetry", headers={"Authorization": f"Bearer {admin}"}).json()
    assert telemetry["enabled"] is True


def test_finalised_runs_export_as_a_valid_telemetry_batch(
    test_context: dict[str, object], tmp_path: Path
) -> None:
    token = _token(test_context)
    run_ids = [
        _send(test_context, token, PRIVATE_FIXTURE_TEXT, f"export-{index}")["run_id"]
        for index in range(2)
    ]
    _flush(test_context)
    later = datetime.now(UTC) + timedelta(days=2)
    with _factory(test_context)() as session:
        for run_id in run_ids:
            assert finalizer.finalize_run(session, run_id, now=later)
        session.commit()
        result = exporter.export_batch(
            session, out_dir=tmp_path / "exports", producer_version="0.1.0", now=later
        )
        session.commit()
    assert result is not None and result.run_count == 2

    raw = result.path.read_text(encoding="utf-8")
    batch = TelemetryBatchV1.model_validate_json(raw)
    assert sorted(run.run_id for run in batch.runs) == sorted(run_ids)
    for run in batch.runs:
        live = [d for d in run.decisions if not d.shadow]
        assert len(live) == 1 and live[0].selection_probability == 1.0
        assert run.outcome.finalized_at is not None
    assert "K1234567" not in raw and "Hidden Lane" not in raw and "request_fingerprint" not in raw
    with _factory(test_context)() as session:
        outcome = session.get(TelemetryRunOutcome, run_ids[0])
        assert outcome is not None and outcome.finalized_at is not None
