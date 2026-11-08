"""E2E tests verifying Clerk SSO identity resolution and Ananta customer provisioning."""

from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from daily_agent.config import Settings
from daily_agent.models import Account, Subscription, User

pytestmark = pytest.mark.e2e

CLERK_TEST_ISSUER = "https://clerk.example.com"


@pytest.fixture
def clerk_auth_issuer(
    test_context: dict[str, object],
) -> Callable[..., str]:
    """Configure Clerk JWT settings on test context and return a token issuer function."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    settings = test_context["settings"]
    assert isinstance(settings, Settings)
    settings.clerk_issuer = CLERK_TEST_ISSUER
    settings.clerk_jwt_public_key_b64 = base64.b64encode(public_pem).decode("ascii")

    def issue_token(
        subject: str,
        *,
        session_id: str = "sess_sso_test",
        name: str | None = "SSO User",
        issued_at: int | None = None,
        expires_at: int | None = None,
    ) -> str:
        now = int(time.time())
        iat = issued_at if issued_at is not None else now
        exp = expires_at if expires_at is not None else iat + 3600
        claims: dict[str, Any] = {
            "iss": CLERK_TEST_ISSUER,
            "sub": subject,
            "sid": session_id,
            "iat": iat,
            "exp": exp,
        }
        if name is not None:
            claims["name"] = name
        return jwt.encode(claims, private_key, algorithm="RS256")

    return issue_token


def _client(test_context: dict[str, object]) -> TestClient:
    client = test_context["client"]
    assert isinstance(client, TestClient)
    return client


def _factory(test_context: dict[str, object]) -> sessionmaker:
    factory = test_context["factory"]
    assert isinstance(factory, sessionmaker)
    return factory


def test_same_clerk_sub_reuses_user_and_account_without_duplicates(
    test_context: dict[str, object],
    clerk_auth_issuer: Callable[..., str],
) -> None:
    """Two authenticated requests with the same Clerk sub resolve to the same user and account."""
    client = _client(test_context)
    factory = _factory(test_context)
    sub = "user_google_oauth_arjun"

    # 1. First sign-in / session (e.g. Google OAuth initial completion)
    token_1 = clerk_auth_issuer(sub, session_id="sess_google_1", name="Arjun Sharma")
    res_profile_1 = client.get("/v1/user/profile", headers={"Authorization": f"Bearer {token_1}"})
    assert res_profile_1.status_code == 200, res_profile_1.text
    profile_1 = res_profile_1.json()
    assert profile_1["display_name"] == "Arjun Sharma"
    user_id_1 = profile_1["id"]

    res_usage_1 = client.get("/v1/usage", headers={"Authorization": f"Bearer {token_1}"})
    assert res_usage_1.status_code == 200, res_usage_1.text
    assert res_usage_1.json()["plan_id"] == "ananta"

    with factory() as session:
        user_count_1 = session.scalar(select(func.count(User.id)))
        account_count_1 = session.scalar(select(func.count(Account.id)))
        sub_count_1 = session.scalar(select(func.count(Subscription.id)))
        assert user_count_1 == 1
        assert account_count_1 == 1
        assert sub_count_1 == 1

        db_user_1 = session.scalar(select(User).where(User.clerk_subject == sub))
        assert db_user_1 is not None
        assert db_user_1.id == user_id_1
        account_id_1 = db_user_1.account_id

        db_sub = session.scalar(select(Subscription).where(Subscription.account_id == account_id_1))
        assert db_sub is not None
        assert db_sub.plan_id == "ananta"

    # 2. Subsequent sign-in / request with same Clerk sub (e.g. new session or subsequent call)
    token_2 = clerk_auth_issuer(sub, session_id="sess_google_2", name="Arjun Sharma")
    res_profile_2 = client.get("/v1/user/profile", headers={"Authorization": f"Bearer {token_2}"})
    assert res_profile_2.status_code == 200, res_profile_2.text
    profile_2 = res_profile_2.json()
    assert profile_2["id"] == user_id_1
    assert profile_2["display_name"] == "Arjun Sharma"

    res_usage_2 = client.get("/v1/usage", headers={"Authorization": f"Bearer {token_2}"})
    assert res_usage_2.status_code == 200, res_usage_2.text
    assert res_usage_2.json()["plan_id"] == "ananta"

    # 3. Assert counts: no duplicate rows in users, accounts, or subscriptions
    with factory() as session:
        user_count_2 = session.scalar(select(func.count(User.id)))
        account_count_2 = session.scalar(select(func.count(Account.id)))
        sub_count_2 = session.scalar(select(func.count(Subscription.id)))
        assert user_count_2 == 1
        assert account_count_2 == 1
        assert sub_count_2 == 1

        db_user_2 = session.scalar(select(User).where(User.clerk_subject == sub))
        assert db_user_2 is not None
        assert db_user_2.id == user_id_1
        assert db_user_2.account_id == account_id_1


def test_distinct_clerk_sub_provisions_fresh_ananta_customer(
    test_context: dict[str, object],
    clerk_auth_issuer: Callable[..., str],
) -> None:
    """A new Clerk sub provisions a fresh Ananta customer with distinct user and account IDs."""
    client = _client(test_context)
    factory = _factory(test_context)

    sub_alpha = "user_google_oauth_alpha"
    sub_beta = "user_google_oauth_beta"

    # 1. Provision first customer (Alpha)
    token_alpha = clerk_auth_issuer(sub_alpha, session_id="sess_alpha", name="Alpha User")
    res_alpha = client.get("/v1/user/profile", headers={"Authorization": f"Bearer {token_alpha}"})
    assert res_alpha.status_code == 200, res_alpha.text
    alpha_user_id = res_alpha.json()["id"]

    res_alpha_usage = client.get("/v1/usage", headers={"Authorization": f"Bearer {token_alpha}"})
    assert res_alpha_usage.status_code == 200
    assert res_alpha_usage.json()["plan_id"] == "ananta"

    # 2. Provision second customer (Beta) with a new Clerk sub
    token_beta = clerk_auth_issuer(sub_beta, session_id="sess_beta", name="Beta User")
    res_beta = client.get("/v1/user/profile", headers={"Authorization": f"Bearer {token_beta}"})
    assert res_beta.status_code == 200, res_beta.text
    beta_user_id = res_beta.json()["id"]

    res_beta_usage = client.get("/v1/usage", headers={"Authorization": f"Bearer {token_beta}"})
    assert res_beta_usage.status_code == 200
    assert res_beta_usage.json()["plan_id"] == "ananta"

    # IDs must be different
    assert alpha_user_id != beta_user_id

    # 3. Assert database state: exactly 2 users, 2 accounts, 2 subscriptions
    with factory() as session:
        user_count = session.scalar(select(func.count(User.id)))
        account_count = session.scalar(select(func.count(Account.id)))
        sub_count = session.scalar(select(func.count(Subscription.id)))
        assert user_count == 2
        assert account_count == 2
        assert sub_count == 2

        alpha_user = session.scalar(select(User).where(User.clerk_subject == sub_alpha))
        beta_user = session.scalar(select(User).where(User.clerk_subject == sub_beta))
        assert alpha_user is not None
        assert beta_user is not None
        assert alpha_user.id == alpha_user_id
        assert beta_user.id == beta_user_id
        assert alpha_user.account_id != beta_user.account_id

        alpha_sub = session.scalar(
            select(Subscription).where(Subscription.account_id == alpha_user.account_id)
        )
        beta_sub = session.scalar(
            select(Subscription).where(Subscription.account_id == beta_user.account_id)
        )
        assert alpha_sub is not None
        assert beta_sub is not None
        assert alpha_sub.plan_id == "ananta"
        assert beta_sub.plan_id == "ananta"
