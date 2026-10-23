"""Admin authentication: allowlisted Clerk identity + personal code + short server-side session.

Layers, all required: a valid Clerk bearer (same sign-in as customers), the Clerk subject in
``ADMIN_CLERK_USER_IDS``, ``users.role == 'admin'``, a personal code verified against a salted
scrypt hash, then an opaque 30-minute session token (only its SHA-256 is stored) sent as
``X-Admin-Session``. Nothing here is shipped to a client bundle.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from daily_agent.config import Settings, get_settings
from daily_agent.db import get_session
from daily_agent.models import AdminAuditLog, AdminCredential, AdminSession, User
from daily_agent.ratelimit import SlidingWindowLimiter
from daily_agent.security import Principal, as_utc, require_principal

CODE_MIN_LENGTH = 12
SESSION_TTL = timedelta(minutes=30)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)
ADMIN_RATE_LIMIT_PER_MINUTE = 300

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**14, 8, 1


class AdminCodeInvalid(Exception):
    """Wrong code (or no code enrolled): deliberately indistinguishable."""


class AdminLocked(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("admin sign-in locked")
        self.retry_after = retry_after


def validate_code(code: str) -> None:
    if len(code) < CODE_MIN_LENGTH or not (code.isascii() and code.isalnum()):
        raise ValueError(f"admin code must be at least {CODE_MIN_LENGTH} letters or digits")


def hash_code(code: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        code.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    salt_b64 = base64.b64encode(salt).decode()
    digest_b64 = base64.b64encode(digest).decode()
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_b64}${digest_b64}"


def verify_code(code: str, stored: str) -> bool:
    """Constant-time comparison of a scrypt digest; malformed hashes never verify."""
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            code.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_dummy_hash: str | None = None


def _dummy() -> str:
    # Hashed lazily so an unenrolled user costs the same scrypt time as a wrong code.
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_code(secrets.token_hex(8))
    return _dummy_hash


def stage_enroll_code(session: Session, user: User, code: str) -> None:
    """Create or rotate a developer's code; clears any lockout and revokes open sessions.

    Stages the change only: the caller commits, so enrollment and its audit row are atomic.
    """
    validate_code(code)
    now = datetime.now(UTC)
    credential = session.get(AdminCredential, user.id)
    if credential is None:
        session.add(AdminCredential(user_id=user.id, code_hash=hash_code(code), updated_at=now))
    else:
        credential.code_hash = hash_code(code)
        credential.failed_attempts = 0
        credential.locked_until = None
        credential.updated_at = now
    revoke_admin_sessions(session, user.id)


def enroll_code(session: Session, user: User, code: str) -> None:
    stage_enroll_code(session, user, code)
    session.commit()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def revoke_admin_sessions(session: Session, user_id: str) -> None:
    session.execute(
        update(AdminSession)
        .where(AdminSession.user_id == user_id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


def append_audit(
    session: Session,
    *,
    admin_user_id: str,
    action: str,
    target_user_id: str | None = None,
    reason: str | None = None,
    detail: dict[str, object] | None = None,
) -> None:
    """Stage one audit row; the caller commits it atomically with the action it records."""
    session.add(
        AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            target_user_id=target_user_id,
            reason=reason,
            detail=json.dumps(detail or {}, sort_keys=True, default=str),
        )
    )


def forbid_unless_admin(session: Session, settings: Settings, principal: Principal) -> User:
    """Role admin AND allowlisted Clerk subject; same 403 for every failure."""
    user = session.get(User, principal.user_id)
    allowed = (
        user is not None
        and user.role == "admin"
        and not user.disabled
        and user.clerk_subject is not None
        and user.clerk_subject in settings.admin_clerk_user_ids
    )
    if not allowed or user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "ADMIN_FORBIDDEN", "message": "admin access denied"},
        )
    return user


def open_session(session: Session, user: User, code: str) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    # Row lock (FOR UPDATE): concurrent guesses for one developer serialise here, so the lockout
    # check and the failure count cannot race past MAX_FAILED_ATTEMPTS.
    credential = session.scalar(
        select(AdminCredential)
        .where(AdminCredential.user_id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if credential is not None and credential.locked_until is not None:
        remaining = as_utc(credential.locked_until) - now
        if remaining > timedelta(0):
            raise AdminLocked(max(1, int(remaining.total_seconds()) + 1))
    matches = verify_code(code, credential.code_hash if credential else _dummy())
    if credential is None or not matches:
        if credential is not None:
            # Atomic increment: parallel guesses cannot dodge the counter.
            session.execute(
                update(AdminCredential)
                .where(AdminCredential.user_id == user.id)
                .values(failed_attempts=AdminCredential.failed_attempts + 1)
            )
            session.refresh(credential)
            locked = credential.failed_attempts >= MAX_FAILED_ATTEMPTS
            if locked:
                credential.locked_until = now + LOCKOUT
                credential.failed_attempts = 0
            append_audit(
                session,
                admin_user_id=user.id,
                action="admin.lockout" if locked else "admin.login_failed",
            )
            session.commit()
            if locked:
                raise AdminLocked(int(LOCKOUT.total_seconds()))
        raise AdminCodeInvalid
    credential.failed_attempts = 0
    credential.locked_until = None
    token = secrets.token_urlsafe(32)
    expires_at = now + SESSION_TTL
    session.add(
        AdminSession(
            user_id=user.id, token_hash=token_digest(token), created_at=now, expires_at=expires_at
        )
    )
    append_audit(session, admin_user_id=user.id, action="admin.login")
    session.commit()
    return token, expires_at


def find_session(session: Session, user_id: str, token: str | None) -> AdminSession | None:
    if not token:
        return None
    found = session.scalar(
        select(AdminSession).where(AdminSession.token_hash == token_digest(token))
    )
    if (
        found is None
        or found.user_id != user_id
        or found.revoked_at is not None
        or as_utc(found.expires_at) <= datetime.now(UTC)
    ):
        return None
    return found


@dataclass(frozen=True)
class AdminContext:
    user: User
    session_row: AdminSession


def admin_identity(
    request: Request,
    principal: Principal = Depends(require_principal),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Clerk bearer + allowlist + role (no admin session yet): used by the sign-in endpoints."""
    user = forbid_unless_admin(session, settings, principal)
    limiter: SlidingWindowLimiter | None = getattr(request.app.state, "admin_limiter", None)
    if limiter is None:
        limiter = SlidingWindowLimiter(limit=ADMIN_RATE_LIMIT_PER_MINUTE)
        request.app.state.admin_limiter = limiter
    retry_after = limiter.check(user.id)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "too many admin requests"},
            headers={"Retry-After": str(retry_after)},
        )
    return user


def require_admin_session(
    user: User = Depends(admin_identity),
    session: Session = Depends(get_session),
    x_admin_session: str | None = Header(default=None),
) -> AdminContext:
    row = find_session(session, user.id, x_admin_session)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "ADMIN_SESSION_REQUIRED", "message": "admin session missing or expired"},
        )
    return AdminContext(user=user, session_row=row)
