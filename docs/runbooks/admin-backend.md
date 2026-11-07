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
| `DAILY_AGENT_ADMIN_UI_ENABLED` | Gates `/admin` and its static assets (`admin.js`, `admin.css`). Defaults to `true`. When set to `false`, `/admin` and admin assets return 404. |
| `DAILY_AGENT_CLERK_SECRET_KEY` | Clerk Backend API secret (`sk_...`), server-side only, never logged or shipped to a client. Needed for admin "revoke sessions". Unset means revocation is refused (see below). |

## Revoking sessions

`POST /v1/admin/users/{id}/revoke-sessions {reason}` ends the user's active Clerk sessions through the
Clerk Backend API, then bumps `token_version` locally so every Clerk token issued before now is rejected.
The order matters: Clerk is called first, and local state changes only after Clerk succeeds.

- **409 `CLERK_SECRET_NOT_CONFIGURED`**: the target has a Clerk subject but `DAILY_AGENT_CLERK_SECRET_KEY`
  is unset. Nothing is revoked and nothing is audited. Suspend the user instead to cut access.
- **502 `CLERK_REVOKE_FAILED`**: the Clerk API call failed (listing or revoking). Local state is untouched,
  so the request is safe to retry once Clerk is reachable again.
- A user without a Clerk subject (local development account) skips Clerk and is revoked locally only.

## Peer-admin guard

Suspend, tier change and erase refuse another admin. An admin cannot act on an allowlisted subject or any
`role = 'admin'` user through those actions; the request gets `403 ADMIN_TARGET_PROTECTED`. The attempt is
itself audited as `<action>.denied` with `refused: target_is_admin` before the refusal is returned. Self-targeting
suspend is refused separately. Unsuspend, revoke-sessions, credits and export do not carry this guard.

## Erased-subject tombstones

Erasing a user (`DELETE /v1/admin/users/{id}` with `confirm: "DELETE"`) stores a tombstone in
`erased_clerk_subjects`: the SHA-256 digest of the Clerk subject, never the raw id. When a later sign-in
presents that subject and no user row exists, the request gets `403 ACCOUNT_ERASED` and no account is
re-provisioned. The tombstone is keyed by digest, so it survives the user row being deleted.

## Enrolling or rotating a developer code

```
ADMIN_CLERK_USER_IDS=user_abc python scripts/admin_set_code.py --clerk-subject user_abc [--generate]
```

The code (>= 12 letters/digits) is read from a hidden prompt, or generated and printed once. Only a
salted scrypt hash is stored. Rotation clears any lockout and ends that developer's open sessions.

The credential change and its `admin.code_set` audit row are staged in one transaction and committed
together. If the audit insert fails, the transaction rolls back and the previous code, lockout state and
open sessions stay as they were.

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

## Removed legacy routes

The unversioned `GET /admin/overview` and `GET /admin/runs` routes are removed; there is no
compatibility alias. Use the versioned endpoints instead: `GET /v1/admin/monitor` for health and
`GET /v1/admin/runs` (cursor-paged) for run listings. Requests to the old unversioned paths are not routed.

## Monitor

`GET /v1/admin/monitor` is safe to poll every 5 s: request metrics are in-process counters
(per replica), the response is cached for 4 s, and the only database reads are two indexed lookups.

## Dashboard page

`GET /admin` serves the operator page with `Content-Security-Policy` limiting scripts to `'self'` and the
Clerk frontend host encoded in the publishable key, `frame-ancestors 'none'`, `object-src 'none'`,
`base-uri 'none'`, plus `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`. The Clerk browser bundle
is pinned to an exact version (`CLERK_JS_VERSION` in `admin.js`, currently `5.125.11`); never use a floating
major range such as `@5`.

When Clerk is configured, `style-src` permits `'self' 'unsafe-inline'`. Clerk's frontend bundle
(`clerk.mountSignIn`) injects dynamic `<style>` elements and applies inline `style` attributes at runtime.
Because Clerk's dynamic CSS-in-JS does not support CSP hashes or nonces in vanilla JS mounts,
`'unsafe-inline'` is the minimum directive required for the sign-in UI to render. Scripts remain strictly
controlled without `'unsafe-eval'` or wildcard origins (`*`). When no Clerk key is configured, `style-src`
reverts to strict `'self'`.

The dashboard page and its assets can be disabled by setting `DAILY_AGENT_ADMIN_UI_ENABLED=false` (or `ADMIN_UI_ENABLED=false`), returning 404. To support authenticated bug report screenshot viewing via blob URLs, `img-src` allows `blob:`.

## Access-log redaction (F-05)

The server access log (`uvicorn.access`) records the client address, HTTP method, request path
(including query strings), protocol version, and HTTP status code (along with response timing).

Sensitive credentials and headers are protected from log leakage:
- **Tokens and credentials:** `install_log_redaction()` installs a custom `LogRecordFactory`
  (`src/daily_agent/ratelimit.py`) that filters log messages and string arguments at record creation
  time. It automatically redacts Bearer tokens (`bearer <token>`), secret API keys (`sk-...`),
  JWTs (`eyJ...`), secret parameters (`TOKEN=...`, `API_KEY=...`, `PASSWORD=...`, `SECRET=...`),
  and database credentials in connection strings.
- **Headers:** Request headers—including `Authorization`, `Cookie`, `X-Admin-Session`, and
  `X-Admin-Reason`—are omitted from access log lines by default.
- **Reason values:** Operator reasons (e.g. for `GET /v1/admin/users/{uid}/export`) are passed
  exclusively in the `X-Admin-Reason` header rather than query strings. Because headers are not logged
  by access formatters, private justification notes do not leak into access logs.

Request paths (excluding headers), HTTP response status codes, and request timing are not redacted and
remain available for operational monitoring and debugging.
