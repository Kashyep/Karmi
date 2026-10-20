# MVP + first tester release: evidence (branch `mvp-gateway`)

Nothing pushed, tagged, published or deployed. Draft PR text: `docs/release-evidence/draft-pr.md`.

## Commits

Karmi (`0c3d11e..HEAD`): 1109262 backend/Clerk/Neon, 33061b9 OpenCode route + action registration,
01d40a4 mobile Clerk client, 9dd4f9a docs, 2859217 gateway, f9323b0 feedback + telemetry,
e73b0c3 hardening, 9878151 mobile feedback UI + tester notice, plus the docs commit holding this file.
Parakh (branch `openrouter-student-set`): 3fa387e adapter/snapshot/registry/student set, 56e95a5 caveats.
Pre-work patch of the 1,150-line working tree: `~/karmi-backups/tracked-20261018-230710.patch` and
`untracked-20261018-230710.tgz`.

## WP0 baseline (before feature work; fresh venvs, Python 3.14)

| Gate | Result |
|---|---|
| Karmi `tasks.py lint` / `typecheck` / `test-unit` / `test-e2e` | exit 0 / 0 / 0 (113 passed) / 0 (45 passed) |
| Parakh `pytest -q` | exit 0, 231 passed, 1 skipped |
| `flutter analyze` | no issues |
| `flutter test` | 318 pass, 8 fail: stale `usage` golden PNGs (0.16%-13.9% pixel diff; screen untouched). Regenerated on this Linux host later; other 300+ goldens matched, so host rendering is consistent |
| Docker | not installed |

Findings: `KNOWN_ACTIONS`/`model_registry()` omitted the OpenCode action (fixed, test added; later
generalized to registry-driven actions); `.env.openrouter` was not git-ignored (fixed). Existing
OpenCode tests already covered reply, DEFERRED, unknown-cost settlement, private-model config and
single-call; the unknown-cost settlement expectation was intentionally replaced by release-on-final-failure.

## Final gates (this branch)

| Command | Result |
|---|---|
| `tasks.py lint` (ruff + secret scan) | exit 0 |
| `tasks.py typecheck` | exit 0, 35 files |
| `tasks.py test-unit` | exit 0, 163 passed |
| `tasks.py test-e2e` | exit 0, 49 passed |
| `tasks.py test-smoke`, `benchmark-demo` | exit 0 |
| Integration (`pytest -m integration`) on disposable local **PostgreSQL 18.6 + Valkey 9.1** on the compose ports 55432/56379 (NOT Docker): migrations up, full downgrade chain, up, `alembic check`, atomic platform budget, exactly-once delivery, token-quota race (12 threads, exactly 5 admitted) | 3 passed |
| Parakh `pytest -q` | exit 0, 247 passed, 1 skipped; `make test-release` exit 0 (reported by worker) |
| Parakh cross-repo test under Karmi runtime (`PARAKH_REQUIRE_KARMI=1`) incl. new gateway-retry + rating + regenerate export | 5 passed; import status `imported`, quarantined 0, accepted 2 |
| `flutter analyze` | no issues |
| `flutter test` | 339 passed, 0 failed |
| `flutter build apk --release` | built 58.2 MB; sha256 `ef1ff8b6fd8ab532428369b0bf6fd1489151f4a8cb3bdeae2215f03dae06747c` (file `mobile/build/app/outputs/flutter-apk/app-release.apk`, untracked) |
| Independent audit (read-only agent) | no defects reported; it ran no commands, so treat as weak evidence |

## Per work package

- **WP0** VERIFIED (above).
- **WP1** PARTIAL. Done and tested on fakes: OpenRouter adapter (zero-price abort, request cap,
  no redirects, bounded 429 backoff, key via `.env.openrouter`), `catalog snapshot` command, registry builder +
  JSON schema, 49-case student set (31/9/9 split, sealed holdout hash), operator guide.
  NOT done: no live run, no dated catalog snapshot, no scores/shortlist/registry (owner gate: key + request cap).
  Deviation: Parakh `pilot run` gates (36 train cases, old provider) block the student set; see known-issues.
- **WP2** VERIFIED on fake HTTP transport: registry loader, adapters, rules router, per-tier classes,
  daily request + token quotas, cooldown, breaker, at most 2 attempts, DEFERRED + release, kill switch, privacy gate,
  demo path, CLAUDE.md rule updated. Deviations: seed registry instead of WP1 registry; quotas provisional;
  Docker integration replaced by local PG/Valkey.
- **WP3** VERIFIED: `message_feedback` table + run links (one migration), idempotent rating upsert (fixed reason vocabulary),
  regenerate (client resends prompt; hash-checked), sanitized export using the existing `feedback` field (no schema change),
  export refuses runs referencing models absent from the registry. Zero quarantined on Parakh import.
- **WP4** PARTIAL: UI, client, notice gate, goldens, tests VERIFIED; APK built (placeholder backend URL,
  debug signing). NOT verified: Clerk email-code sign-in on a physical phone (none connected).
- **WP5** PARTIAL: per-user rate limit, log redaction, real `synthetic_provider_disabled` audit check, migration
  rollback rehearsal on PostgreSQL (in integration test), hosting proposal. Audit status against a real candidate config
  remains BLOCKED on observation-only checks (TLS, deployed telemetry, rollback on candidate). Not deployed.
- **WP6** PREPARED: tester guide, notice (legal review flagged), known issues, hosting options, this file. Not pushed.

## Remaining owner inputs

OpenRouter key in `.env.openrouter`; approved request cap; Docker (to re-run integration the official way);
Android phone with Clerk email-code enabled; hosting choice and approval; signing key decision; tester list;
legal review of the notice; final approval to push, tag and publish.

## Update 2026-10-19 (owner supplied key, phone, publish approval)

- **Key**: `.env.openrouter` uses the variable `OPEN_ROUTER_KEY`; both loaders now accept it (file mode set to 600).
  `GET /key`: free tier, 50 requests/day. A full pilot is impossible at that limit, so a capped probe was run
  (details and results in `known-issues.md`; raw rows in `Parakh/docs/live_pilots/runs/probe-2026-10-19.json`,
  provisional registry in `Parakh/docs/live_pilots/registry/`, catalog in `.../catalog/`).
- **Registry**: 7 OpenRouter models + the OpenCode seed are packaged; one live request through the real gateway
  (ananta plan) returned a correct reply from `liquid/lfm-2.5-2.6b:free`, cost 0.
- **Access codes**: `POST /v1/access-code`, hashes only in the repo, 5 guesses/min per user, never downgrades;
  Flutter UI in Plans and in Settings. Plain codes are in `~/karmi-backups/access-codes.txt` (not in git).
- **Podman**: `tasks.py test-integration` now falls back to rootless podman when Docker is absent; run: 3 passed.
- Final gates: lint, typecheck, test-unit (164), test-e2e (52), test-smoke, test-integration (3, podman) exit 0;
  Parakh 247 passed + `make test-release` exit 0; flutter analyze clean, flutter test all passed after
  regenerating plans/settings/welcome goldens.
- Release APK `mobile/build/app/outputs/flutter-apk/app-release.apk`, sha256
  `ee94f426d269c9116de18e573dcca73c8ac754090a7d8e577a8833f349dabb95` (debug-signed, placeholder server).

## Update 2026-10-21: hosted backend and notes removal

- Notes feature removed end to end (ceda6c3, f1dd564, 3707441). Neon migrated 1a2b3c4d5e6f -> 4d5e6f708192
  (drops `notes`; owner approved the destructive drop).
- Azure Container Apps `karmi-beta` in `cae-karmi-prod` (eastasia), one replica, image
  `karmiprod49bem0.azurecr.io/karmi-backend:fe59b82` built locally with podman (ACR Tasks are not allowed on the
  Azure for Students subscription). First deploy crashed: `httpx` was only a dev dependency; fixed in fe59b82.
- Live checks against https://karmi-beta.gentlepebble-6595a0fa.eastasia.azurecontainerapps.io:
  `/health` 200 `{"status":"alive"}`; `/ready` 200 `database: ok`; `/v1/usage` without token 401;
  `/dev/token` 404; plain http -> 301 to https.
- `scripts/readiness_config.py --env-file .env.azure.prod`: status BLOCKED, **0 FAIL**. BLOCKED (observation-only,
  by design): telemetry_live_observed, migrations_restored, rollback_proven, tls_termination, payment_approval.
- APK rebuilt against the hosted URL: sha256 `0c38dc61ff6420c447bf428e90c869278f41930f08a701bb0d76d25b350a094f`;
  installed on Pixel 9a (adb `Success`). Device sign-in not yet recorded (phone locked; Clerk code needs the owner).
