# Admin console repro: Azure beta (karmi-beta, image 34f4062)

Status: **not reproduced**. The enrolled admin's code entry and every admin read endpoint returned 200 with valid JSON. No server 5xx occurred in the last 6 hours of logs. The reported "errors and no data" symptom has not been observed from the server side. Details and the next step follow.

## Method

- Test admin `karmi_dev_admin` (Clerk subject `user_3L7D8ho8Vd9bZypNZwh17YpJ342`). Enrolled via `scripts/admin_set_code.py --generate`. Code stored only in gitignored `.env.testusers`. Never printed.
- Clerk JWT minted via `clerk@4.0.0 api /sessions` and `/sessions/{id}/tokens`. Session tokens are short-lived (~60s); one minted token expired mid-run (see the 401 note below).
- Probe script `/tmp/karmi-repro/probe.py` (outside repo) called each endpoint the Flutter client (`admin_http_api.dart`) and the web client (`admin.js`) use, with `Authorization: Bearer` and `X-Admin-Session` headers.
- Mutating endpoints were called with validation-failing bodies only (no reason or confirm, or empty ids). FastAPI rejected them with 422 before any handler ran. No production data changed.
- Log check: `az containerapp logs show` fails inside the Azure CLI (`KeyError: 'eventStreamEndpoint'`). Used Log Analytics workspace `89cac178-5f7e-4b3b-ba87-efe1e95dba39` (`ContainerAppConsoleLogs_CL`) instead.

## Per-endpoint status (test admin, live server)

| Endpoint | Status | Notes |
|---|---|---|
| `GET /v1/admin/session` (no session header) | 200 | probe; valid:false expected |
| `POST /v1/admin/session` (enrolled code) | 200 | token issued |
| `GET /v1/admin/session` (with session) | 200 | |
| `GET /v1/admin/users?limit=25` | 200 | 5 users total in DB |
| `GET /v1/admin/users` with `q`, `status`, `suspended`, `tester_label`, `plan_expiring_before` | 200 | |
| `GET /v1/admin/users?tier=free` | 400 | `{"detail":"unknown tier"}`. My probe value, not a server bug; valid tier set not checked against `admin.js` TIERS |
| `GET /v1/admin/users?cursor=...` | not exercised | `next_cursor` was null; full pagination (1 page) also checked: shapes valid |
| `GET /v1/admin/users/{id}` | 200 | includes `usage` |
| `GET /v1/admin/users/{id}/export?reason=` | 200 | audit-logged read |
| `GET /v1/admin/monitor` | 200 | `provider_health` present |
| `GET /v1/admin/audit?limit=50` | 200 | 10 rows total; `detail` non-null in all |
| `GET /v1/admin/runs?limit=5` | 200 | not used by app/web |
| `PATCH /users/{id}`, `POST suspend/unsuspend/revoke-sessions/tier/credits`, `POST bulk-tier`, `DELETE /users/{id}` | 422 (validation-only) | confirms routing and auth pass; body contract enforced |
| `DELETE /v1/admin/session` | 200 | |
| `POST /v1/admin/session` (stale JWT) | 401 | expected after Clerk JWT expiry; not a server bug |

Response gzip (`Accept-Encoding: gzip`, as the Dart client sends) also returned valid JSON for users, audit, monitor and session.

## Dart parse check

Mirrored the `fromJson` rules in `admin_api.dart` against the live JSON: `AdminUser.id` is a string, `AuditEntry.id` is `toString()`, `AdminMonitor` uses numeric casts, `AdminUserPage` and `AuditPage` read `items` and `next_cursor`. No type mismatches found.

## Server logs (Log Analytics, last 6h)

- No HTTP 5xx from `karmi-beta` in the last 6 hours.
- Every admin request logged a `--- Logging error ---` traceback. The root is `ValueError: not enough values to unpack (expected 5, got 0)` in `uvicorn/logging.py:99` (`AccessFormatter.formatMessage`), raised from `uvicorn/protocols/http/httptools_impl.py:482` when the access logger is called with empty args. The response is still sent as the correct status. This is a logging defect, not the request failure.
- The traceback stack passes through `daily_agent/admin_metrics.py:78-81` and `daily_agent/gzip_middleware.py:27`. These only wrap `send`, so they do not cause the error.

## Code observations

- `src/daily_agent/admin_service.py:651-675` (`list_audit`): `json.loads(row.detail)` has no null guard. Live rows are non-null, so this is a latent risk, not the observed fault.
- `src/daily_agent/web/static/admin.js:686-724` (`loadUsers`): any failed `api()` call writes `err.message` to `users-message`. A server 5xx would show as the reported error. None was observed.

## Conclusion and next step

The live server returns correct data for the enrolled admin. The console symptom has therefore not been reproduced server-side. Remaining candidates to test: (1) the real admin's data (`rossoadmin`), which I was told not to touch; (2) the Flutter client's Clerk token source and build base URL, which this probe does not exercise; (3) a cold start or latency issue on the first call after sign-in (not measured here).

Suggested next step: capture the exact `users-message`/Flutter error text from the failing console and the matching request in the Log Analytics table, keyed to the time of the failure.
