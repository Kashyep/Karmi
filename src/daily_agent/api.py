import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daily_agent.config import Settings, get_settings
from daily_agent.db import create_schema, get_session
from daily_agent.models import (
    Account,
    BillingEvent,
    BudgetReservation,
    CostLedger,
    Note,
    Reminder,
    Run,
    Subscription,
    Task,
    UsagePeriod,
    UsageWindow,
)
from daily_agent.plans import SYNTHETIC_POLICIES
from daily_agent.schemas import (
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
    BudgetDenied,
    IdempotencyConflict,
    accept_internal_event,
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
    reserve_budget,
    scoped_note_query,
    seed_development_identity,
    settle_budget,
    subscription_period,
)
from daily_agent.web import render_shell


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        if settings.is_development:
            create_schema()
        yield

    app = FastAPI(title="Daily Agent", version="0.1.0", lifespan=lifespan)

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
            reserved_micro=period.reserved_micro if period else 0,
            settled_micro=period.settled_micro if period else 0,
            spend_limit_micro=period.spend_limit_micro if period else policy.period_cost_cap_micro,
            reset_at=window.reset_at if window else day_reset,
            period_reset_at=period.reset_at if period else period_reset,
            policy_version=subscription.policy_version if subscription else "synthetic-dev-v1",
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

    @app.post("/v1/messages", response_model=MessageView)
    def send_message(
        body: MessageCreate,
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
        amount = estimate_request_cost_micro(policy, settings)
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
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "ALLOWANCE_EXHAUSTED", "message": str(exc), "reset_at": exc.reset_at.isoformat()},
            ) from exc
        # Commit the reservation before provider calls so network latency does
        # not hold row locks on the account's budget rows.
        session.commit()
        try:
            context = build_note_context(
                session,
                account_id=principal.account_id,
                user_id=principal.user_id,
                max_tokens=policy.input_tokens,
                query_text=body.text,
                settings=settings,
            )
            result = fake_generate(body.text, context, settings=settings)
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
            )
            provider_calls = [*context.provider_calls, *result.provider_calls]
            settle_budget(
                session,
                reservation,
                attempt_id=f"{run.id}:1",
                actual_micro=measured_cost_micro(provider_calls),
                calls=provider_calls,
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            release_budget(session, reservation)
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
                route=_route_for(session, principal.account_id, body.idempotency_key),
            )
        except Exception:
            session.rollback()
            release_budget(session, reservation)
            session.commit()
            raise
        return MessageView(
            run_id=run.id,
            status=run.status,
            outcome=result.outcome,
            response=result.response,
            route=result.route,
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
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"accepted": False, "duplicate": True}
        return {"accepted": True, "duplicate": False, "stale": stale}

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(render_shell())

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        path = Path(__file__).with_name("web") / "manifest.webmanifest"
        return FileResponse(path, media_type="application/manifest+json")

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


def _route_for(session: Session, account_id: str, logical_request_id: str) -> str:
    """Recover the route taken for an earlier run via its cost ledger rows."""
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


app = create_app()
