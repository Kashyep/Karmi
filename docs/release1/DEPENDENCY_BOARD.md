# Release 1 Dependency Board

Owner: Manager-ProgramDirector. Authoritative inputs: `docs/release1/EXECUTION_CONTRACT.md` (v1, commit `5de20a8`, owner Manager-IntegrationLead), squad handoffs in `docs/release1/handoffs/*.md`, and QA evidence in `docs/release1/QA_REPORT.md`.
Last updated: 2026-10-21 (contract v1 landed; no squad handoff exists yet).

Status values: `NOT STARTED`, `IN PROGRESS`, `HANDOFF`, `MERGED`, `VERIFIED`, `BLOCKED`.

## Program status

| Phase | Gate | Status |
|---|---|---|
| 0 Discovery | Five discovery files `docs/release1/discovery/01–05` | DONE. Perf baseline (`05-perf-baseline.md`) is code-read only: no device or frame timings measured; only `flutter analyze` (0 issues, 8.4 s) and two prose-width tests (9.75 s) recorded. Frame and startup numbers are owed by QA in `docs/release1/perf/`. |
| 0 Contract | `EXECUTION_CONTRACT.md` v1 | DONE (commit 5de20a8) |
| 1 Build | P1 prerequisite, then squads F → A → B → D → E → C → G, Phase 2 ChatWiring | NOT STARTED (no handoffs) |
| 2 Integrate | Merge order §11; backend `make` targets; flutter analyze/test; goldens (TZ=Asia/Kolkata) | NOT STARTED |
| 2 Release | RELEASE_REPORT, Memory.md | NOT STARTED |

## Prerequisite and squads

| ID | Scope (contract ref) | Owner | Writes (contract §6) | Depends on | Status | Merge rank |
|---|---|---|---|---|---|---|
| P1 | Additive schema + DTO + router skeleton: ORM classes, migrations `c7a1d2e3f405` (stream_runs), `d8b2e3f4a516` (conversations), `schemas_chat.py`, `deps.py`, `routes/__init__.py`, empty routers, `chat_models.dart`, `chat_events.dart`, pubspec deps (`markdown`, `url_launcher`) | IntegrationLead worker (serial) | as §6 P1 | Contract | NOT STARTED | 0 (first) |
| F | Tokens, dark mode, usage warning pill ≥0.8, a11y (`mobile/lib/theme/`, `usage_warning_pill.dart`, `feedback.dart`) | Manager-IntegrationLead (squad F) | §6 F | P1 | NOT STARTED | 1 |
| A | Streaming: `src/daily_agent/streaming/`, `routes/stream.py`, gateway adapters; client `mobile/lib/api/stream/`, `chat_controller.dart` | Manager-IntegrationLead (squad A) | §6 A | P1, F (tokens for status UI only) | NOT STARTED | 2 |
| B | Persistence/search/management: `src/daily_agent/conversations/`, `routes/conversations.py`; `mobile/lib/api/conversations/`, `mobile/lib/features/history/` | Manager-IntegrationLead (squad B) | §6 B | P1 (schema), A (message write path) | NOT STARTED | 3 |
| D | Rich rendering: `mobile/lib/features/chat/rendering/` | Manager-IntegrationLead (squad D) | §6 D | A (typed events), F | NOT STARTED | 4 |
| E | Composer, processing panel, error card, drafts (`composer.dart`, `composer/`, `processing_panel.dart`, `error_card.dart`) | Manager-IntegrationLead (squad E) | §6 E | A (ChatController seam), F | NOT STARTED | 5 |
| C | Workspace shell, breakpoints, end-anchored scroll, Jump to Latest, history rail (`shell/`, `features/chat/scroll/`) | Manager-IntegrationLead (squad C) | §6 C | B (history list), E | NOT STARTED | 6 |
| G | Startup perf: `mobile/lib/main.dart`, `mobile/lib/app.dart` (deferred Clerk init, parallel startup awaits) | Manager-IntegrationLead (squad G) | §6 G | C (shell files stable) | NOT STARTED | 7 |
| Wiring | `chat_screen.dart`, `message_bubble.dart`, `chat_entry.dart`, `status_chip.dart` | IntegrationLead worker `ChatWiring` | §6 Phase 2 | A–G | NOT STARTED | 8 |
| H | Tests, goldens, a11y, perf measurement, QA_REPORT (`tests/**`, `mobile/test/**`, `docs/release1/perf/*`) | Manager-QAReleaseLead | §6 QA-owned | Contract; each squad handoff | NOT STARTED | final gate |

Note on the rank: the contract §11 order is P1 → F → A → B → D → E → C → G → Wiring → QA. This board uses the same order; the table ranks are that order.

## Contract deviations to track (contract §0, D1–D7)

| ID | Deviation | Owner of follow-up | R1.1 ticket |
|---|---|---|---|
| D1 | No `message_parts` table; rich parts derived client-side from markdown | IntegrationLead | R1.1-6 |
| D2 | Attachments text-only, inlined; no upload route or storage | IntegrationLead | R1.1-7 |
| D3 | Drafts client-side (SharedPreferences) only | IntegrationLead | R1.1-8 |
| D4 | Real provider streaming; no simulated chunking; OpenCode non-streaming if no SSE | Squad A | (verify in A handoff) |
| D5 | Resume only within process lifetime; restart marks run `interrupted` | Squad A | R1.1-9 |
| D6 | Legacy `POST /v1/messages`, regenerate, feedback routes kept for `web/` and tests | IntegrationLead | R1.1-10 |
| D7 | Search is case-insensitive substring (ILIKE), no FTS | Squad B | R1.1-11 |

## Shared-file serialization

| Shared asset | Single writer window | Consumers that wait |
|---|---|---|
| `models.py`, migrations, `schemas_chat.py`, `deps.py`, `api.py` router lines | P1 only | all |
| `mobile/lib/api/chat/*`, `pubspec*` | P1 only | all |
| `mobile/lib/theme/` | F | C, D, E, G |
| `mobile/lib/features/chat/chat_screen.dart` and wiring files | Wiring only | — |
| `mobile/lib/shell/karmi_shell.dart` | C | G |

## Gating on R1 (R1.1 tickets)

R1.1 MUST NOT start until: A and B MERGED and VERIFIED, F MERGED, H regression gate passed. Tickets in `R1_1_BACKLOG.md` carry per-ticket gates (G-1 to G-4, OD-1 to OD-5).

## Risks (live)

- R-1 Stream schema collisions: mitigated by P1 serial writer and contract §2.
- R-2 Plan web-flavour vs Flutter: adaptations live in contract §0 and backlog stack notes.
- R-3 Untracked evidence (`docs/release-evidence/device/*.png`, `Claude outputs/`): never delete or stage-delete.
- R-4 Contract §6 lists `api.py` as shared; only router-include lines and dep imports may change there.
- R-5 Squad workers may not run checks mid-flight; all checks run once by IntegrationLead per §11.
- R-6 RESOLVED (Supervisor decision): Artifact and Sources drawers are deferred to R1.1 (R1.1-5). R1 keeps inline citation chips and file cards only.

## Handoff log

| Date | From | Squad | Handoff file | Status change |
|---|---|---|---|---|
| 2026-10-21 | Manager-ProgramDirector | — | this file | Board created |
| 2026-10-21 | Manager-IntegrationLead | — | `EXECUTION_CONTRACT.md` (5de20a8) | Contract v1 landed; Phase 0 DONE |
