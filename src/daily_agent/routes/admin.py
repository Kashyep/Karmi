"""``/v1/admin/*``: operator API. Every route needs Clerk bearer + allowlist + admin role
(+ an unexpired ``X-Admin-Session`` except the sign-in endpoints). Never returns secrets."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, StrictInt, StringConstraints, model_validator
from sqlalchemy.orm import Session

from daily_agent import admin_service as svc
from daily_agent.admin_auth import (
    AdminCodeInvalid,
    AdminContext,
    AdminLocked,
    admin_identity,
    append_audit,
    find_session,
    open_session,
    require_admin_session,
)
from daily_agent.admin_metrics import METRICS
from daily_agent.clerk_backend import ClerkBackend, get_clerk_backend
from daily_agent.config import Settings, get_settings
from daily_agent.db import get_session
from daily_agent.deps import gateway_dependency
from daily_agent.gateway import Gateway
from daily_agent.models import User
from daily_agent.security import as_utc

router = APIRouter(prefix="/v1/admin", tags=["admin"])

Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]


class SessionOpen(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class ReasonBody(BaseModel):
    reason: Reason


class TierBody(ReasonBody):
    tier: str | StrictInt
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def future_expiry(self) -> TierBody:
        if self.expires_at is not None:
            expiry = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=UTC)
            if expiry <= datetime.now(UTC):
                raise ValueError("expires_at must be in the future")
            self.expires_at = expiry
        return self


class UserEditBody(ReasonBody):
    display_name: str | None = Field(default=None, max_length=120)
    tester: bool | None = None
    tester_label: str | None = Field(default=None, max_length=40)
    admin_notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_edit(self) -> UserEditBody:
        if self.display_name is not None and not self.display_name.strip():
            raise ValueError("display_name cannot be blank")
        return self


class BulkTierBody(TierBody):
    user_ids: list[str] = Field(min_length=1, max_length=100)

class CreditsBody(ReasonBody):
    delta_usd: float | None = Field(default=None, ge=-1_000_000, le=1_000_000)
    budget_usd: float | None = Field(default=None, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def exactly_one(self) -> CreditsBody:
        if (self.delta_usd is None) == (self.budget_usd is None):
            raise ValueError("provide exactly one of delta_usd or budget_usd")
        return self


class DeleteBody(ReasonBody):
    confirm: Literal["DELETE"]


@router.post("/session")
def create_session(
    body: SessionOpen,
    user: User = Depends(admin_identity),
    session: Session = Depends(get_session),
) -> Response:
    try:
        token, expires_at = open_session(session, user, body.code)
    except AdminLocked as exc:
        return JSONResponse(
            status_code=status.HTTP_423_LOCKED,
            content={"retry_after": exc.retry_after},
            headers={"Retry-After": str(exc.retry_after)},
        )
    except AdminCodeInvalid:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": "invalid credentials"}
        )
    return JSONResponse(
        {"admin_session_token": token, "expires_at": as_utc(expires_at).isoformat()},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/session")
def read_session(
    user: User = Depends(admin_identity),
    session: Session = Depends(get_session),
    x_admin_session: str | None = Header(default=None),
) -> dict[str, Any]:
    row = find_session(session, user.id, x_admin_session)
    return {"valid": row is not None, "expires_at": as_utc(row.expires_at).isoformat() if row else None}


@router.delete("/session")
def delete_session(
    user: User = Depends(admin_identity),
    session: Session = Depends(get_session),
    x_admin_session: str | None = Header(default=None),
) -> dict[str, bool]:
    row = find_session(session, user.id, x_admin_session)
    if row is not None:
        row.revoked_at = datetime.now(UTC)
        append_audit(session, admin_user_id=user.id, action="admin.logout")
        session.commit()
    return {"signed_out": True}


@router.get("/users")
def users(
    q: str | None = Query(default=None, max_length=200),
    tier: str | None = Query(default=None, max_length=20),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    tester_label: str | None = Query(default=None, max_length=40),
    suspended: bool | None = None,
    plan_expiring_before: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=svc.MAX_PAGE),
    cursor: str | None = Query(default=None, max_length=64),
    _admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return svc.list_users(
        session, q=q, tier=tier, state=status_filter, tester_label=tester_label,
        suspended=suspended, plan_expiring_before=plan_expiring_before, limit=limit, cursor=cursor
    )


@router.get("/users/{user_id}")
def user_detail(
    user_id: str,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return svc.user_detail(session, settings, admin.user.id, user_id)
@router.patch("/users/{user_id}")
def edit_user(
    user_id: str,
    body: UserEditBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return svc.edit_user(
        session, settings, admin.user.id, user_id,
        display_name=body.display_name, tester=body.tester,
        tester_label=body.tester_label, admin_notes=body.admin_notes, reason=body.reason,
    )


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    body: ReasonBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return svc.suspend(session, settings, admin.user.id, user_id, body.reason)


@router.post("/users/{user_id}/unsuspend")
def unsuspend_user(
    user_id: str,
    body: ReasonBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return svc.unsuspend(session, admin.user.id, user_id, body.reason)


@router.post("/users/{user_id}/revoke-sessions")
def revoke_user_sessions(
    user_id: str,
    body: ReasonBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    clerk: ClerkBackend | None = Depends(get_clerk_backend),
) -> dict[str, Any]:
    return svc.revoke_sessions(session, admin.user.id, user_id, body.reason, clerk)


@router.post("/users/{user_id}/tier")
def set_user_tier(
    user_id: str,
    body: TierBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return svc.change_tier(session, settings, admin.user.id, user_id, body.tier, body.reason, body.expires_at)


@router.post("/users/bulk-tier")
def bulk_tier(
    body: BulkTierBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return svc.bulk_change_tier(session, settings, admin.user.id, body.user_ids, body.tier, body.reason, body.expires_at)


@router.post("/users/{user_id}/credits")
def set_user_credits(
    user_id: str,
    body: CreditsBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return svc.adjust_credits(
        session,
        settings,
        admin.user.id,
        user_id,
        delta_usd=body.delta_usd,
        budget_usd=body.budget_usd,
        reason=body.reason,
    )


@router.get("/users/{user_id}/export")
def export_user_data(
    user_id: str,
    reason: Annotated[str, Query(min_length=3, max_length=500)],
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
) -> JSONResponse:
    return JSONResponse(
        svc.export_user(session, admin.user.id, user_id, reason.strip()),
        headers={
            "Content-Disposition": f'attachment; filename="user-{user_id}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    body: DeleteBody,
    admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return svc.erase_user(session, settings, admin.user.id, user_id, body.reason)


@router.get("/monitor")
def monitor(
    request: Request,
    _admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway: Gateway = Depends(gateway_dependency),
) -> dict[str, Any]:
    cache: svc.MonitorCache | None = getattr(request.app.state, "admin_monitor_cache", None)
    if cache is None:
        cache = svc.MonitorCache()
        request.app.state.admin_monitor_cache = cache
    return cache.get(lambda: svc.build_monitor(session, settings, gateway, METRICS))


@router.get("/audit")
def audit(
    limit: int = Query(default=50, ge=1, le=svc.MAX_PAGE),
    cursor: str | None = Query(default=None, max_length=32),
    _admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return svc.list_audit(session, limit=limit, cursor=cursor)


@router.get("/runs")
def runs(
    limit: int = Query(default=50, ge=1, le=svc.MAX_PAGE),
    cursor: str | None = Query(default=None, max_length=80),
    _admin: AdminContext = Depends(require_admin_session),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return svc.list_runs(session, limit=limit, cursor=cursor)
