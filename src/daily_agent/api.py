import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from daily_agent.access_codes import PLAN_RANK, load_access_code_hashes, plan_for_code
from daily_agent.config import Settings, get_settings
from daily_agent.db import create_schema, get_engine, get_session
from daily_agent.deps import gateway_dependency, limited_principal, own_run
from daily_agent.gateway import Gateway
from daily_agent.gateway.service import MAX_ATTEMPTS
from daily_agent.models import (
    Account,
    BillingEvent,
    BudgetReservation,
    MessageFeedback,
    Reminder,
    RoutingRecord,
    Run,
    Subscription,
    Task,
    UsagePeriod,
    UsageWindow,
    User,
)
from daily_agent.parakh.routing import RunTiming, record_routing_evidence, route_for_action
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.ratelimit import SlidingWindowLimiter, install_log_redaction
from daily_agent.routes.conversations import router as conversations_router
from daily_agent.routes.stream import router as stream_router
from daily_agent.schemas import (
    ARMORY_TIERS,
    AccessCodeRedeem,
    AccessCodeView,
    ActiveThemeUpdate,
    ArmoryView,
    FeedbackCreate,
    FeedbackView,
    MessageCreate,
    MessageView,
    Outcome,
    RegenerateCreate,
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
    BudgetDenied,
    GatewayAdmission,
    GatewayCapacityFull,
    IdempotencyConflict,
    ReservationInFlight,
    accept_internal_event,
    admit_gateway_requests,
    create_task_idempotent,
    current_period_key,
    current_window_key,
    estimate_request_cost_micro,
    gateway_requests_made,
    generate_reply,
    measured_cost_micro,
    measured_tokens,
    persist_completed_run,
    plan_policy,
    policy_for,
    release_budget,
    reserve_budget,
    return_gateway_requests,
    scoped_task_query,
    seed_development_identity,
    settle_budget,
    subscription_period,
    sync_account_progression,
    sync_theme_progression,
)
from daily_agent.streaming.registry import sweep_interrupted_runs
from daily_agent.web import build_manifest, render_shell

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    install_log_redaction()
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        if settings.is_development and settings.database_url.startswith("sqlite"):
            create_schema()
        try:
            with Session(get_engine()) as session:
                swept = sweep_interrupted_runs(session)
            if swept:
                logger.info("stream.swept_interrupted runs=%s", swept)
        except SQLAlchemyError:
            logger.warning("stream.sweep_failed (schema not migrated?)", exc_info=True)
        yield

    app = FastAPI(title="Daily Agent", version="0.1.0", lifespan=lifespan)

    app.include_router(stream_router)
    app.include_router(conversations_router)

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
            tokens_used=(window.tokens_reserved + window.tokens_settled) if window else 0,
            tokens_limit=policy.daily_token_limit,
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
        task.completed = True
        session.commit()
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

    def execute_message(
        body: MessageCreate,
        principal: Principal,
        session: Session,
        settings: Settings,
        gateway: Gateway,
        *,
        escalate: bool = False,
        previous_run_id: str | None = None,
        regenerate_reason: str | None = None,
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
                route=_route_for(session, existing.id),
                previous_run_id=existing.previous_run_id,
            )
        _subscription, policy = policy_for(session, principal.account_id)
        amount = estimate_request_cost_micro(policy, settings)
        # Token quota applies to live generation only; the demo path never spends tokens.
        token_hold = (
            max(1, len(body.text.encode("utf-8")) // 4) + policy.output_tokens
            if gateway.live
            else 0
        )
        try:
            reservation = reserve_budget(
                session,
                settings=settings,
                account_id=principal.account_id,
                logical_request_id=body.idempotency_key,
                stage="execution",
                amount_micro=amount,
                tokens=token_hold,
            )
            # Every live reply may make up to MAX_ATTEMPTS provider requests; unused ones are
            # handed back after generation.
            admission: GatewayAdmission | None = (
                admit_gateway_requests(
                    session, settings, paid=policy.price_inr > 0, slots=MAX_ATTEMPTS
                )
                if gateway.live
                else None
            )
        except GatewayCapacityFull as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "BETA_CAPACITY_FULL",
                    "message": _capacity_full_message(exc.reset_at),
                    "reset_at": exc.reset_at.isoformat(),
                },
            ) from exc
        except BudgetDenied as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "ALLOWANCE_EXHAUSTED", "message": str(exc), "reset_at": exc.reset_at.isoformat()},
            ) from exc
        except ReservationInFlight as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="request already in flight; retry to observe its result",
            ) from exc
        # Commit the reservation before provider calls so network latency does
        # not hold row locks on the account's budget rows.
        session.commit()
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        try:
            result = generate_reply(
                body.text,
                settings=settings,
                plan=policy,
                gateway=gateway,
                escalate=escalate,
            )
            timing = RunTiming(
                started_at=started_at,
                completed_at=datetime.now(UTC),
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        except Exception:
            session.rollback()
            release_budget(session, reservation)
            session.commit()
            raise
        try:
            _apply_intent(session, result.intent, body, principal)
            run = persist_completed_run(
                session,
                account_id=principal.account_id,
                user_id=principal.user_id,
                logical_request_id=body.idempotency_key,
                response=result.response,
                outcome=result.outcome,
                request_hash=request_hash,
                previous_run_id=previous_run_id,
                regenerate_reason=regenerate_reason,
            )
            record_routing_evidence(
                session,
                run_id=run.id,
                settings=settings,
                plan=policy,
                text=body.text,
                result=result,
                timing=timing,
                gateway=gateway,
            )
            provider_calls = list(result.provider_calls)
            if admission is not None:
                return_gateway_requests(session, admission, gateway_requests_made(provider_calls))
            if result.release_reservation:
                # Every model attempt failed: nothing usable was produced, so nothing is charged.
                release_budget(session, reservation)
            else:
                settle_budget(
                    session,
                    reservation,
                    attempt_id=f"{run.id}:1",
                    actual_micro=measured_cost_micro(provider_calls),
                    actual_tokens=measured_tokens(provider_calls),
                    calls=provider_calls,
                )
            session.commit()
        except IntegrityError:
            session.rollback()
            release_budget(session, reservation)
            if admission is not None:
                return_gateway_requests(
                    session, admission, gateway_requests_made(result.provider_calls)
                )
            session.commit()
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
                route=_route_for(session, recovered.id),
                previous_run_id=recovered.previous_run_id,
            )
        except Exception:
            session.rollback()
            release_budget(session, reservation)
            if admission is not None:
                return_gateway_requests(
                    session, admission, gateway_requests_made(result.provider_calls)
                )
            session.commit()
            raise
        return MessageView(
            run_id=run.id,
            status=run.status,
            outcome=result.outcome,
            response=result.response,
            route=result.route,
            previous_run_id=run.previous_run_id,
        )

    @app.post("/v1/messages", response_model=MessageView)
    def send_message(
        body: MessageCreate,
        principal: Principal = Depends(limited_principal),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
        gateway: Gateway = Depends(gateway_dependency),
    ) -> MessageView:
        return execute_message(body, principal, session, settings, gateway)


    @app.post("/v1/access-code", response_model=AccessCodeView)
    def redeem_access_code(
        body: AccessCodeRedeem,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> AccessCodeView:
        """Unlock a higher beta tier with a secret code. Never downgrades; guesses are throttled."""
        guesses: SlidingWindowLimiter | None = getattr(app.state, "code_limiter", None)
        if guesses is None:
            guesses = SlidingWindowLimiter(limit=5)
            app.state.code_limiter = guesses
        retry_after = guesses.check(principal.user_id)
        if retry_after is not None:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "RATE_LIMITED", "message": "too many attempts; wait and retry"},
                headers={"Retry-After": str(retry_after)},
            )
        hashes = getattr(app.state, "access_code_hashes", None)
        if hashes is None:
            hashes = load_access_code_hashes(settings.access_codes_path)
            app.state.access_code_hashes = hashes
        plan_id = plan_for_code(body.code, hashes)
        if plan_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invalid access code")
        subscription, current = policy_for(session, principal.account_id)
        changed = PLAN_RANK[plan_id] > PLAN_RANK.get(current.plan_id, 0)
        if changed:
            subscription.plan_id = plan_id
            subscription.policy_version = "beta-access-code-v1"
            sync_account_progression(session, principal.account_id)
            session.commit()
            logger.info("access code upgraded account %s to %s", principal.account_id, plan_id)
        policy = SYNTHETIC_POLICIES[subscription.plan_id]
        return AccessCodeView(plan_id=policy.plan_id, plan_label=policy.display_name, changed=changed)

    @app.post("/v1/runs/{run_id}/feedback", response_model=FeedbackView)
    def rate_reply(
        run_id: str,
        body: FeedbackCreate,
        principal: Principal = Depends(limited_principal),
        session: Session = Depends(get_session),
    ) -> FeedbackView:
        """Idempotent upsert: repeating a rating is a no-op, a new rating replaces the old one."""
        own_run(session, principal, run_id)
        reason = body.reason if body.rating == "down" else None

        def upsert() -> None:
            row = session.scalar(
                select(MessageFeedback).where(
                    MessageFeedback.account_id == principal.account_id,
                    MessageFeedback.run_id == run_id,
                )
            )
            if row is None:
                session.add(
                    MessageFeedback(
                        account_id=principal.account_id,
                        user_id=principal.user_id,
                        run_id=run_id,
                        rating=body.rating,
                        reason=reason,
                    )
                )
            elif (row.rating, row.reason) != (body.rating, reason):
                row.rating, row.reason, row.updated_at = body.rating, reason, datetime.now(UTC)
            session.commit()

        try:
            upsert()
        except IntegrityError:
            session.rollback()  # a concurrent identical request created the row first
            upsert()
        return FeedbackView(run_id=run_id, rating=body.rating, reason=reason)

    @app.post("/v1/runs/{run_id}/regenerate", response_model=MessageView)
    def regenerate_reply(
        run_id: str,
        body: RegenerateCreate,
        principal: Principal = Depends(limited_principal),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
        gateway: Gateway = Depends(gateway_dependency),
    ) -> MessageView:
        previous = own_run(session, principal, run_id)
        if body.idempotency_key == previous.logical_request_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="regenerate needs a new idempotency key",
            )
        if previous.request_hash != hashlib.sha256(body.text.encode("utf-8")).hexdigest():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="text does not match the original request",
            )
        return execute_message(
            MessageCreate(text=body.text, idempotency_key=body.idempotency_key),
            principal,
            session,
            settings,
            gateway,
            escalate=True,
            previous_run_id=previous.id,
            regenerate_reason=body.reason,
        )

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


# India Standard Time, for the reset time shown to beta testers.
IST = timedelta(hours=5, minutes=30)


def _capacity_full_message(reset_at: datetime) -> str:
    ist = (reset_at.astimezone(UTC) + IST).strftime("%H:%M")
    utc = reset_at.astimezone(UTC).strftime("%H:%M")
    return (
        "Karmi's beta has reached today's limit for free AI replies. "
        f"Try again after {ist} IST ({utc} UTC)."
    )


def _idempotency_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="idempotency key was reused with a different payload",
    )


def _apply_intent(
    session: Session, intent: str | None, body: MessageCreate, principal: Principal
) -> None:
    """Perform the mutations a generated response claims, so response copy stays true."""
    if intent == "create_task":
        session.add(
            Task(
                account_id=principal.account_id,
                owner_user_id=principal.user_id,
                title=body.text.strip()[:200] or body.text.strip(),
                idempotency_key=f"{body.idempotency_key}:task",
            )
        )


def _route_for(session: Session, run_id: str) -> str:
    """Recover the route an earlier run executed from its routing record."""
    executed = session.scalar(
        select(RoutingRecord.executed_action).where(RoutingRecord.run_id == run_id)
    )
    return route_for_action(executed) if executed else "fake-economy"


app = create_app()
