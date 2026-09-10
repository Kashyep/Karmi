import hashlib
import hmac
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from daily_agent.config import Settings, get_settings
from daily_agent.db import get_session
from daily_agent.models import User


@dataclass(frozen=True)
class Principal:
    user_id: str
    account_id: str
    role: str


def issue_development_token(user: User, settings: Settings, ttl_seconds: int = 3600) -> str:
    expires = int(time.time()) + ttl_seconds
    body = f"{user.id}|{user.role}|{expires}"
    signature = hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}|{signature}"


def verify_token(token: str, settings: Settings, session: Session) -> Principal:
    try:
        user_id, role, expires_text, supplied = token.split("|", 3)
        expires = int(expires_text)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session") from exc
    body = f"{user_id}|{role}|{expires}"
    expected = hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied) or expires < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    user = session.get(User, user_id)
    if user is None or user.role != role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    return Principal(user_id=user.id, account_id=user.account_id, role=user.role)


def require_principal(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return verify_token(authorization[7:], settings, session)


def require_admin(principal: Principal = Depends(require_principal)) -> Principal:
    if principal.role not in {"admin", "support"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return principal


def verify_hmac(raw_body: bytes, supplied: str | None, secret: str) -> None:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if supplied is None or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

