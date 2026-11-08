"""Minimal Clerk Backend API client: lists a user's active sessions and revokes them.

Revoking at Clerk ends the sessions there, so a stolen Clerk token stops working at the
identity provider; the local ``sessions_revoked_at`` iat check covers tokens already issued.
"""

from __future__ import annotations

import httpx
from fastapi import Depends

from daily_agent.config import Settings, get_settings

CLERK_API_BASE_URL = "https://api.clerk.com/v1"
_PAGE_SIZE = 100
_MAX_PAGES = 20
_TIMEOUT_SECONDS = 10.0


class ClerkBackendError(Exception):
    """Clerk did not confirm the revocation; nothing local should be marked as done."""


class ClerkBackend:
    def __init__(self, secret_key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._secret_key = secret_key
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=CLERK_API_BASE_URL,
            headers={"Authorization": f"Bearer {self._secret_key}"},
            timeout=_TIMEOUT_SECONDS,
            transport=self._transport,
        )

    def revoke_user_sessions(self, clerk_user_id: str) -> int:
        """Revoke every active Clerk session of the user; returns how many were revoked."""
        with self._client() as client:
            session_ids = self._active_session_ids(client, clerk_user_id)
            for session_id in session_ids:
                response = client.post(f"/sessions/{session_id}/revoke")
                # A session that ended between listing and revoking is already gone.
                if response.status_code not in (200, 404):
                    raise ClerkBackendError(f"Clerk refused to revoke a session ({response.status_code})")
            return len(session_ids)

    def _active_session_ids(self, client: httpx.Client, clerk_user_id: str) -> list[str]:
        ids: list[str] = []
        for page in range(_MAX_PAGES):
            response = client.get(
                "/sessions",
                params={
                    "user_id": clerk_user_id,
                    "status": "active",
                    "limit": _PAGE_SIZE,
                    "offset": page * _PAGE_SIZE,
                },
            )
            if response.status_code != 200:
                raise ClerkBackendError(f"Clerk session lookup failed ({response.status_code})")
            body = response.json()
            rows = body.get("data", []) if isinstance(body, dict) else body
            if not isinstance(rows, list):
                raise ClerkBackendError("Clerk session lookup returned an unexpected shape")
            ids.extend(str(row["id"]) for row in rows if isinstance(row, dict) and "id" in row)
            if len(rows) < _PAGE_SIZE:
                return ids
        raise ClerkBackendError("Clerk returned more active sessions than the revoke limit")


def get_clerk_backend(settings: Settings = Depends(get_settings)) -> ClerkBackend | None:
    """None when no Clerk secret is configured; callers must then refuse session revocation."""
    if not settings.clerk_secret_key:
        return None
    return ClerkBackend(settings.clerk_secret_key)
