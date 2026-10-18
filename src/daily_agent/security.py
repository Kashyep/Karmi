import base64
import binascii
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daily_agent.config import Settings, get_settings
from daily_agent.db import get_session
from daily_agent.models import Account, Subscription, User

logger = logging.getLogger(__name__)

# Maximum accepted clock skew between sender and receiver on signed events.
MAX_EVENT_AGE_SECONDS = 300


@dataclass(frozen=True)
class Principal:
    user_id: str
    account_id: str
    role: str


def issue_development_token(user: User, settings: Settings, ttl_seconds: int = 3600) -> str:
    expires = int(time.time()) + ttl_seconds
    body = f"{user.id}|{user.role}|{expires}|{user.token_version}"
    signature = hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}|{signature}"


def verify_token(token: str, settings: Settings, session: Session) -> Principal:
    if "." in token:
        return verify_clerk_token(token, settings, session)
    if not settings.allow_development_auth or not settings.is_development:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    try:
        user_id, role, expires_text, version_text, supplied = token.split("|", 4)
        expires = int(expires_text)
        token_version = int(version_text)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session") from exc
    body = f"{user_id}|{role}|{expires}|{token_version}"
    expected = hmac.new(settings.auth_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    # `expires <= now`: a token is invalid from the start of its expiry second.
    if not hmac.compare_digest(expected, supplied) or expires <= int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    user = session.get(User, user_id)
    if user is None or user.role != role or user.token_version != token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    return Principal(user_id=user.id, account_id=user.account_id, role=user.role)


def verify_clerk_token(token: str, settings: Settings, session: Session) -> Principal:
    """Validate a Clerk session JWT, then resolve its immutable subject to a tenant user."""
    issuer = settings.clerk_issuer
    encoded_key = settings.clerk_jwt_public_key_b64
    if not issuer or not encoded_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    try:
        public_key = base64.b64decode(encoded_key, validate=True).decode("ascii")
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            leeway=30,
            options={"require": ["exp", "iat", "iss", "sub", "sid"]},
        )
        subject = claims["sub"]
        session_id = claims["sid"]
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise ValueError("invalid subject")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("invalid session id")
    except (jwt.PyJWTError, ValueError, UnicodeDecodeError, binascii.Error, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session") from exc

    user = session.scalar(select(User).where(User.clerk_subject == subject))
    if user is None:
        display_name = claims.get("name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = "Karmi user"
        display_name = display_name.strip()[:120]
        account = Account(name=f"{display_name[:108]}'s account")
        session.add(account)
        session.flush()
        user = User(
            account_id=account.id,
            clerk_subject=subject,
            display_name=display_name,
            role="customer",
        )
        session.add_all((user, Subscription(account_id=account.id, plan_id="ananta")))
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            user = session.scalar(select(User).where(User.clerk_subject == subject))
            if user is None:
                logger.exception("failed to provision Clerk subject")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="account setup temporarily unavailable",
                ) from exc
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
    if principal.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return principal


def verify_hmac(raw_body: bytes, supplied: str | None, secret: str) -> None:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if supplied is None or not hmac.compare_digest(expected, supplied):
        logger.warning("rejected request with invalid signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")


def verify_event_signature(
    raw_body: bytes,
    event_id: str,
    timestamp: str,
    supplied: str | None,
    secret: str,
    *,
    max_age_seconds: int = MAX_EVENT_AGE_SECONDS,
) -> None:
    """Verify an HMAC that binds the body, event id, and timestamp.

    The signature covers ``{event_id}.{timestamp}.{body}``, so a captured
    signature cannot be replayed under a different event id, and stale
    events are rejected outright.
    """
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid event timestamp"
        ) from exc
    if abs(time.time() - ts) > max_age_seconds:
        logger.warning("rejected stale event id=%s ts=%s", event_id, timestamp)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="stale event timestamp"
        )
    signable = f"{event_id}.{timestamp}.".encode() + raw_body
    verify_hmac(signable, supplied, secret)
