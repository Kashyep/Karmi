# Admin backend (`/v1/admin/*`)

Operator API for the admin dashboard. Four independent gates, all required:

1. A valid Clerk bearer token (same sign-in as customers).
2. The Clerk subject is listed in `ADMIN_CLERK_USER_IDS` (comma-separated `user_...` ids;
   `DAILY_AGENT_ADMIN_CLERK_USER_IDS` also works). Empty means nobody is admin.
3. `users.role = 'admin'` (set directly in the database; there is no API to grant it).
4. A personal code, exchanged via `POST /v1/admin/session {code}` for an opaque 30-minute
   `admin_session_token`, sent afterwards as `X-Admin-Session` alongside the Bearer token.

Failure behavior: not allowlisted / not admin -> `403`; wrong code or no code enrolled -> `401`
(indistinguishable); 5 wrong codes -> `423 {retry_after}` for 15 minutes (persisted in
`admin_credentials`, survives restarts); missing/expired session -> `401 ADMIN_SESSION_REQUIRED`.

## Environment

| Variable | Meaning |
| --- | --- |
| `ADMIN_CLERK_USER_IDS` | Allowlisted Clerk subjects. Server-side only; never in client bundles. |
| `DAILY_AGENT_ADMIN_MICRO_PER_USD` | Budget-unit micros per displayed "USD" in the admin API (default `1000000`, i.e. the stored budget unit shown 1:1). |

## Enrolling or rotating a developer code

```
ADMIN_CLERK_USER_IDS=user_abc python scripts/admin_set_code.py --clerk-subject user_abc [--generate]
```

The code (>= 12 letters/digits) is read from a hidden prompt, or generated and printed once. Only a
salted scrypt hash is stored. Rotation clears any lockout and ends that developer's open sessions.

## Audit and erasure

Every mutation (suspend, unsuspend, revoke-sessions, tier, credits, erase), export, per-user read and
sign-in event appends a row to `admin_audit_log` in the same transaction. The table is append-only:
database triggers (PostgreSQL and SQLite) refuse UPDATE/DELETE and the ORM refuses them too. It has
no foreign keys, so rows outlive erased users. Erasure (`DELETE /v1/admin/users/{id}` with
`confirm: "DELETE"`) removes the user, account and everything keyed to them; message bodies are never
exposed by any admin endpoint.

Suspension sets `users.disabled` and revokes sessions: every later request from that user gets
`403 ACCOUNT_SUSPENDED`. "Revoke sessions" bumps `token_version` and stamps `sessions_revoked_at`;
Clerk tokens issued at or before that instant are rejected.

## Monitor

`GET /v1/admin/monitor` is safe to poll every 5 s: request metrics are in-process counters
(per replica), the response is cached for 4 s, and the only database reads are two indexed lookups.
