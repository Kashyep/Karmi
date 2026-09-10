import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daily_agent.config import Settings, get_settings
from daily_agent.db import create_schema, get_session
from daily_agent.models import Account, BudgetReservation, Note, Reminder, Run, Subscription, Task
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
    verify_hmac,
)
from daily_agent.services import (
    BudgetDenied,
    accept_internal_event,
    build_note_context,
    create_task_idempotent,
    ensure_usage_window,
    fake_generate,
    persist_completed_run,
    policy_for,
    reserve_budget,
    scoped_note_query,
    seed_development_identity,
    settle_budget,
)
from daily_agent.web import render_shell


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        if settings.environment in {"development", "test"}:
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
        if not settings.allow_development_auth or settings.environment == "production":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if role not in {"customer", "admin"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        user = seed_development_identity(session, role=role)
        return {"token": issue_development_token(user, settings), "user_id": user.id}

    @app.get("/admin/overview")
    def admin_overview(
        _admin: Principal = Depends(require_admin),
        session: Session = Depends(get_session),
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
            "live_models": False,
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
        settings: Settings = Depends(get_settings),
    ) -> UsageView:
        subscription, policy = policy_for(session, principal.account_id)
        window = ensure_usage_window(session, principal.account_id, settings)
        session.commit()
        return UsageView(
            plan_id=policy.plan_id,
            plan_label=policy.display_name,
            everyday_used=window.everyday_used,
            everyday_limit=window.everyday_limit,
            reserved_micro=window.reserved_micro,
            settled_micro=window.settled_micro,
            spend_limit_micro=window.spend_limit_micro,
            reset_at=window.reset_at,
            policy_version=subscription.policy_version,
        )

    @app.post("/v1/notes", response_model=NoteView, status_code=status.HTTP_201_CREATED)
    def create_note(
        body: NoteCreate,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> NoteView:
        note = Note(
            account_id=principal.account_id, owner_user_id=principal.user_id, content=body.content
        )
        session.add(note)
        session.commit()
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
        return TaskView(id=task.id, title=task.title, completed=task.completed)

    @app.patch("/v1/tasks/{task_id}/complete", response_model=TaskView)
    def complete_task(
        task_id: str,
        principal: Principal = Depends(require_principal),
        session: Session = Depends(get_session),
    ) -> TaskView:
        task = session.scalar(
            select(Task).where(Task.id == task_id, Task.account_id == principal.account_id)
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
        existing = session.scalar(
            select(Run).where(Run.logical_request_id == body.idempotency_key)
        )
        if existing is not None:
            if existing.account_id != principal.account_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="request key conflict")
            return MessageView(
                run_id=existing.id,
                status=existing.status,
                outcome=Outcome(existing.outcome or "DEFERRED"),
                response=existing.response_text or "",
                route="fake-economy",
            )
        _subscription, policy = policy_for(session, principal.account_id)
        amount = min(1_000, policy.request_cost_cap_micro)
        try:
            reservation = reserve_budget(
                session,
                settings=settings,
                account_id=principal.account_id,
                logical_request_id=body.idempotency_key,
                stage="execution",
                amount_micro=amount,
            )
            context = build_note_context(
                session,
                account_id=principal.account_id,
                user_id=principal.user_id,
                max_tokens=policy.input_tokens,
            )
            response, outcome = fake_generate(body.text, context)
            run = persist_completed_run(
                session,
                account_id=principal.account_id,
                user_id=principal.user_id,
                logical_request_id=body.idempotency_key,
                response=response,
                outcome=outcome,
            )
            settle_budget(session, reservation, attempt_id=f"{run.id}:1", actual_micro=100)
            session.commit()
        except BudgetDenied as exc:
            session.rollback()
            window = ensure_usage_window(session, principal.account_id, settings)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "ALLOWANCE_EXHAUSTED", "message": str(exc), "reset_at": window.reset_at.isoformat()},
            ) from exc
        return MessageView(
            run_id=run.id,
            status=run.status,
            outcome=outcome,
            response=response,
            route="fake-economy",
        )

    @app.post("/webhooks/internal-test")
    async def internal_webhook(
        request: Request,
        x_event_id: str = Header(min_length=1, max_length=160),
        x_signature_sha256: str | None = Header(default=None),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        raw = await request.body()
        if len(raw) > 256_000:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        verify_hmac(raw, x_signature_sha256, settings.webhook_secret)
        event, created = accept_internal_event(
            session, channel="internal_test", source_event_id=x_event_id, raw_body=raw
        )
        session.commit()
        return {"event_id": event.id, "accepted": created, "duplicate": not created}

    @app.post("/webhooks/billing-sandbox")
    async def billing_sandbox(
        request: Request,
        x_signature_sha256: str | None = Header(default=None),
        session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, object]:
        from daily_agent.models import BillingEvent

        if settings.environment not in {"development", "test"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        raw = await request.body()
        verify_hmac(raw, x_signature_sha256, settings.webhook_secret)
        payload = json.loads(raw)
        required = {"event_id", "account_id", "version", "type", "plan_id"}
        if not required.issubset(payload):
            raise HTTPException(status_code=422, detail="invalid billing event")
        if payload["plan_id"] not in SYNTHETIC_POLICIES:
            raise HTTPException(status_code=422, detail="unknown plan")
        existing = session.scalar(
            select(BillingEvent).where(
                BillingEvent.provider == "sandbox",
                BillingEvent.provider_event_id == payload["event_id"],
            )
        )
        if existing is not None:
            return {"accepted": False, "duplicate": True}
        subscription = session.scalar(
            select(Subscription).where(Subscription.account_id == payload["account_id"])
        )
        if subscription is None:
            raise HTTPException(status_code=404, detail="account not found")
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
            subscription.status = "active" if payload["type"] in {"activated", "renewed"} else "cancelled"
        session.commit()
        return {"accepted": True, "duplicate": False, "stale": stale}

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        return HTMLResponse(render_shell())

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        path = Path(__file__).with_name("web") / "manifest.webmanifest"
        return FileResponse(path, media_type="application/manifest+json")

    return app


app = create_app()
