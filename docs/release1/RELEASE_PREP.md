# Release 1 prep (v0.1.0-beta.3)

State on 2026-10-22: prod backend updated; prod test APK built; awaiting owner device approval.

## Prod backend (done)
- Pre-migration backup: `~/karmi-backups/prod-pre-r1-20261022-0536.dump` (pg_dump custom, 21 tables).
- Migrations (additive only): `5f708192a3b4` -> `c7a1d2e3f405` (5 new nullable/defaulted `runs` columns) -> `d8b2e3f4a516` (new `conversations`, `chat_messages` tables).
- Image `karmiprod49bem0.azurecr.io/karmi-backend:ac51d1e`, revision `karmi-beta--latest`, 1 replica, Running.
- Smoke: `/health` alive, `/ready` 200, `/v1/conversations` and `/v1/chat/stream` 401 without auth (routes live), `/dev/token` 404 (dev auth off).
- Gates before deploy: lint + secret scan clean; unit 226 passed; e2e 62 passed.

## Test APK (prod)
- `~/karmi-backups/karmi-v0.1.0-beta.3-prod-test.apk` (61.9 MB), sha256 `4fc694b54b68039c704295556d18b23572a6e6377519338f74aa9e4af334feff`.
- Release mode, `API_BASE_URL=https://karmi-beta.gentlepebble-6595a0fa.eastasia.azurecontainerapps.io`, Clerk dev instance (`pk_test_`, same issuer as the backend).
- Signed with the local debug keystore (no release keystore in `mobile/android/`); replacing the installed beta.2 requires `adb uninstall ai.karmi.app` first.

## Rollback
1. App image: `az containerapp update -g rg-karmi-prod -n karmi-beta --image karmiprod49bem0.azurecr.io/karmi-backend:c7c0aba` (previous image).
2. Schema: leave the additive columns/tables in place (old code ignores them). Only if required: `alembic downgrade 5f708192a3b4` with the migration URL from `.env.neon` (drops the new tables and columns and loses R1 conversation data).
3. Full data restore (last resort): `pg_restore --clean --no-owner -d <direct URL> ~/karmi-backups/prod-pre-r1-20261022-0536.dump`.

## Owner device checks (PENDING-USER, Pixel 9a)
Sign-in, streaming reply, Stop/Continue/Regenerate, airplane-mode resume, history search/rename/pin/archive/delete+Undo, New Chat creates nothing before the first send, >2500-char paste chip, scroll-up during streaming + Jump to Latest, dark/light, keyboard overlap.

## To cut the release after approval
1. Record the device results above in `QA_REPORT.md`.
2. Close the perf gate (rebuilds per send at or below the baseline) or record an explicit owner waiver.
3. Generate a release keystore (or use Play App Signing) and an `appbundle`; bump to `0.1.0` with a fresh build number.
4. Tag `v0.1.0-r1` on `release1/chat-redesign`, open the PR to `main`, and update `RELEASE_REPORT.md` and `Memory.md`.
