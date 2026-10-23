# Discovery 01 — Architecture (PHASE 0, read-only)

Source: explorer SourRhinoceros, 2026-10-21. Branch `release1/chat-redesign` at `dcf4f75`.

## Layout
- `src/daily_agent/` — backend. `api.py` (FastAPI routes, `create_app()` at :97), `services.py` (budget reserve/settle, `generate_reply` :703, `persist_completed_run`), `models.py` (SQLAlchemy), `schemas.py`, `plans.py` (tier policies), `security.py` (JWT/dev tokens), `ratelimit.py`, `worker.py` (outbox/reminders), `gateway/` (`service.py` Gateway.generate :102-183, `adapters.py`, `registry.py`, `router.py`, `health.py`, `types.py`), `parakh/`, `web/` (embedded PWA served at `/`), `model_lab/` (offline eval).
- `mobile/lib/` — Flutter client. `main.dart` (bootstrap, prefs, Clerk optional), `app.dart` (KarmiApp, tier theme, LiquidGlass wrap), `api/` (`karmi_api.dart`, `errors.dart`, `models.dart`), `auth/` (`session.dart`), `shell/karmi_shell.dart` (4-tab IndexedStack: Chat/Tasks/Usage/Settings), `features/{chat,welcome,plans,tasks,usage,armory,settings}`, `settings/` (KarmiSettings ChangeNotifier over SharedPreferences), `theme/`, `widgets/`, `armory/`.
- `tests/` (unit, e2e, integration, model_lab, web), `migrations/versions/` (alembic), `scripts/tasks.py` (Makefile delegate).

## Entry points
- Dev server: `python -m uvicorn daily_agent.api:app --host 127.0.0.1 --port 8000`.
- Worker: `python -m daily_agent.worker`.
- Console scripts: `daily-agent`, `karmi-parakh`, `model-lab`.

## Mobile → gateway
- Base URL: `KarmiApi.defaultBaseUrl` = `String.fromEnvironment('API_BASE_URL', defaultValue: 'http://10.0.2.2:8000')` (karmi_api.dart:27-30); overridable by `KarmiSettings.apiBaseUrl`.
- Auth: `KarmiSession` (auth/session.dart:21). Clerk JWT via `_clerkToken()` (:57) or dev token from `POST /dev/token` stored under `dev_session_token`. Bearer header; 401 → `onUnauthorized` → session expire.
- Transport: `http.Client`, `_send` aggregates full body (`Response.fromStream`), JSON parse. 60s client timeout (karmi_api.dart:21).

## Dependencies
- Backend: fastapi 0.141.1, pydantic 2.13.5, sqlalchemy 2.0.52, alembic >=1.16, psycopg >=3.2, redis >=6, PyJWT, typesafe-sdk 0.7.0, pytest 9.1.1, mypy >=1.17 strict on src, ruff >=0.12.
- Flutter: liquid_glass_widgets 1.6.2, google_fonts 8.2.1, http 1.6.0, shared_preferences 2.5.5, clerk_flutter/clerk_auth 0.0.18-beta, flutter_lints 5.0.0. SDK >=3.47.5, Dart >=3.10.
- NOT present: any markdown renderer, SSE/stream parser, sqlite/drift (drift 2.35.0 exists in the local pub cache but is not a dependency), state-management framework.

## Gaps vs R1 (summary)
- No streaming transport (sync request-response only).
- Chat transcript lives in `_ChatScreenState._entries` (in memory); no conversation persistence.
- Replies are plain `Text()`; no rich rendering pipeline.
- Composer: single TextField 1–5 lines; no attachments, paste chips, drafts, Enter/Shift+Enter semantics, Stop.
- Shell: fixed bottom tabs; no tablet/desktop history rail, no Jump to Latest, no end-anchored scroll.
- Processing UI: one spinner; no staged processing states; error mapping limited to 4 codes (chat_screen.dart:72).
