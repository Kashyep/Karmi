import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daily_agent.config import Settings, get_settings
from daily_agent.db import create_schema, get_session
from daily_agent.harness.versioning import BUILTIN_HARNESS
from daily_agent.models import (
    Account,
    BillingEvent,
    BudgetReservation,
    CostLedger,
    Note,
    OutboxEvent,
    Reminder,
    Run,
    RunStatus,
    Subscription,
    Task,
    UsagePeriod,
    UsageWindow,
    User,
)
from daily_agent.observability import METRICS
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.policy_artifacts.schema import HarnessBundleV1
from daily_agent.routing.features import build_routing_context
from daily_agent.routing.models import (
    NoEligibleModel,
    RoutingContext,
    RoutingDecision,
    RoutingOutcome,
)
from daily_agent.routing.registry import LIVE_ROUTE, LOCAL_PROVIDER
from daily_agent.routing.runtime import RoutingRuntime
from daily_agent.schemas import (
    ARMORY_TIERS,
    ActiveThemeUpdate,
    ArmoryView,
    FeedbackCreate,
    MessageCreate,
    MessageView,
    NoteCreate,
    NoteView,
    Outcome,
    ReminderCreate,
    TaskCreate,
    TaskView,
    UsageView,
)
from daily_agent.security import (
    Principal,
    issue_development_token,
    require_admin,
    require_principal,
    verify_event_signature,
    verify_hmac,
)
from daily_agent.services import (
    AttemptOutcome,
    BudgetDenied,
    IdempotencyConflict,
    ReservationInFlight,
    accept_internal_event,
    accounted_provider_calls,
    build_note_context,
    create_task_idempotent,
    current_period_key,
    current_window_key,
    estimate_request_cost_micro,
    fake_generate,
    measured_cost_micro,
    persist_completed_run,
    plan_policy,
    policy_for,
    release_budget,
    release_failed_execution,
    reserve_budget,
    scoped_note_query,
    scoped_task_query,
    seed_development_identity,
    settle_budget,
    subscription_period,
    sync_account_progression,
    sync_theme_progression,
)
from daily_agent.telemetry.collector import NullCollector, TelemetrySink
from daily_agent.telemetry.events import RunStatus as TelemetryRunStatus
from daily_agent.telemetry.events import SignalRecord, SignalSource, SignalStrength, SignalType
from daily_agent.telemetry.pseudonym import actor_id, request_fingerprint, telemetry_key
from daily_agent.telemetry.recorder import (
    ToolObservation,
    build_feedback_record,
    build_run_record,
)
from daily_agent.web import build_manifest, render_shell
from daily_agent.wiring import build_routing_runtime, build_telemetry

logger = logging.getLogger(__name__)

# Tool actions performed by _apply_intent, keyed by the validated intent label.
_INTENT_TOOLS = {"store_memory": "memory.store", "create_task": "tasks.create"}
NO_ROUTE_RESPONSE = (
    "No eligible route is available for this request right now. "
    "Nothing was charged; please try again later."
)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = app.dependency_overrides.get(get_settings, get_settings)()
        if settings.is_development:
            create_schema()
        # Tests (and embedders) may pre-install components on app.state before startup.
        if app.state.telemetry is None:
            app.state.telemetry = build_telemetry(settings)
        if app.state.routing is None:
            app.state.routing = build_routing_runtime(settings)
        app.state.routing.set_ops_sink(app.state.telemetry.emit)
        app.state.telemetry.start()
        try:
            yield
        finally:
            app.state.telemetry.stop()

    app = FastAPI(title="Daily Agent", version="0.1.0", lifespan=lifespan)
    app.state.telemetry = None
    app.state.routing = None

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/ready")
    def ready(session: Session = Depends(get_session)) -> dict[str, object]:
        session.execute(select(1))
        settings = get_settings()
        return {
            "status": "ready",
            "database": "ok",
            "live_models": settings.live_models_enabled,
            "paid_checkout": settings.paid_checkout_enabled,
            "whatsapp": "policy_disabled",
        }

    @app.post("/dev/token")
    def development_token(
        role: str = "customer",
        session: Session = Depends(get_session), settings: Settings = Depends(get_settings)
    ) -> dict[str, str]:
        if not settings.allow_development_auth or not settings.is_development:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if role not in {"customer", "admin"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        user = seed_development_identity(session, role=role)
        return {"token": issue_development_token(user, settings), "user_id": user.id}

    @app.get("/admin/overview")
    def admin_overview(
        _admin: Principal = Depends(require_admin),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        statuses = session.execute(select(Run.status, func.count()).group_by(Run.status)).all()
        return {
            "customers": session.scalar(select(func.count()).select_from(Account)) or 0,
            "runs_by_status": {str(run_status): count for run_status, count in statuses},
            "open_reservations": session.scalar(
                select(func.count())
                .select_from(BudgetReservation)
                .where(BudgetReservation.status == "reserved")
            )
            or 0,
            "live_models": settings.live_models_enabled,
            "whatsapp": "policy_disabled",
            "raw_message_access": "not_available",
        }

    @app.get("/admin/runs")
    def admin_runs(
        _admin: Principal = Depends(require_admin),
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        runs = session.scalars(select(Run).order_by(Run.id.desc()).limit(100)).all()
        return [
            {
                "run_id": run.id,
                "status": run.status,
                "outcome": run.outcome,
                "account_ref": hashlib.sha256(run.account_id.encode()).hexdigest()[:12],
                "response": "redacted",
            }
            for run in runs
        ]

    @app.get("/admin/routing")
    def admin_routing(
        request: Request,
        _admin: Principal = Depends(require_admin),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        return {
            "runtime": _routing_runtime(request, settings).status(settings),
            "metrics": METRICS.snapshot(),
        }

    @app.get("/admin/telemetry")
    def admin_telemetry(
        request: Request, _admin: Principal = Depends(require_admin)
    ) -> dict[str, object]:
        return _telemetry(request).health()

    @app.get("/v1/usage", response_model=UsageView)
    def usage(
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> UsageView:
        # Read-only: a GET must not create subscriptions or budget rows. Missing
        # rows simply mean the account has not consumed anything this window.
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == principal.account_id)
        )
        policy = plan_policy(subscription)
        day_key, day_reset = current_window_key()
        now = datetime.now(UTC)
        window = session.scalar(
            select(UsageWindow).where(
                UsageWindow.account_id == principal.account_id,
                UsageWindow.window_key == day_key,
            )
        )
        period = session.scalars(
            select(UsagePeriod)
            .where(UsagePeriod.account_id == principal.account_id, UsagePeriod.reset_at > now)
            .order_by(UsagePeriod.reset_at)
        ).first()
        if period is not None:
            period_reset = period.reset_at
        elif subscription is not None:
            _key, period_reset = subscription_period(subscription.period_anchor, now)
        else:
            _key, period_reset = current_period_key(now)
        return UsageView(
            plan_id=policy.plan_id,
            plan_label=policy.display_name,
            everyday_used=window.everyday_used if window else 0,
            everyday_limit=policy.everyday_limit,
            reserved_micro=period.reserved_micro if period else 0,
            settled_micro=period.settled_micro if period else 0,
            spend_limit_micro=period.spend_limit_micro if period else policy.period_cost_cap_micro,
            reset_at=window.reset_at if window else day_reset,
            period_reset_at=period.reset_at if period else period_reset,
            policy_version=subscription.policy_version if subscription else "synthetic-dev-v1",
        )

    @app.get("/v1/armory", response_model=ArmoryView)
    def get_armory(
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> ArmoryView:
        user = session.get(User, principal.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        prev_unlocked = user.unlocked_tier
        prev_theme = user.active_theme
        sync_theme_progression(session, user)
        if user.unlocked_tier != prev_unlocked or user.active_theme != prev_theme:
            session.commit()
        return ArmoryView(
            unlocked_tier=user.unlocked_tier,
            active_theme=user.active_theme,
            tiers=list(ARMORY_TIERS),
        )

    @app.put("/v1/armory/active-theme", response_model=ArmoryView)
    def update_active_theme(
        body: ActiveThemeUpdate,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> ArmoryView:
        user = session.get(User, principal.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        sync_theme_progression(session, user)
        if body.active_theme > user.unlocked_tier:
            locked_tier = user.unlocked_tier
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "TIER_LOCKED", "unlocked_tier": locked_tier},
            )
        user.active_theme = body.active_theme
        session.commit()
        return ArmoryView(
            unlocked_tier=user.unlocked_tier,
            active_theme=user.active_theme,
            tiers=list(ARMORY_TIERS),
        )

    @app.post("/v1/notes", response_model=NoteView)
    def create_note(
        body: NoteCreate,
        response: Response,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> NoteView:
        def replay() -> NoteView | None:
            """The earlier note for this idempotency key, or 409 if the payload differs."""
            existing = session.scalar(
                select(Note).where(
                    Note.account_id == principal.account_id,
                    Note.idempotency_key == body.idempotency_key,
                )
            )
            if existing is None:
                return None
            if existing.content != body.content or existing.owner_user_id != principal.user_id:
                raise _idempotency_conflict() from None
            response.status_code = status.HTTP_200_OK
            return NoteView(id=existing.id, content=existing.content, version=existing.version)

        if body.idempotency_key is not None and (earlier := replay()) is not None:
            return earlier
        note = Note(
            account_id=principal.account_id,
            owner_user_id=principal.user_id,
            content=body.content,
            idempotency_key=body.idempotency_key,
        )
        session.add(note)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            # Lost a concurrent insert race on the same key: replay the winner.
            if body.idempotency_key is None or (earlier := replay()) is None:
                raise
            return earlier
        response.status_code = status.HTTP_201_CREATED
        return NoteView(id=note.id, content=note.content, version=note.version)

    @app.get("/v1/notes", response_model=list[NoteView])
    def list_notes(
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> list[NoteView]:
        notes = session.scalars(scoped_note_query(principal.account_id, principal.user_id)).all()
        return [NoteView(id=n.id, content=n.content, version=n.version) for n in notes]

    @app.delete("/v1/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_note(
        note_id: str,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> Response:
        note = session.scalar(
            scoped_note_query(principal.account_id, principal.user_id).where(Note.id == note_id)
        )
        if note is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
        note.deleted = True
        note.version += 1
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/v1/tasks", response_model=list[TaskView])
    def list_tasks(
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> list[TaskView]:
        return [
            TaskView(id=t.id, title=t.title, completed=t.completed)
            for t in session.scalars(scoped_task_query(principal.account_id)).all()
        ]

    @app.post("/v1/tasks", response_model=TaskView, status_code=status.HTTP_201_CREATED)
    def create_task(
        body: TaskCreate,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> TaskView:
        try:
            task = create_task_idempotent(
                session,
                account_id=principal.account_id,
                user_id=principal.user_id,
                title=body.title,
                key=body.idempotency_key,
            )
            session.commit()
        except IdempotencyConflict as exc:
            session.rollback()
            raise _idempotency_conflict() from exc
        except IntegrityError:
            session.rollback()
            recovered_task = session.scalar(
                select(Task).where(
                    Task.account_id == principal.account_id,
                    Task.idempotency_key == body.idempotency_key,
                )
            )
            if recovered_task is None:
                raise
            task = recovered_task
            if task.title != body.title:
                raise _idempotency_conflict() from None
        return TaskView(id=task.id, title=task.title, completed=task.completed)

    @app.patch("/v1/tasks/{task_id}/complete", response_model=TaskView)
    def complete_task(
        task_id: str,
        request: Request,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> TaskView:
        # Tasks are shared across the account; any member may complete them.
        task = session.scalar(
            select(Task).where(
                Task.id == task_id,
                Task.account_id == principal.account_id,
            )
        )
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        newly_completed = not task.completed
        task.completed = True
        session.commit()
        if newly_completed:
            _signal_task_completed(session, request, task)
        return TaskView(id=task.id, title=task.title, completed=task.completed)

    @app.post("/v1/reminders", status_code=status.HTTP_201_CREATED)
    def create_reminder(
        body: ReminderCreate,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        if body.due_at.tzinfo is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="due_at must include a timezone offset",
            )
        existing = session.scalar(
            select(Reminder).where(
                Reminder.account_id == principal.account_id,
                Reminder.idempotency_key == body.idempotency_key,
            )
        )
        if existing is not None and (
            existing.text != body.text
            or existing.due_at_utc != body.due_at.astimezone(UTC)
            or existing.timezone != body.timezone
        ):
            raise _idempotency_conflict()
        reminder = existing or Reminder(
            account_id=principal.account_id,
            owner_user_id=principal.user_id,
            text=body.text,
            due_at_utc=body.due_at.astimezone(UTC),
            timezone=body.timezone,
            idempotency_key=body.idempotency_key,
        )
        if existing is None:
            session.add(reminder)
        session.commit()
        return {
            "id": reminder.id,
            "text": reminder.text,
            "due_at_utc": reminder.due_at_utc,
            "timezone": reminder.timezone,
            "state": reminder.state,
            "delivery": "test_adapter_only",
        }

    @app.post("/v1/messages", response_model=MessageView)
    def send_message(
        body: MessageCreate,
        request: Request,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> MessageView:
        request_hash = hashlib.sha256(body.text.encode("utf-8")).hexdigest()
        existing = session.scalar(
            select(Run).where(
                Run.account_id == principal.account_id,
                Run.logical_request_id == body.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash is not None and existing.request_hash != request_hash:
                raise _idempotency_conflict()
            return MessageView(
                run_id=existing.id,
                status=existing.status,
                outcome=Outcome(existing.outcome or "DEFERRED"),
                response=existing.response_text or "",
                route=_route_for(session, principal.account_id, body.idempotency_key),
            )
        _subscription, policy = policy_for(session, principal.account_id)
        runtime = _routing_runtime(request, settings)
        trace = _RequestTrace.begin(settings, principal, body.text, policy.plan_id, _telemetry(request))
        context: RoutingContext | None = None
        try:
            context = build_routing_context(
                request_id=trace.request_id,
                run_id=trace.run_id,
                text=body.text,
                tier=policy.plan_id,
                context_budget_tokens=policy.input_tokens,
            )
            trace.task_domain = context.task_domain
            routing: RoutingOutcome | None = runtime.route(
                settings=settings, context=context, plan=policy, actor_id=trace.actor_id
            )
        except NoEligibleModel as exc:
            return _defer_without_route(
                session, principal, body, request_hash, trace, exc, runtime, settings
            )
        except Exception as exc:
            # A failed policy or feature extractor must not bypass eligibility.
            logger.error("routing failed: %s; evaluating static eligibility", type(exc).__name__)
            routing = None
            trace.fallback_reason = "routing_error"
            METRICS.inc("router_routing_errors_total")
            try:
                safe_context = context or _conservative_context(trace, body.text, policy.input_tokens)
                trace.fallback_decision, eligibility = runtime.static_after_error(
                    settings, safe_context, policy
                )
                trace.rejections = eligibility.rejections
            except NoEligibleModel as no_route:
                return _defer_without_route(
                    session, principal, body, request_hash, trace, no_route, runtime, settings
                )
            except Exception as fallback_error:
                logger.error("static eligibility unavailable: %s", type(fallback_error).__name__)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="No safe route is available right now",
                ) from None
        live_decision = routing.live if routing is not None else trace.fallback_decision
        assert live_decision is not None
        route_name = live_decision.selected_model
        is_live = route_name == LIVE_ROUTE
        harness = runtime.harness_for(routing) if routing is not None else BUILTIN_HARNESS
        trace.routing, trace.harness = routing, harness
        amount = estimate_request_cost_micro(policy, settings, live=is_live)
        try:
            reservation = reserve_budget(
                session,
                settings=settings,
                account_id=principal.account_id,
                logical_request_id=body.idempotency_key,
                stage="execution",
                amount_micro=amount,
            )
        except BudgetDenied as exc:
            session.rollback()
            trace.finish(
                runtime, settings, TelemetryRunStatus.DEFERRED, outcome="DEFERRED", cost=0
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "ALLOWANCE_EXHAUSTED",
                    "message": str(exc),
                    "reset_at": exc.reset_at.isoformat(),
                },
            ) from exc
        except ReservationInFlight as exc:
            session.rollback()
            trace.finish(runtime, settings, TelemetryRunStatus.DUPLICATE, outcome=None, cost=0)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="request already in flight; retry to observe its result",
            ) from exc
        # Commit the reservation before provider calls so network latency does
        # not hold row locks on the account's budget rows.
        session.commit()
        trace.executed = True
        retrieved = False
        try:
            retrieval_started = time.perf_counter()
            context_manifest = build_note_context(
                session,
                account_id=principal.account_id,
                user_id=principal.user_id,
                max_tokens=policy.input_tokens,
                query_text=body.text,
                settings=settings,
                live=is_live,
                harness=harness,
            )
            retrieved = True
            trace.tools.append(
                ToolObservation("memory.retrieve", True, True, _elapsed_ms(retrieval_started))
            )
            trace.attempts.extend(context_manifest.attempts)
            result = fake_generate(
                body.text, context_manifest, settings=settings, route=route_name, harness=harness
            )
            trace.attempts.extend(result.attempts)
        except Exception as exc:
            session.rollback()
            release_budget(session, reservation)
            session.commit()
            if not retrieved:
                trace.tools.append(
                    ToolObservation("memory.retrieve", True, False, 0, type(exc).__name__)
                )
            trace.finish(runtime, settings, TelemetryRunStatus.FAILED, outcome=None, cost=None)
            raise
        for attempt in trace.attempts:
            if attempt.provider != LOCAL_PROVIDER:
                runtime.observe_provider(attempt.provider, success=attempt.success)
        tool_name = _INTENT_TOOLS.get(result.intent or "")
        provider_calls = accounted_provider_calls(
            [*context_manifest.provider_calls, *result.provider_calls], trace.attempts
        )
        actual_micro = measured_cost_micro(provider_calls)
        try:
            write_started = time.perf_counter()
            _apply_intent(session, result.intent, body, principal)
            run = persist_completed_run(
                session,
                account_id=principal.account_id,
                user_id=principal.user_id,
                logical_request_id=body.idempotency_key,
                response=result.response,
                outcome=result.outcome,
                request_hash=request_hash,
                run_id=trace.run_id,
                route=result.route,
            )
            settle_budget(
                session,
                reservation,
                attempt_id=f"{run.id}:1",
                actual_micro=actual_micro,
                calls=provider_calls,
            )
            session.commit()
            if tool_name:
                trace.tools.append(
                    ToolObservation(tool_name, True, True, _elapsed_ms(write_started))
                )
        except IntegrityError:
            session.rollback()
            release_failed_execution(
                session,
                reservation,
                attempt_id=f"{trace.run_id}:duplicate",
                calls=provider_calls,
            )
            session.commit()
            if tool_name:
                trace.tools.append(ToolObservation(tool_name, True, False, 0, "IntegrityError"))
            trace.finish(
                runtime, settings, TelemetryRunStatus.DUPLICATE,
                outcome=result.outcome, cost=actual_micro,
            )
            recovered = session.scalar(
                select(Run).where(
                    Run.account_id == principal.account_id,
                    Run.logical_request_id == body.idempotency_key,
                )
            )
            if recovered is None:
                raise
            if recovered.request_hash is not None and recovered.request_hash != request_hash:
                raise _idempotency_conflict() from None
            return MessageView(
                run_id=recovered.id,
                status=recovered.status,
                outcome=Outcome(recovered.outcome or "DEFERRED"),
                response=recovered.response_text or "",
                route=_route_for(session, principal.account_id, body.idempotency_key),
            )
        except Exception as exc:
            session.rollback()
            release_failed_execution(
                session,
                reservation,
                attempt_id=f"{trace.run_id}:failed",
                calls=provider_calls,
            )
            session.commit()
            if tool_name:
                trace.tools.append(ToolObservation(tool_name, True, False, 0, type(exc).__name__))
            trace.finish(
                runtime, settings, TelemetryRunStatus.FAILED, outcome=None, cost=actual_micro
            )
            raise
        trace.finish(
            runtime,
            settings,
            TelemetryRunStatus.COMPLETED
            if run.status == RunStatus.COMPLETED
            else TelemetryRunStatus.DEFERRED,
            outcome=result.outcome,
            cost=actual_micro,
        )
        return MessageView(
            run_id=run.id,
            status=run.status,
            outcome=result.outcome,
            response=result.response,
            route=result.route,
        )

    @app.post(
        "/v1/runs/{run_id}/feedback", status_code=status.HTTP_202_ACCEPTED
    )
    def run_feedback(
        run_id: str,
        body: FeedbackCreate,
        request: Request,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        run = session.scalar(
            select(Run).where(
                Run.id == run_id,
                Run.account_id == principal.account_id,
                Run.user_id == principal.user_id,
            )
        )
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
        record = build_feedback_record(
            run_id=run.id,
            feedback_type=body.feedback_type,
            original_response=run.response_text,
            corrected_text=body.corrected_text,
            key=telemetry_key(settings.auth_secret),
            store_text=settings.telemetry_store_correction_text,
        )
        _telemetry(request).emit(record)
        return {"feedback_id": record.feedback_id, "accepted": True}

    @app.post("/webhooks/internal-test")
    async def internal_webhook(
        request: Request,
        x_event_id: str = Header(min_length=1, max_length=160),
        x_timestamp: str = Header(min_length=1, max_length=20),
        x_signature_sha256: str | None = Header(default=None),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        raw = await request.body()
        if len(raw) > 256_000:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        verify_event_signature(
            raw, x_event_id, x_timestamp, x_signature_sha256, settings.webhook_secret
        )
        try:
            event, created = accept_internal_event(
                session, channel="internal_test", source_event_id=x_event_id, raw_body=raw
            )
        except IdempotencyConflict as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="event id was replayed with a different payload",
            ) from exc
        session.commit()
        return {"event_id": event.id, "accepted": created, "duplicate": not created}

    @app.post("/webhooks/billing-sandbox")
    async def billing_sandbox(
        request: Request,
        x_signature_sha256: str | None = Header(default=None),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        if not settings.is_development:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        raw = await request.body()
        verify_hmac(raw, x_signature_sha256, settings.webhook_secret)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="malformed billing event") from exc
        required = {"event_id", "account_id", "version", "type", "plan_id"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            raise HTTPException(status_code=422, detail="invalid billing event")
        if not isinstance(payload["version"], int):
            raise HTTPException(status_code=422, detail="invalid billing event version")
        if payload["type"] not in {"activated", "renewed", "cancelled"}:
            raise HTTPException(status_code=422, detail="unknown billing event type")
        if payload["plan_id"] not in SYNTHETIC_POLICIES:
            raise HTTPException(status_code=422, detail="unknown plan")
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == payload["account_id"])
        )
        if subscription is None:
            raise HTTPException(status_code=404, detail="account not found")
        existing = session.scalar(
            select(BillingEvent).where(
                BillingEvent.provider == "sandbox",
                BillingEvent.provider_event_id == payload["event_id"],
            )
        )
        if existing is not None:
            if existing.payload_hash != hashlib.sha256(raw).hexdigest():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="billing event id was replayed with a different payload",
                )
            return {"accepted": False, "duplicate": True}
        session.add(
            BillingEvent(
                provider="sandbox",
                provider_event_id=payload["event_id"],
                account_id=payload["account_id"],
                event_version=payload["version"],
                event_type=payload["type"],
                payload_hash=hashlib.sha256(raw).hexdigest(),
            )
        )
        stale = payload["version"] <= subscription.event_version
        if not stale:
            subscription.event_version = payload["version"]
            subscription.plan_id = payload["plan_id"]
            subscription.status = (
                "cancelled" if payload["type"] == "cancelled" else "active"
            )
            sync_account_progression(session, payload["account_id"])
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"accepted": False, "duplicate": True}
        return {"accepted": True, "duplicate": False, "stale": stale}

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(render_shell())

    @app.get("/static/{path:path}", include_in_schema=False)
    def static_file(path: str) -> FileResponse:
        static_dir = (Path(__file__).resolve().parent / "web" / "static").resolve()
        target = (static_dir / path).resolve()
        if not target.is_file() or not target.is_relative_to(static_dir):
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(target)

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest(tier: str | None = None) -> Response:
        data = build_manifest(tier)
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/manifest+json",
        )
    return app


def _idempotency_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="idempotency key was reused with a different payload",
    )


def _apply_intent(
    session: Session, intent: str | None, body: MessageCreate, principal: Principal
) -> None:
    """Perform the mutations a generated response claims, so response copy stays true."""
    if intent == "store_memory":
        session.add(
            Note(
                account_id=principal.account_id,
                owner_user_id=principal.user_id,
                content=body.text,
            )
        )
    elif intent == "create_task":
        session.add(
            Task(
                account_id=principal.account_id,
                owner_user_id=principal.user_id,
                title=body.text.strip()[:200] or body.text.strip(),
                idempotency_key=f"{body.idempotency_key}:task",
            )
        )


def _route_for(session: Session, account_id: str, logical_request_id: str) -> str | None:
    """Replay the executed route; legacy outbox rows fall back to their cost ledger."""
    outbox = session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.logical_key == f"response:{account_id}:{logical_request_id}"
        )
    )
    if outbox is not None:
        payload = json.loads(outbox.payload)
        if isinstance(payload, dict) and "route" in payload:
            route = payload["route"]
            if route is None:
                return None
            if isinstance(route, str) and route in {"fake-economy", "typesafe-system-one"}:
                return route
    reservation = session.scalar(
        select(BudgetReservation).where(
            BudgetReservation.account_id == account_id,
            BudgetReservation.logical_request_id == logical_request_id,
            BudgetReservation.stage == "execution",
        )
    )
    if reservation is None:
        return "fake-economy"
    provider = session.scalar(
        select(CostLedger.provider)
        .where(CostLedger.reservation_id == reservation.id)
        .limit(1)
    )
    return "typesafe-system-one" if provider == "typesafe" else "fake-economy"


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _telemetry(request: Request) -> TelemetrySink:
    sink: TelemetrySink | None = getattr(request.app.state, "telemetry", None)
    # Components are installed at startup; a bare app (no lifespan) gets a no-op sink.
    return sink if sink is not None else NullCollector()


def _routing_runtime(request: Request, settings: Settings) -> RoutingRuntime:
    runtime: RoutingRuntime | None = getattr(request.app.state, "routing", None)
    if runtime is None:
        runtime = build_routing_runtime(settings)
        request.app.state.routing = runtime
    return runtime


def _conservative_context(trace: "_RequestTrace", text: str, budget: int) -> RoutingContext:
    """Feature-extraction failure: use only bounded numeric facts, not a guessed task domain."""
    tokens = max(1, len(text.encode("utf-8")) // 4)
    return RoutingContext(
        request_id=trace.request_id,
        run_id=trace.run_id,
        tier=trace.tier,
        task_domain="general",
        estimated_input_tokens=tokens,
        context_budget_tokens=budget,
        context_utilization_ratio=min(1.0, tokens / budget) if budget > 0 else 0.0,
        tool_count=0,
        requires_structured_output=False,
        requires_tools=False,
        requires_memory=False,
        requires_external_data=False,
        conversation_depth=0,
        retry_number=0,
        previous_tool_failure=False,
        previous_structured_output_failure=False,
        latency_slo_ms=None,
    )



@dataclass
class _RequestTrace:
    """Observations gathered along one /v1/messages request, emitted once at the end."""

    sink: TelemetrySink
    run_id: str
    request_id: str
    actor_id: str
    fingerprint: str
    tier: str
    task_domain: str
    started_at: datetime
    started: float
    routing: RoutingOutcome | None = None
    harness: HarnessBundleV1 = BUILTIN_HARNESS
    fallback_decision: RoutingDecision | None = None
    fallback_reason: str | None = None
    rejections: dict[str, tuple[str, ...]] | None = None
    executed: bool = False
    attempts: list[AttemptOutcome] = field(default_factory=list)
    tools: list[ToolObservation] = field(default_factory=list)

    @classmethod
    def begin(
        cls, settings: Settings, principal: Principal, text: str, tier: str, sink: TelemetrySink
    ) -> "_RequestTrace":
        key = telemetry_key(settings.auth_secret)
        return cls(
            sink=sink,
            run_id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            actor_id=actor_id(key, principal.account_id, principal.user_id),
            fingerprint=request_fingerprint(key, text),
            tier=tier,
            task_domain="general",
            started_at=datetime.now(UTC),
            started=time.perf_counter(),
        )

    def finish(
        self,
        runtime: RoutingRuntime,
        settings: Settings,
        run_status: TelemetryRunStatus,
        *,
        outcome: str | None,
        cost: int | None,
    ) -> None:
        """Emit the run record and feed guardrails. Never raises into the request."""
        latency_ms = _elapsed_ms(self.started)
        try:
            record = build_run_record(
                run_id=self.run_id,
                request_id=self.request_id,
                actor_id=self.actor_id,
                fingerprint=self.fingerprint,
                started_at=self.started_at,
                completed_at=datetime.now(UTC),
                tier=self.tier,
                task_domain=self.task_domain,
                harness=self.harness,
                routing=self.routing,
                rejections=self.rejections,
                status=run_status,
                attempts=self.attempts,
                tools=self.tools,
                outcome=outcome,
                final_latency_ms=latency_ms,
                final_cost_micro=cost,
                live_fallback_reason=self.fallback_reason,
                fallback_decision=self.fallback_decision,
            )
            self.sink.emit(record)
        except Exception:
            METRICS.inc("telemetry_record_errors_total")
            logger.exception("could not build the telemetry run record")
        if self.routing is None or not self.executed:
            return
        try:
            runtime.after_run(
                settings,
                self.routing,
                failed=run_status == TelemetryRunStatus.FAILED,
                fell_back=any(not attempt.success for attempt in self.attempts),
                cost_micro=cost,
                latency_ms=latency_ms,
            )
        except Exception:
            logger.exception("routing guardrail evaluation failed")


def _defer_without_route(
    session: Session,
    principal: Principal,
    body: MessageCreate,
    request_hash: str,
    trace: _RequestTrace,
    exc: NoEligibleModel,
    runtime: RoutingRuntime,
    settings: Settings,
) -> MessageView:
    """No route survived eligibility: defer without reserving or charging anything."""
    METRICS.inc("router_no_eligible_model_total")
    trace.rejections = exc.rejections
    try:
        run = persist_completed_run(
            session,
            account_id=principal.account_id,
            user_id=principal.user_id,
            logical_request_id=body.idempotency_key,
            response=NO_ROUTE_RESPONSE,
            outcome=Outcome.DEFERRED,
            request_hash=request_hash,
            run_id=trace.run_id,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        trace.finish(runtime, settings, TelemetryRunStatus.DUPLICATE, outcome=None, cost=None)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="request already in flight; retry to observe its result",
        ) from None
    trace.finish(
        runtime, settings, TelemetryRunStatus.NO_ELIGIBLE_MODEL, outcome=Outcome.DEFERRED, cost=0
    )
    return MessageView(
        run_id=run.id,
        status=run.status,
        outcome=Outcome.DEFERRED,
        response=NO_ROUTE_RESPONSE,
        route=None,
    )


def _signal_task_completed(session: Session, request: Request, task: Task) -> None:
    """A task created from a message run was completed: a strong derived outcome signal."""
    if task.idempotency_key is None or not task.idempotency_key.endswith(":task"):
        return
    run_id = session.scalar(
        select(Run.id).where(
            Run.account_id == task.account_id,
            Run.logical_request_id == task.idempotency_key.removesuffix(":task"),
        )
    )
    if run_id is None:
        return
    _telemetry(request).emit(
        SignalRecord(
            signal_id=str(uuid.uuid4()),
            run_id=run_id,
            signal_type=SignalType.TASK_COMPLETED,
            strength=SignalStrength.STRONG,
            confidence=0.9,
            source=SignalSource.DERIVED,
            observed_at=datetime.now(UTC),
        )
    )


app = create_app()
