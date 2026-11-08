# Release 1 Dependency Board

Owner: Manager-ProgramDirector. Authoritative inputs: `docs/release1/EXECUTION_CONTRACT.md` (v1, commit `5de20a8`, owner Manager-IntegrationLead), squad handoffs in `docs/release1/handoffs/*.md`, QA evidence in `docs/release1/QA_AUDIT_BACKEND.md`, `docs/release1/QA_AUDIT_CLIENT.md`, `docs/release1/QA_A11Y.md` and `docs/release1/QA_REPORT.md` (Boss rejection round 1 verdict), and the release summary `docs/release1/RELEASE_REPORT.md`.
Last updated: 2026-10-22 (all squads and Phase 2 Wiring merged on `release1/chat-redesign`, HEAD `4b95f5c`).

Status values: `NOT STARTED`, `IN PROGRESS`, `HANDOFF`, `MERGED`, `VERIFIED`, `BLOCKED`.
`MERGED` = commits are on `release1/chat-redesign`. `VERIFIED` = an observed check result exists in a handoff or in a command re-run recorded in `RELEASE_REPORT.md`.

## Program status

| Phase | Gate | Status |
|---|---|---|
| 0 Discovery | Five discovery files `docs/release1/discovery/01–05` | DONE. Perf baseline (`05-perf-baseline.md`) is code-read only. Measured numbers are in `docs/release1/perf/BASELINE.md`. |
| 0 Contract | `EXECUTION_CONTRACT.md` v1 | DONE (commit 5de20a8) |
| 1 Build | P1 prerequisite, then squads F → A → B → D → E → C → G, Phase 2 Wiring | MERGED. Squad handoffs exist for A, B, BW, C, D, E, F, G, FIX, QA1, WIRING. |
| 2 Integrate | Merge order §11; backend `make` targets; flutter analyze/test; goldens (TZ=Asia/Kolkata) | IN PROGRESS. Re-run at `4b95f5c` (2026-10-22): backend lint/typecheck clean, `test-unit` 226 passed, `test-e2e` 62 passed, `test-integration` 6 passed. Supervisor at `4b95f5c`: `flutter analyze` clean; a11y and chat suites 103 passed. Full Flutter suite final count: `QA_REPORT.md`. Perf after-numbers are host-VM proxies only. |
| 2 Release | `RELEASE_REPORT.md`, Memory.md | IN PROGRESS. `RELEASE_REPORT.md` final. Sign-off waits for QA approval and PENDING-USER items (`RELEASE_REPORT.md` section 11). |

## Prerequisite and squads

| ID | Scope (contract ref) | Owner | Writes (contract §6) | Depends on | Status | Merge rank | Commits (on release1/chat-redesign) |
|---|---|---|---|---|---|---|---|
| P1 | Additive schema + DTO + router skeleton | IntegrationLead worker (serial) | as §6 P1 | Contract | MERGED | 0 (first) | a7b2025, 8d4cb3a |
| F | Tokens, dark mode, usage warning pill ≥0.8, a11y | Manager-IntegrationLead (squad F) | §6 F | P1 | MERGED | 1 | c9eb670 |
| A | Streaming backend + client `ChatController` | Manager-IntegrationLead (squad A) | §6 A | P1, F | MERGED | 2 | e472945, 4f785fc, e0dbbb1 (merge) |
| B | Persistence/search/management | Manager-IntegrationLead (squad B) | §6 B | P1, A | MERGED | 3 | cb16086, f41d011 (merge) |
| BW | Backend wiring: startup sweep, conversation attach/touch in stream route | Manager-IntegrationLead | `api.py` lifespan, `routes/stream.py`, `streaming/runner.py` | A, B | MERGED | 3b | 365e17f, 938b060 |
| D | Rich rendering: `mobile/lib/features/chat/rendering/` | Manager-IntegrationLead (squad D) | §6 D | A, F | MERGED | 4 | d17831e, dddb9d5 (merge) |
| E | Composer, processing panel, error card, drafts | Manager-IntegrationLead (squad E) | §6 E | A, F | MERGED | 5 | b0f0fdc, 4e0a9b3, 7b2d17e, c79920d, 4cc6ca3, 35697a5 (merge) |
| C | Workspace shell, breakpoints, end-anchored scroll, Jump to Latest, history rail | Manager-IntegrationLead (squad C) | §6 C | B, E | MERGED | 6 | a2bf8e2, cd7a5ec, f2aabf6 (merge) |
| G | Startup perf: `mobile/lib/main.dart`, `mobile/lib/app.dart` | Manager-IntegrationLead (squad G) | §6 G | C | MERGED (startup ordering only; after-numbers NOT MEASURED) | 7 | efd44e7, 6fd8bc1, 50024bb (merge) |
| Wiring | `chat_screen.dart`, `message_bubble.dart`, `chat_entry.dart`, `status_chip.dart`, streaming ChatScreen | IntegrationLead worker `ChatWiring` | §6 Phase 2 | A–G | MERGED | 8 | f9d9a17, 28e1d07, feb94d4, 408661a, d705ac5, fe571e0, e6c0d57 (merge) |
| QA-gap | QA gap tests (backend + client), backend audit | Manager-QAGap | tests, `QA_AUDIT_BACKEND.md` | Wiring | MERGED | 9 | ee900ba, c9a9263, b1e570d, 264c1e5, 65e0175 |
| FIX | Audit fixes: auth scoping, registry, sweep, IME Enter, paste threshold, PG integration | Manager-AuditFix | `routes/stream.py`, `streaming/`, `composer.dart`, tests | QA-gap | MERGED | 10 | 59d4609, 4b5ccb3, b8a4fff, 8eb0f81, dd3d00a, 2227b6f |
| H | Tests, goldens, a11y, perf measurement, QA_REPORT (`tests/**`, `mobile/test/**`, `docs/release1/perf/*`) | Manager-QAReleaseLead | §6 QA-owned | Contract; each squad handoff | Test commits merged (see QA-gap, FIX, 9404fed). Audits fixed (AUDIT-03/04/05 in `4b95f5c`). Goldens not visually reviewed (R-9). QA_REPORT updated for Boss rejection round 1; not signed off. | final gate | 4b95f5c |

Note on the rank: the contract §11 order is P1 → F → A → B → D → E → C → G → Wiring → QA. The QA-gap and FIX rows were added after Wiring; they are fixes and tests on top of that order.

## Contract deviations to track (contract §0, D1–D7)

| ID | Deviation | Owner of follow-up | R1.1 ticket | State in R1 |
|---|---|---|---|---|
| D1 | No `message_parts` table; rich parts derived client-side from markdown | IntegrationLead | R1.1-6 | As designed (squad D renders markdown) |
| D2 | Attachments text-only, inlined; no upload route or storage | IntegrationLead | R1.1-7 | As designed (squad E `text_attachment.dart`) |
| D3 | Drafts client-side (SharedPreferences) only | IntegrationLead | R1.1-8 | As designed (squad E `draft_store.dart`) |
| D4 | Real provider streaming; no simulated chunking; OpenCode non-streaming if no SSE | Squad A | (verify in A handoff) | NOT VERIFIED: A handoff states gateway streaming with finish_reason and timeouts; it does not state which OpenCode mode is in use |
| D5 | Resume only within process lifetime; restart marks run `interrupted` | Squad A | R1.1-9 | Startup sweep wired in `api.py` lifespan (BW). Sweep covered by unit tests (QA-gap, FIX). |
| D6 | Legacy `POST /v1/messages`, regenerate, feedback routes kept for `web/` and tests | IntegrationLead | R1.1-10 | Kept; thumbs feedback uses the legacy API (WIRING) |
| D7 | Search is case-insensitive substring (ILIKE), no FTS | Squad B | R1.1-11 | As designed; LIKE escaping tested (QA-gap) |

File-layout deviations from §6 (not contract decisions, recorded for traceability): squad F kept motion helpers in `lib/theme/karmi_motion.dart` and did not create `theme/motion.dart` or `transparency.dart` (F handoff). Squad E defined `ChatRunPhase` locally in `processing_panel.dart` with a note to move it to A's `chat_controller.dart`; current location not re-checked in this docs pass.

## Shared-file serialization

| Shared asset | Single writer window | Consumers that wait |
|---|---|---|
| `models.py`, migrations, `schemas_chat.py`, `deps.py`, `api.py` router lines | P1 only (`api.py` lifespan sweep: BW) | all |
| `mobile/lib/api/chat/*`, `pubspec*` | P1 only | all |
| `mobile/lib/theme/` | F | C, D, E, G |
| `mobile/lib/features/chat/chat_screen.dart` and wiring files | Wiring only | — |
| `mobile/lib/shell/karmi_shell.dart` | C | G |

Window closed: all listed windows are merged on `release1/chat-redesign`.

## Gating on R1 (R1.1 tickets)

R1.1 MUST NOT start until: A and B MERGED and VERIFIED, F MERGED, H regression gate passed. Tickets in `R1_1_BACKLOG.md` carry per-ticket gates (G-1 to G-4, OD-1 to OD-5).
Status against this gate: A and B MERGED; "VERIFIED" for A/B rests on their handoff checks; the H regression gate is recorded in `QA_REPORT.md` (Supervisor full-suite result pending at time of writing). R1.1 is NOT started.

## Risks (live)

- R-1 Stream schema collisions: mitigated by P1 serial writer and contract §2.
- R-2 Plan web-flavour vs Flutter: adaptations live in contract §0 and backlog stack notes.
- R-3 Untracked evidence (`docs/release-evidence/device/*.png`, `Claude outputs/`): never delete or stage-delete. `docs/release-evidence/device/01-launch.png` shows as modified in the working tree; it predates this release and was not changed by the docs work.
- R-4 Contract §6 lists `api.py` as shared; only router-include lines, dep imports and the BW lifespan sweep call may change there.
- R-5 Squad workers may not run checks mid-flight; all checks run once by IntegrationLead per §11.
- R-6 RESOLVED (Supervisor decision): Artifact and Sources drawers are deferred to R1.1 (R1.1-5). R1 keeps inline citation chips and file cards only.
- R-7 OPEN: Postgres integration covers 6 tests (`make test-integration`, FIX handoff). Not re-run on 2026-10-22.
- R-8 OPEN: Device/profile perf and APK size not measured. See `RELEASE_REPORT.md` section "Unresolved risks".
- R-9 OPEN: Goldens regenerated in this release need human review of the diffs (see `RELEASE_REPORT.md`).

## Handoff log

| Date | From | Squad | Handoff file | Status change |
|---|---|---|---|---|
| 2026-10-21 | Manager-ProgramDirector | — | this file | Board created |
| 2026-10-21 | Manager-IntegrationLead | — | `EXECUTION_CONTRACT.md` (5de20a8) | Contract v1 landed; Phase 0 DONE |
| 2026-10-21 | Squads P1, F, A, B, BW, D, E, C, G | per `handoffs/*.md` | `handoffs/A.md` … `G.md` | MERGED on `release1/chat-redesign` |
| 2026-10-21 | Manager-QAGap | — | `handoffs/QA1.md`, `QA_AUDIT_BACKEND.md` | Gap tests and audit merged |
| 2026-10-21 | Manager-AuditFix | — | `handoffs/FIX.md` | Audit findings fixed and merged |
| 2026-10-21 | Manager-ChatWiring | Wiring | `handoffs/WIRING.md` | MERGED (e6c0d57) |
| 2026-10-22 | Manager-FinalVerify | — | `RELEASE_REPORT.md`, `QA_REPORT.md`, `Memory.md` | Release report final; QA_REPORT updated for Boss rejection round 1 |
