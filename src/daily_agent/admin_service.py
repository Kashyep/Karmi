"""Admin operations on users, usage, audit and the live monitor.

Every mutation stages its ``admin_audit_log`` row in the same transaction as the change it
records, so an action is never committed without its audit entry (and vice versa). Message
bodies are never read here: support sees metadata only.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session, defer

from daily_agent.admin_auth import append_audit, revoke_admin_sessions
from daily_agent.admin_metrics import RequestMetrics
from daily_agent.clerk_backend import ClerkBackend, ClerkBackendError
from daily_agent.config import Settings
from daily_agent.gateway import Gateway
from daily_agent.models import (
    Account,
    AdminAuditLog,
    AdminCredential,
    AdminSession,
    BillingEvent,
    BudgetReservation,
    BugReport,
    ChatMessage,
    Conversation,
    CostLedger,
    ErasedClerkSubject,
    GatewayRequestDay,
    MessageFeedback,
    OutboxEvent,
    PlatformBudget,
    Reminder,
    RoutingDecision,
    RoutingRecord,
    Run,
    RunStatus,
    Subscription,
    Task,
    UsagePeriod,
    UsageWindow,
    User,
)
from daily_agent.plans import MICRO_PER_INR, SYNTHETIC_POLICIES
from daily_agent.security import as_utc, clerk_subject_digest
from daily_agent.services import (
    current_window_key,
    ensure_usage_period,
    plan_for_tier,
    plan_policy,
    rebase_usage_window,
    sync_account_progression,
    tier_for_plan,
)
from daily_agent.streaming.registry import get_stream_registry

MAX_PAGE = 100
ACTIVE_WINDOW = timedelta(minutes=5)
MONITOR_CACHE_SECONDS = 4.0


def _iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat() if value is not None else None


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def parse_tier(tier: str | int) -> str:
    """Accept a plan id (``yanta``) or a tier number 1-4; return the plan id."""
    if isinstance(tier, bool):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid tier")
    if isinstance(tier, int) or (isinstance(tier, str) and tier.isascii() and tier.isdigit()):
        number = int(tier)
        if number not in range(1, 5):
            raise _bad("tier must be 1-4 or a plan id")
        return plan_for_tier(number)
    if isinstance(tier, str) and not tier.isascii():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid tier")
    plan = str(tier).strip().lower()
    if plan not in SYNTHETIC_POLICIES:
        raise _bad("unknown tier")
    return plan


def inr_to_micro(inr: float) -> int:
    return round(inr * MICRO_PER_INR)


def micro_to_inr(micro: int) -> float:
    return round(micro / MICRO_PER_INR, 6)


def _subscription(session: Session, account_id: str) -> Subscription | None:
    return session.scalar(select(Subscription).where(Subscription.account_id == account_id))


def user_item(
    user: User,
    subscription: Subscription | None,
    open_bug_reports: int = 0,
) -> dict[str, Any]:
    policy = plan_policy(subscription)
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "tester": user.tester,
        "tester_label": user.tester_label,
        "tier": policy.plan_id,
        "effective_plan": policy.plan_id,
        "plan_expires_at": _iso(subscription.tier_expires_at) if subscription else None,
        "revert_plan_id": subscription.revert_plan_id if subscription else None,
        "unlocked_tier": user.unlocked_tier,
        "disabled": user.disabled,
        "created_at": _iso(user.created_at),
        "last_active_at": _iso(user.last_active_at),
        "open_bug_reports": open_bug_reports,
    }


def _load_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise _not_found()
    return user


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_users(
    session: Session,
    *,
    q: str | None,
    tier: str | None,
    state: str | None,
    tester_label: str | None = None,
    suspended: bool | None = None,
    plan_expiring_before: datetime | None = None,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_PAGE))
    stmt = select(User, Subscription).outerjoin(Subscription, Subscription.account_id == User.account_id)
    if q:
        needle = f"%{_escape_like(q.strip().lower())}%"
        stmt = stmt.where(
            or_(func.lower(User.email).like(needle, escape="\\"), func.lower(User.display_name).like(needle, escape="\\"), User.id == q.strip())
        )
    if tier:
        parse_tier(tier)
    if state:
        if state not in {"active", "suspended"}:
            raise _bad("status must be active or suspended")
        stmt = stmt.where(User.disabled.is_(state == "suspended"))
    if suspended is not None:
        stmt = stmt.where(User.disabled.is_(suspended))
    if tester_label is not None:
        stmt = stmt.where(User.tester_label == tester_label)
    if plan_expiring_before is not None:
        stmt = stmt.where(Subscription.tier_expires_at.is_not(None), Subscription.tier_expires_at <= plan_expiring_before)
    if cursor:
        stmt = stmt.where(User.id > cursor)
    rows = session.execute(stmt.order_by(User.id).limit(limit + 1)).all()
    if tier:
        plan = parse_tier(tier)
        rows = [(user, sub) for user, sub in rows if user_item(user, sub)["effective_plan"] == plan]  # type: ignore[misc]
    page = rows[:limit]
    user_ids = [u.id for u, _ in page]
    counts: dict[str, int] = {}
    if user_ids:
        report_counts = session.execute(
            select(BugReport.user_id, func.count())
            .where(
                BugReport.user_id.in_(user_ids),
                BugReport.status.notin_(["fixed", "closed", "duplicate", "wontfix"]),
            )
            .group_by(BugReport.user_id)
        ).all()
        counts = {uid: int(count) for uid, count in report_counts}
    return {
        "items": [user_item(user, sub, counts.get(user.id, 0)) for user, sub in page],
        "next_cursor": page[-1][0].id if len(rows) > limit and page else None,
    }


def usage_summary(session: Session, settings: Settings, user: User) -> dict[str, Any]:
    subscription = _subscription(session, user.account_id)
    policy = plan_policy(subscription)
    now = datetime.now(UTC)
    day_key, _reset = current_window_key(now)
    window = session.scalar(
        select(UsageWindow).where(
            UsageWindow.account_id == user.account_id, UsageWindow.window_key == day_key
        )
    )
    period = session.scalars(
        select(UsagePeriod)
        .where(UsagePeriod.account_id == user.account_id, UsagePeriod.reset_at > now)
        .order_by(UsagePeriod.reset_at)
    ).first()
    limit = period.spend_limit_micro if period else policy.period_cost_cap_micro
    spent = (period.settled_micro + period.reserved_micro) if period else 0
    conversations = session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.user_id == user.id, Conversation.deleted_at.is_(None))
    )
    return {
        "today_requests": window.everyday_used if window else 0,
        "month_spend_inr": micro_to_inr(spent),
        "credits_remaining": micro_to_inr(max(0, limit - spent)),
        "sessions": conversations or 0,
    }


def user_detail(session: Session, settings: Settings, admin_id: str, user_id: str) -> dict[str, Any]:
    user = _load_user(session, user_id)
    open_reports = (
        session.scalar(
            select(func.count())
            .select_from(BugReport)
            .where(
                BugReport.user_id == user.id,
                BugReport.status.notin_(["fixed", "closed", "duplicate", "wontfix"]),
            )
        )
        or 0
    )
    result = user_item(user, _subscription(session, user.account_id), open_bug_reports=open_reports)
    result["admin_notes"] = user.admin_notes
    result["usage"] = usage_summary(session, settings, user)
    append_audit(session, admin_user_id=admin_id, action="user.view", target_user_id=user.id)
    session.commit()
    return result


def _revoke_all(session: Session, user: User) -> None:
    user.token_version += 1
    user.sessions_revoked_at = datetime.now(UTC)
    revoke_admin_sessions(session, user.id)


def _refuse_admin_target(
    session: Session, settings: Settings, admin_id: str, user: User, action: str, reason: str
) -> None:
    """Admins cannot act on another admin's account; the attempt is audited, then refused."""
    if user.clerk_subject not in settings.admin_clerk_user_ids and user.role != "admin":
        return
    append_audit(
        session,
        admin_user_id=admin_id,
        action=f"{action}.denied",
        target_user_id=user.id,
        reason=reason,
        detail={"refused": "target_is_admin"},
    )
    session.commit()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "ADMIN_TARGET_PROTECTED", "message": "admins cannot act on another admin"},
    )


def suspend(
    session: Session, settings: Settings, admin_id: str, user_id: str, reason: str
) -> dict[str, Any]:
    if user_id == admin_id:
        raise _bad("admins cannot suspend themselves")
    user = _load_user(session, user_id)
    _refuse_admin_target(session, settings, admin_id, user, "user.suspend", reason)
    before = user.disabled
    user.disabled = True
    _revoke_all(session, user)
    append_audit(
        session,
        admin_user_id=admin_id,
        action="user.suspend",
        target_user_id=user.id,
        reason=reason,
        detail={"before": {"disabled": before}, "after": {"disabled": True}},
    )
    session.commit()
    return user_item(user, _subscription(session, user.account_id))


def unsuspend(session: Session, settings: Settings, admin_id: str, user_id: str, reason: str) -> dict[str, Any]:
    user = _load_user(session, user_id)
    _refuse_admin_target(session, settings, admin_id, user, "user.unsuspend", reason)
    before = user.disabled
    user.disabled = False
    append_audit(
        session,
        admin_user_id=admin_id,
        action="user.unsuspend",
        target_user_id=user.id,
        reason=reason,
        detail={"before": {"disabled": before}, "after": {"disabled": False}},
    )
    session.commit()
    return user_item(user, _subscription(session, user.account_id))


def revoke_sessions(
    session: Session,
    settings: Settings,
    admin_id: str,
    user_id: str,
    reason: str,
    clerk: ClerkBackend | None,
) -> dict[str, Any]:
    """End the user's Clerk sessions, then reject every token issued before now locally."""
    user = _load_user(session, user_id)
    clerk_revoked = 0
    if user.clerk_subject is not None:
        if clerk is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CLERK_SECRET_NOT_CONFIGURED",
                    "message": (
                        "revoking Clerk sessions needs DAILY_AGENT_CLERK_SECRET_KEY; "
                        "suspend the user instead to cut access"
                    ),
                },
            )
        try:
            clerk_revoked = clerk.revoke_user_sessions(user.clerk_subject)
        except ClerkBackendError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "CLERK_REVOKE_FAILED", "message": str(exc)},
            ) from exc
    _revoke_all(session, user)
    append_audit(
        session,
        admin_user_id=admin_id,
        action="user.revoke_sessions",
        target_user_id=user.id,
        reason=reason,
        detail={"token_version": user.token_version, "clerk_sessions_revoked": clerk_revoked},
    )
    session.commit()
    return {
        "revoked": True,
        "token_version": user.token_version,
        "clerk_sessions_revoked": clerk_revoked,
    }
def edit_user(
    session: Session,
    settings: Settings,
    admin_id: str,
    user_id: str,
    *,
    display_name: str | None,
    tester: bool | None,
    tester_label: str | None,
    admin_notes: str | None,
    reason: str,
) -> dict[str, Any]:
    user = _load_user(session, user_id)
    _refuse_admin_target(session, settings, admin_id, user, "user.edit", reason)
    before = {"display_name": user.display_name, "tester": user.tester, "tester_label": user.tester_label, "admin_notes": user.admin_notes}
    if display_name is not None:
        user.display_name = display_name.strip()
    if tester is not None:
        user.tester = tester
    if tester_label is not None:
        user.tester_label = tester_label or None
    if admin_notes is not None:
        user.admin_notes = admin_notes or None
    after = {"display_name": user.display_name, "tester": user.tester, "tester_label": user.tester_label, "admin_notes": user.admin_notes}
    append_audit(session, admin_user_id=admin_id, action="user.edit", target_user_id=user.id, reason=reason, detail={"before": before, "after": after})
    session.commit()
    return user_item(user, _subscription(session, user.account_id)) | {"admin_notes": user.admin_notes}



def change_tier(
    session: Session,
    settings: Settings,
    admin_id: str,
    user_id: str,
    tier: str | int,
    reason: str,
    expires_at: datetime | None = None,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    plan = parse_tier(tier)
    user = _load_user(session, user_id)
    _refuse_admin_target(session, settings, admin_id, user, "user.tier", reason)

    subscription = _subscription(session, user.account_id)
    if subscription is None:
        subscription = Subscription(account_id=user.account_id, plan_id="ananta")
        session.add(subscription)
        session.flush()
    old_policy = plan_policy(subscription)
    before = {
        "plan_id": subscription.plan_id,
        "status": subscription.status,
        "tier_expires_at": _iso(subscription.tier_expires_at),
        "revert_plan_id": subscription.revert_plan_id,
    }
    subscription.plan_id = plan
    subscription.status = "active"
    subscription.policy_version = "admin-override-v1"
    subscription.tier_expires_at = expires_at
    base_plan = subscription.revert_plan_id or old_policy.plan_id
    subscription.revert_plan_id = base_plan if expires_at is not None else None
    new_policy = SYNTHETIC_POLICIES[plan]
    # Entitlements only; billing is never touched. Re-base the live counters on the new plan.
    now = datetime.now(UTC)
    rebase_usage_window(session, user.account_id, new_policy, now)
    period = session.scalars(
        select(UsagePeriod)
        .where(UsagePeriod.account_id == user.account_id, UsagePeriod.reset_at > now)
        .order_by(UsagePeriod.reset_at)
    ).first()
    if period is not None:
        period.spend_limit_micro = max(
            0,
            new_policy.period_cost_cap_micro + (period.credit_adjust_micro or 0),
        )
    session.flush()
    sync_account_progression(session, user.account_id)
    append_audit(
        session,
        admin_user_id=admin_id,
        action="user.tier",
        target_user_id=user.id,
        reason=reason,
        detail={"before": before, "after": {"plan_id": plan, "tier": tier_for_plan(plan)}},
    )
    if commit:
        session.commit()
    return user_item(user, subscription)

def bulk_change_tier(
    session: Session,
    settings: Settings,
    admin_id: str,
    user_ids: list[str],
    tier: str | int,
    reason: str,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    if len(user_ids) > 100:
        raise _bad("user_ids cannot contain more than 100 users")
    if len(set(user_ids)) != len(user_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="user_ids must be unique")
    plan = parse_tier(tier)
    users = [session.get(User, uid) for uid in user_ids]
    if any(user is None for user in users):
        raise _not_found()
    for user in users:
        assert user is not None
        _refuse_admin_target(session, settings, admin_id, user, "user.bulk_tier", reason)
    for uid in user_ids:
        change_tier(session, settings, admin_id, uid, plan, reason, expires_at, commit=False)
    session.commit()
    return {"updated": len(user_ids), "user_ids": user_ids}


def adjust_credits(
    session: Session,
    settings: Settings,
    admin_id: str,
    user_id: str,
    *,
    delta_inr: float | None = None,
    budget_inr: float | None = None,
    reason: str,
) -> dict[str, Any]:
    user = _load_user(session, user_id)
    _refuse_admin_target(session, settings, admin_id, user, "user.credits", reason)
    subscription = _subscription(session, user.account_id)
    if subscription is None:
        subscription = Subscription(account_id=user.account_id, plan_id="ananta")
        session.add(subscription)
        session.flush()
    policy = plan_policy(subscription)
    period = ensure_usage_period(session, user.account_id, policy, subscription.period_anchor)
    before = period.spend_limit_micro
    if delta_inr is not None:
        adjustment = inr_to_micro(delta_inr)
        after = before + adjustment
        period.credit_adjust_micro = (period.credit_adjust_micro or 0) + adjustment
    else:
        after = inr_to_micro(budget_inr or 0.0)
        period.credit_adjust_micro = after - policy.period_cost_cap_micro
    used = period.reserved_micro + period.settled_micro
    if after < used:
        session.rollback()
        raise _bad("budget cannot be set below what the period has already used")
    period.spend_limit_micro = after
    append_audit(
        session,
        admin_user_id=admin_id,
        action="user.credits",
        target_user_id=user.id,
        reason=reason,
        detail={
            "before_budget_micro": before,
            "after_budget_micro": after,
            "delta_inr": delta_inr,
            "budget_inr": budget_inr,
        },
    )
    session.commit()
    return {
        "budget_inr": micro_to_inr(after),
        "credits_remaining": micro_to_inr(after - used),
    }


def export_user(session: Session, admin_id: str, user_id: str, reason: str) -> dict[str, Any]:
    user = _load_user(session, user_id)
    account = session.get(Account, user.account_id)
    subscription = _subscription(session, user.account_id)
    runs = session.scalars(
        select(Run).where(Run.user_id == user.id).order_by(Run.created_at.desc(), Run.id.desc())
    ).all()
    conversations = session.execute(
        select(Conversation, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .group_by(Conversation.id)
    ).all()
    tasks = session.scalars(select(Task).where(Task.owner_user_id == user.id)).all()
    reminders = session.scalars(select(Reminder).where(Reminder.owner_user_id == user.id)).all()
    periods = session.scalars(
        select(UsagePeriod).where(UsagePeriod.account_id == user.account_id)
    ).all()
    payload: dict[str, Any] = {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {
            **user_item(user, subscription),
            "role": user.role,
            "clerk_subject": user.clerk_subject,
            "active_theme": user.active_theme,
        },
        "account": {"id": user.account_id, "name": account.name if account else None},
        "subscription": {
            "plan_id": subscription.plan_id,
            "status": subscription.status,
            "policy_version": subscription.policy_version,
            "period_anchor": subscription.period_anchor.isoformat(),
        }
        if subscription
        else None,
        "usage_periods": [
            {
                "period_key": p.period_key,
                "spend_limit_micro": p.spend_limit_micro,
                "settled_micro": p.settled_micro,
                "reserved_micro": p.reserved_micro,
            }
            for p in periods
        ],
        "runs": [
            {
                "id": r.id,
                "status": r.status,
                "outcome": r.outcome,
                "created_at": _iso(r.created_at),
                "served_model": r.served_model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
            }
            for r in runs
        ],
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": _iso(c.created_at),
                "deleted_at": _iso(c.deleted_at),
                "message_count": count,
            }
            for c, count in conversations
        ],
        "tasks": [{"title": t.title, "completed": t.completed} for t in tasks],
        "reminders": [
            {"text": r.text, "due_at_utc": _iso(r.due_at_utc), "state": r.state} for r in reminders
        ],
        # Support never reads message bodies; the owner's own history export covers them.
        "message_bodies_included": False,
    }
    append_audit(
        session,
        admin_user_id=admin_id,
        action="user.export",
        target_user_id=user.id,
        reason=reason,
        detail={"runs": len(runs), "conversations": len(conversations)},
    )
    session.commit()
    return payload


def erase_user(
    session: Session, settings: Settings, admin_id: str, user_id: str, reason: str
) -> dict[str, Any]:
    """Irreversibly delete the user, their account and everything keyed to it.

    Rows are removed explicitly (children first) so erasure is complete even on engines
    that do not enforce ``ON DELETE CASCADE``. The audit trail keeps only the opaque ids.
    """
    if user_id == admin_id:
        raise _bad("admins cannot delete themselves")
    user = _load_user(session, user_id)
    _refuse_admin_target(session, settings, admin_id, user, "user.erase", reason)
    account_id = user.account_id
    others = session.scalar(
        select(func.count()).select_from(User).where(User.account_id == account_id, User.id != user.id)
    )
    if others:
        raise _bad("account is shared with other users; refusing to erase")
    run_ids = select(Run.id).where(Run.account_id == account_id)
    reservation_ids = select(BudgetReservation.id).where(BudgetReservation.account_id == account_id)
    conversation_ids = select(Conversation.id).where(Conversation.account_id == account_id)
    counts: dict[str, int] = {}

    def purge(name: str, statement: Any) -> None:
        result = session.execute(statement)
        counts[name] = int(getattr(result, "rowcount", 0) or 0)

    purge("message_feedback", delete(MessageFeedback).where(MessageFeedback.account_id == account_id))
    purge("outbox_events", delete(OutboxEvent).where(OutboxEvent.run_id.in_(run_ids)))
    purge("routing_records", delete(RoutingRecord).where(RoutingRecord.run_id.in_(run_ids)))
    purge("routing_decisions", delete(RoutingDecision).where(RoutingDecision.run_id.in_(run_ids)))
    purge("cost_ledger", delete(CostLedger).where(CostLedger.reservation_id.in_(reservation_ids)))
    purge("budget_reservations", delete(BudgetReservation).where(BudgetReservation.account_id == account_id))
    purge("billing_events", delete(BillingEvent).where(BillingEvent.account_id == account_id))
    session.execute(update(Run).where(Run.account_id == account_id).values(previous_run_id=None))
    purge("runs", delete(Run).where(Run.account_id == account_id))
    purge("chat_messages", delete(ChatMessage).where(ChatMessage.conversation_id.in_(conversation_ids)))
    purge("conversations", delete(Conversation).where(Conversation.account_id == account_id))
    purge("tasks", delete(Task).where(Task.account_id == account_id))
    purge("reminders", delete(Reminder).where(Reminder.account_id == account_id))
    purge("bug_reports", delete(BugReport).where(BugReport.account_id == account_id))
    purge("usage_windows", delete(UsageWindow).where(UsageWindow.account_id == account_id))
    purge("usage_periods", delete(UsagePeriod).where(UsagePeriod.account_id == account_id))
    purge("subscriptions", delete(Subscription).where(Subscription.account_id == account_id))
    purge("admin_sessions", delete(AdminSession).where(AdminSession.user_id == user.id))
    purge("admin_credentials", delete(AdminCredential).where(AdminCredential.user_id == user.id))
    if user.clerk_subject is not None:
        session.merge(
            ErasedClerkSubject(
                subject_hash=clerk_subject_digest(user.clerk_subject), erased_at=datetime.now(UTC)
            )
        )
    purge("users", delete(User).where(User.id == user.id))
    purge("accounts", delete(Account).where(Account.id == account_id))
    append_audit(
        session,
        admin_user_id=admin_id,
        action="user.erase",
        target_user_id=user_id,
        reason=reason,
        detail={"deleted_rows": counts},
    )
    session.commit()
    return {"deleted": True, "user_id": user_id}


def list_audit(session: Session, *, limit: int, cursor: str | None) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_PAGE))
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(limit + 1)
    if cursor:
        try:
            stmt = stmt.where(AdminAuditLog.id < int(cursor))
        except ValueError:
            raise _bad("invalid cursor") from None
    rows = session.scalars(stmt).all()
    page = rows[:limit]
    return {
        "items": [
            {
                "id": row.id,
                "at": _iso(row.at),
                "admin_user_id": row.admin_user_id,
                "action": row.action,
                "target_user_id": row.target_user_id,
                "reason": row.reason,
                "detail": json.loads(row.detail),
            }
            for row in page
        ],
        "next_cursor": str(page[-1].id) if len(rows) > limit and page else None,
    }


def list_runs(session: Session, *, limit: int, cursor: str | None) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_PAGE))
    stmt = select(Run).order_by(Run.created_at.desc(), Run.id.desc()).limit(limit + 1)
    if cursor:
        try:
            stamp, run_id = cursor.split("|", 1)
            at = as_utc(datetime.fromisoformat(stamp))
        except ValueError:
            raise _bad("invalid cursor") from None
        stmt = stmt.where(
            or_(Run.created_at < at, and_(Run.created_at == at, Run.id < run_id))
        )
    rows = session.scalars(stmt).all()
    page = rows[:limit]
    return {
        "items": [
            {
                "run_id": run.id,
                "status": run.status,
                "outcome": run.outcome,
                "created_at": _iso(run.created_at),
                "account_ref": hashlib.sha256(run.account_id.encode()).hexdigest()[:12],
                "served_model": run.served_model,
                "served_provider": run.served_provider,
                "latency_ms": run.latency_ms,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "response": "redacted",
            }
            for run in page
        ],
        "next_cursor": (
            f"{as_utc(page[-1].created_at).astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}"
            f"|{page[-1].id}"
            if len(rows) > limit and page
            else None
        ),
    }


class MonitorCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._at = 0.0
        self._value: dict[str, Any] | None = None

    def get(self, build: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            if self._value is None or now - self._at > MONITOR_CACHE_SECONDS:
                self._value = build()
                self._at = now
            value: dict[str, Any] = self._value
            return value


def build_monitor(
    session: Session, settings: Settings, gateway: Gateway, metrics: RequestMetrics
) -> dict[str, Any]:
    now = datetime.now(UTC)
    day_key, _reset = current_window_key(now)
    active_users = session.scalar(
        select(func.count()).select_from(User).where(User.last_active_at > now - ACTIVE_WINDOW)
    )
    budget = session.get(PlatformBudget, day_key)
    spent = (budget.settled_micro + budget.reserved_micro) if budget else 0
    limit = budget.spend_limit_micro if budget else settings.global_daily_budget_micro
    providers: Mapping[str, str] = {
        provider: (
            "disabled"
            if not gateway.live
            else "down"
            if gateway.health.provider_open(provider)
            else "ok"
        )
        for provider in sorted({model.provider for model in gateway.registry.models})
    }
    snapshot = metrics.snapshot()
    day_requests = session.get(GatewayRequestDay, day_key)
    requests_today = day_requests.requests_used if day_requests else 0
    daily_request_cap = settings.gateway_daily_request_limit

    today_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    total_runs_today = (
        session.scalar(
            select(func.count()).select_from(Run).where(Run.created_at >= today_start)
        )
        or 0
    )
    if total_runs_today > 0:
        successful_runs_today = (
            session.scalar(
                select(func.count()).select_from(Run).where(
                    Run.created_at >= today_start,
                    Run.status == RunStatus.COMPLETED,
                )
            )
            or 0
        )
        success_rate: float | None = round(successful_runs_today / total_runs_today, 4)
    else:
        success_rate = None

    open_bug_reports = (
        session.scalar(
            select(func.count()).select_from(BugReport).where(
                BugReport.status.notin_(["fixed", "closed", "duplicate", "wontfix"])
            )
        )
        or 0
    )

    since_24h = now - timedelta(hours=24)
    recent_runs = session.execute(
        select(
            Run.served_model,
            Run.served_provider,
            Run.status,
            Run.created_at,
            Run.latency_ms,
        ).where(
            Run.created_at >= since_24h,
            Run.served_model.is_not(None),
        )
    ).all()
    models_map: dict[tuple[str, str], list[Any]] = {
        (m.model_id, m.provider): [] for m in gateway.registry.models
    }
    for r in recent_runs:
        if r.served_model and r.served_provider:
            models_map.setdefault((r.served_model, r.served_provider), []).append(r)

    model_health = []
    for (model_id, provider), runs in sorted(models_map.items()):
        run_count = len(runs)
        if run_count > 0:
            successful = [r for r in runs if r.status == RunStatus.COMPLETED]
            last_success = max((r.created_at for r in successful), default=None)
            failed = [r for r in runs if r.status == RunStatus.FAILED]
            err_rate = round(len(failed) / run_count, 4)
            latencies = sorted(r.latency_ms for r in runs if r.latency_ms is not None)
            p50_ms: float | None = float(latencies[len(latencies) // 2]) if latencies else None
            last_success_str = _iso(last_success) if last_success else None
        else:
            last_success_str = None
            err_rate = 0.0
            p50_ms = None
        model_health.append(
            {
                "model": model_id,
                "provider": provider,
                "last_success_at": last_success_str,
                "error_rate": err_rate,
                "p50_latency_ms": p50_ms,
                "runs": run_count,
            }
        )

    return {
        "active_users": active_users or 0,
        "active_streams": get_stream_registry().active_count(),
        "req_per_min": snapshot["req_per_min"],
        "error_rate": snapshot["error_rate"],
        "p95_latency_ms": snapshot["p95_latency_ms"],
        "spend_today_inr": micro_to_inr(spent),
        "platform_budget_inr": micro_to_inr(limit),
        "cost_today_inr": micro_to_inr(spent),
        "requests_today": requests_today,
        "daily_request_cap": daily_request_cap,
        "success_rate": success_rate,
        "open_bug_reports": open_bug_reports,
        "model_health": model_health,
        "provider_health": [{"provider": p, "status": s} for p, s in providers.items()],
        "generated_at": now.isoformat(),
    }


ALLOWED_BUG_REPORT_STATUSES = {
    "new", "triaged", "in_progress", "fixed", "closed", "duplicate", "wontfix"
}

ALLOWED_BUG_REPORT_TRANSITIONS: dict[str, set[str]] = {
    "new": {"triaged", "duplicate", "wontfix", "closed"},
    "triaged": {"in_progress", "duplicate", "wontfix", "closed"},
    "in_progress": {"fixed", "wontfix", "closed"},
    "fixed": {"closed", "in_progress"},
    "duplicate": {"closed", "triaged"},
    "wontfix": {"closed", "triaged"},
    "closed": {"triaged"},
}


def list_bug_reports(
    session: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    limit: int = 25,
    cursor: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(limit, 100))
    stmt = (
        select(
            BugReport,
            User.display_name,
            (BugReport.screenshot.is_not(None)).label("has_screenshot"),
        )
        .options(defer(BugReport.screenshot))
        .outerjoin(User, User.id == BugReport.user_id)
        .order_by(BugReport.created_at.desc(), BugReport.id.desc())
        .limit(limit + 1)
    )
    if status:
        stmt = stmt.where(BugReport.status == status)
    if category:
        stmt = stmt.where(BugReport.category == category)
    if cursor:
        try:
            stamp, report_id = cursor.split("|", 1)
            at = as_utc(datetime.fromisoformat(stamp))
        except ValueError:
            raise _bad("invalid cursor") from None
        stmt = stmt.where(
            or_(
                BugReport.created_at < at,
                and_(BugReport.created_at == at, BugReport.id < report_id),
            )
        )
    rows = session.execute(stmt).all()
    page = rows[:limit]
    items = [
        {
            "id": report.id,
            "ticket": report.ticket,
            "category": report.category,
            "status": report.status,
            "description_preview": report.description[:140],
            "user_id": report.user_id,
            "user_display_name": display_name or "",
            "has_screenshot": bool(has_screenshot),
            "created_at": _iso(report.created_at),
            "updated_at": _iso(report.updated_at),
        }
        for report, display_name, has_screenshot in page
    ]
    next_cursor = (
        f"{as_utc(page[-1][0].created_at).astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}|{page[-1][0].id}"
        if len(rows) > limit and page
        else None
    )
    return {"items": items, "next_cursor": next_cursor}


def get_admin_bug_report(
    session: Session,
    admin_id: str,
    report_id: str,
) -> dict[str, Any]:
    report = session.get(BugReport, report_id)
    if report is None:
        raise _not_found()
    user = session.get(User, report.user_id)
    sub = _subscription(session, report.account_id)
    plan = plan_policy(sub).plan_id
    append_audit(
        session,
        admin_user_id=admin_id,
        action="bug_report.read",
        target_user_id=report.user_id,
        detail={"bug_report_id": report.id, "ticket": report.ticket},
    )
    session.commit()
    return {
        "id": report.id,
        "ticket": report.ticket,
        "category": report.category,
        "description": report.description,
        "diagnostics": report.diagnostics,
        "status": report.status,
        "admin_notes": report.admin_notes,
        "has_screenshot": report.screenshot is not None,
        "user": {
            "id": user.id if user else report.user_id,
            "display_name": user.display_name if user else "",
            "plan": plan,
        },
        "created_at": _iso(report.created_at),
        "updated_at": _iso(report.updated_at),
        "triaged_at": _iso(report.triaged_at) if report.triaged_at else None,
        "resolved_at": _iso(report.resolved_at) if report.resolved_at else None,
    }


def get_admin_bug_report_screenshot(
    session: Session,
    admin_id: str,
    report_id: str,
) -> tuple[bytes, str]:
    report = session.get(BugReport, report_id)
    if report is None or report.screenshot is None:
        raise _not_found()
    append_audit(
        session,
        admin_user_id=admin_id,
        action="bug_report.screenshot",
        target_user_id=report.user_id,
        detail={"bug_report_id": report.id, "ticket": report.ticket},
    )
    session.commit()
    return report.screenshot, report.screenshot_content_type or "image/png"


def patch_admin_bug_report(
    session: Session,
    admin_id: str,
    report_id: str,
    *,
    status: str | None,
    admin_notes: str | None,
    reason: str,
) -> dict[str, Any]:
    report = session.get(BugReport, report_id)
    if report is None:
        raise _not_found()
    now = datetime.now(UTC)
    if status is not None:
        if status not in ALLOWED_BUG_REPORT_STATUSES:
            raise _bad(f"unknown bug report status {status}")
        if status != report.status:
            allowed = ALLOWED_BUG_REPORT_TRANSITIONS.get(report.status, set())
            if status not in allowed:
                raise HTTPException(
                    status_code=409,
                    detail=f"invalid status transition from {report.status} to {status}",
                )
            if status == "triaged" and report.triaged_at is None:
                report.triaged_at = now
            if status in {"fixed", "closed", "duplicate", "wontfix"}:
                report.resolved_at = now
            elif status in {"triaged", "in_progress"}:
                report.resolved_at = None
            report.status = status
    if admin_notes is not None:
        report.admin_notes = admin_notes
    report.updated_at = now
    append_audit(
        session,
        admin_user_id=admin_id,
        action="bug_report.update",
        target_user_id=report.user_id,
        reason=reason,
        detail={"bug_report_id": report.id, "ticket": report.ticket, "status": report.status},
    )
    session.commit()
    user = session.get(User, report.user_id)
    sub = _subscription(session, report.account_id)
    plan = plan_policy(sub).plan_id
    return {
        "id": report.id,
        "ticket": report.ticket,
        "category": report.category,
        "description": report.description,
        "diagnostics": report.diagnostics,
        "status": report.status,
        "admin_notes": report.admin_notes,
        "has_screenshot": report.screenshot is not None,
        "user": {
            "id": user.id if user else report.user_id,
            "display_name": user.display_name if user else "",
            "plan": plan,
        },
        "created_at": _iso(report.created_at),
        "updated_at": _iso(report.updated_at),
        "triaged_at": _iso(report.triaged_at) if report.triaged_at else None,
        "resolved_at": _iso(report.resolved_at) if report.resolved_at else None,
    }

