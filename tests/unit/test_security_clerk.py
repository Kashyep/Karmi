from __future__ import annotations

import base64
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from daily_agent.config import Settings
from daily_agent.db import Base
from daily_agent.models import Account, Subscription, User
from daily_agent.security import issue_development_token, verify_token


@pytest.fixture
def clerk_context():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        clerk_issuer="https://example.clerk.accounts.dev",
        clerk_jwt_public_key_b64=base64.b64encode(public_pem).decode("ascii"),
    )
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield private_key, settings, session
    engine.dispose()


def issue_token(private_key, *, issuer: str = "https://example.clerk.accounts.dev", exp=None):
    now = int(time.time())
    claims = {
        "iss": issuer,
        "sub": "user_clerk_123",
        "sid": "sess_clerk_456",
        "iat": now - 1,
        "exp": exp if exp is not None else now + 300,
        "name": "Test User",
    }
    return jwt.encode(claims, private_key, algorithm="RS256")


def test_clerk_token_provisions_one_free_tenant_user(clerk_context) -> None:
    private_key, settings, session = clerk_context
    token = issue_token(private_key)

    principal = verify_token(token, settings, session)
    first_user_id = principal.user_id
    user = session.get(User, first_user_id)
    subscription = session.scalar(
        select(Subscription).where(Subscription.account_id == principal.account_id)
    )

    assert user is not None
    assert user.clerk_subject == "user_clerk_123"
    assert user.role == "customer"
    assert user.display_name == "Test User"
    assert subscription is not None and subscription.plan_id == "ananta"
    assert verify_token(token, settings, session).user_id == first_user_id
    assert session.scalar(select(User.id).where(User.clerk_subject == "user_clerk_123")) == first_user_id


@pytest.mark.parametrize(
    "kwargs",
    [
        {"issuer": "https://wrong.clerk.accounts.dev"},
        {"exp": int(time.time()) - 60},
    ],
)
def test_clerk_token_rejects_wrong_issuer_or_expiry(clerk_context, kwargs) -> None:
    private_key, settings, session = clerk_context
    with pytest.raises(HTTPException) as error:
        verify_token(issue_token(private_key, **kwargs), settings, session)
    assert error.value.status_code == 401


def test_clerk_verifier_rejects_wrong_signing_key(clerk_context) -> None:
    private_key, settings, session = clerk_context
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(HTTPException) as error:
        verify_token(issue_token(other_key), settings, session)
    assert error.value.status_code == 401


def test_local_development_token_still_works_when_clerk_is_configured(clerk_context) -> None:
    _private_key, settings, session = clerk_context
    account = Account(name="Local account")
    session.add(account)
    session.flush()
    user = User(account_id=account.id, display_name="Local user", role="customer")
    session.add_all((user, Subscription(account_id=account.id, plan_id="ananta")))
    session.commit()

    principal = verify_token(issue_development_token(user, settings), settings, session)

    assert principal.user_id == user.id
    assert principal.account_id == account.id
