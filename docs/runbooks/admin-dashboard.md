# Admin dashboard runbook

This runbook covers the Karmi Release 1 admin dashboard on the web and in the app. Admin operations are destructive or affect tester access; use a specific reason for every mutation and verify the target before submitting.

## Access model

Every admin request requires all of the following:

1. A valid Clerk bearer token.
2. The Clerk subject is present in the server-side `ADMIN_CLERK_USER_IDS` comma-separated allowlist.
3. The local user has `role = 'admin'`.
4. A current personal admin session, created with the personal code and sent as `X-Admin-Session`.

The server also accepts `DAILY_AGENT_ADMIN_CLERK_USER_IDS` as the legacy/configuration alias documented by the backend runbook. An empty allowlist means nobody is an admin. Never put either allowlist or a Clerk secret in a client bundle or in source control.

## Sign in

### PC / web

1. Open the backend's `/admin` page on the configured HTTPS host.
2. Sign in with the Clerk account that is allowlisted and has the local admin role.
3. Enter that administrator's personal code when prompted. The resulting session is presented as `X-Admin-Session` for admin API requests.
4. Confirm that the dashboard loads users and monitor data before making a change.

The backend serves `/admin` with a restrictive CSP, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`. The Clerk browser bundle is pinned to an exact version. The deployed web hostname and the exact browser UI labels are **PENDING**.

### App

1. Open the administrator dashboard in the Karmi app.
2. Sign in with the same allowlisted Clerk account.
3. Complete personal-code verification and confirm the user list/monitor view appears.

The required authentication gates are the same as on PC: Clerk bearer token, allowlist, local admin role, and `X-Admin-Session`. The exact app navigation path and whether the app embeds or links to `/admin` are **PENDING**; do not infer a separate mobile credential or bypass.

## Enroll or rotate a personal code

Run the script from the repository root. First verify the current flags:

```sh
python scripts/admin_set_code.py --help
```

The verified usage is:

```text
usage: admin_set_code.py [-h] --clerk-subject CLERK_SUBJECT [--generate]
```

Enroll or rotate an interactively entered code:

```sh
ADMIN_CLERK_USER_IDS=user_abc \
  python scripts/admin_set_code.py --clerk-subject user_abc
```

Generate a strong code and print it once:

```sh
ADMIN_CLERK_USER_IDS=user_abc \
  python scripts/admin_set_code.py --clerk-subject user_abc --generate
```

`--clerk-subject` is required. Codes must be at least 12 letters/digits; the script stores only a salted scrypt hash. Rotation clears lockout and ends that administrator's open admin sessions. Store the plaintext code in the approved password manager; never commit it or paste it into logs. Five incorrect attempts lock the credential for 15 minutes.

The code change and its `admin.code_set` audit row commit together. If audit insertion fails, the prior code, lockout state, and sessions remain unchanged.

## Azure configuration

Set `ADMIN_CLERK_USER_IDS` on the Azure Container App/server environment to a comma-separated list of approved Clerk `user_...` subjects. Apply the setting through the deployment secret/configuration mechanism; never commit an `.env` file or print the value. Restart or roll the app as required by the deployment platform, then sign in and verify `/admin` and an admin API read. The exact Azure resource/revision to edit is **PENDING** for the target deployment; the deployment runbook identifies the current beta resource as `rg-karmi-prod` / `karmi-beta` in `eastasia`.

## Tester and plan operations

Use the dashboard's user list and detail view to confirm the target, then supply a reason before every mutation. The fixed admin API contract is:

- `PATCH /v1/admin/users/{id}` — update optional `display_name`, `tester`, `tester_label`, or `admin_notes`; `reason` is required.
- `POST /v1/admin/users/{id}/tier` — set `tier`, with required `reason` and optional future UTC ISO-8601 `expires_at`.
- `POST /v1/admin/users/bulk-tier` — set a tier for 1–100 `user_ids`, with required `reason` and optional expiry; response is `{updated, user_ids}`.
- `GET /v1/admin/users` — filter/query users, including `tester_label`, `suspended`, and `plan_expiring_before`.

User list/detail responses include `tester_label`, `effective_plan`, `plan_expires_at` (or `null`), and `revert_plan_id`; detail also includes `admin_notes`. On expiry, the effective plan reverts to `revert_plan_id` when evaluated at read/entitlement time.

Tier ordering is `ananta` (free) < `yanta` < `trika` < `part`. Use UTC timestamps in the future for expiry. A peer admin or the acting admin cannot be suspended, tier-changed, or erased; self-suspension is also refused. These denials are audited.

## Suspend, erase, export, and audit

- **Suspend/unsuspend:** use the user action in the dashboard and provide a reason. Suspension disables the user and revokes sessions; later requests return `403 ACCOUNT_SUSPENDED`. Unsuspend, when appropriate, is also a reasoned mutation.
- **Erase:** use the erase action only after confirming the target and the required `DELETE` confirmation. Erasure removes the user/account data keyed to the user and stores only a SHA-256 tombstone of a Clerk subject, preventing automatic re-provisioning. Message bodies are not exposed by admin endpoints.
- **Export:** use the per-user export action for an operational data export. Export events are audited; the exact dashboard download format/location is **PENDING**.
- **Audit log:** every mutation, export, per-user read, sign-in, and denied protected-target attempt appends an `admin_audit_log` row. Rows are append-only and survive user erasure. Review the audit entry immediately after sensitive actions and retain the reason that was submitted.

The fixed error classes are `422` for invalid input, `403` for forbidden/peer-admin or self-protected actions, and `404` for an unknown user. Missing or expired admin sessions return `401 ADMIN_SESSION_REQUIRED`; an unallowlisted/non-admin subject returns `403`.

## Operational safety

Do not share personal codes. Do not use a customer account to test admin actions. Prefer a single-user tier change when a bulk change is not required, and record the intended expiry in the reason. If Clerk revocation is unavailable because `DAILY_AGENT_CLERK_SECRET_KEY` is unset, use suspension to cut access; do not claim that remote Clerk sessions were revoked.
