# Karmi R1 — Execution Contract

Status: v1, 2026-10-21. Owner: Manager-IntegrationLead. Branch `release1/chat-redesign`.
Discovery inputs: `docs/release1/discovery/01–05`. Plan source: `/home/rosso/Downloads/ai_chat_ui_ux_redesign_plan_2026.md`.
Changes to this contract require IntegrationLead approval and a commit that edits this file.

## 0. Decisions that deviate from the plan (and why)
- **D1 Content storage**: a message stores markdown text in `chat_messages.content`. No `message_parts` table in R1. Rich parts (code, table, citation, file chip) are derived in the client from markdown. Structured parts move to R1.1. Reason: avoids a second source of truth while the gateway still returns text.
- **D2 Attachments**: R1 supports **text files only**, read on device and inlined into the prompt as fenced blocks. Limits: ≤3 files, ≤40,000 chars each, ≤60,000 chars total. No upload route, no storage, no images. Reason: no backend storage exists, and this avoids a new upload surface in R1.
- **D3 Drafts**: client-side only, in SharedPreferences, keyed `draft.v1.<conversationId or "new">`. Reason: no server draft table; drafts never leave the device.
- **D4 Streaming reality**: providers are streamed for real (OpenRouter-compatible `stream: true`; OpenCode if its endpoint supports SSE, otherwise OpenCode is marked non-streaming and sends a single `message.delta`). No simulated/chunked fake streaming of a completed reply.
- **D5 Resume scope**: resume works within the lifetime of the serving process (in-memory event buffer). After a process restart, the run is marked `interrupted`; the user resumes via Continue. Multi-instance fan-out is out of scope for R1 (the app runs as one instance).
- **D6 Compatibility**: `POST /v1/messages`, `POST /v1/runs/{id}/regenerate`, `POST /v1/runs/{id}/feedback` remain unchanged (used by `web/` PWA and tests). Mobile moves to new routes. Removal is R1.1.
- **D7 Search**: case-insensitive substring match (`ILIKE`, escaped) on conversation title and message content. No FTS in R1.

## 1. Canonical models

### 1.1 Backend (Postgres/SQLite-compatible; additive only)
Migration `c7a1d2e3f405_stream_runs` (down_revision `5f708192a3b4`):
- `runs` add nullable: `finish_reason VARCHAR(24)`, `partial_text TEXT`, `last_seq INTEGER NOT NULL DEFAULT 0`, `heartbeat_at TIMESTAMPTZ`, `continuation_of_run_id VARCHAR(64)`.
- Downgrade drops those columns.

Migration `d8b2e3f4a516_conversations` (down_revision `c7a1d2e3f405`):
- `conversations`: `id VARCHAR(40) PK` (`conv_` + 32 hex), `account_id FK accounts`, `user_id FK users`, `title VARCHAR(200) NULL`, `title_source VARCHAR(8) NOT NULL DEFAULT 'auto'` (`auto|user`), `pinned BOOLEAN NOT NULL DEFAULT false`, `archived_at TIMESTAMPTZ NULL`, `deleted_at TIMESTAMPTZ NULL`, `created_at`, `updated_at`, `last_message_at`. Indexes: `(user_id, deleted_at, updated_at)`.
- `chat_messages`: `id VARCHAR(40) PK` (`msg_` + 32 hex), `conversation_id FK conversations ON DELETE CASCADE`, `account_id FK`, `role VARCHAR(12)` (`user|assistant`), `status VARCHAR(16)` (`complete|streaming|stopped|interrupted|failed`), `content TEXT NOT NULL DEFAULT ''`, `finish_reason VARCHAR(24) NULL`, `run_id VARCHAR(64) NULL`, `parent_message_id VARCHAR(40) NULL`, `variant_index INTEGER NOT NULL DEFAULT 0`, `client_message_id VARCHAR(64) NULL`, `created_at`, `updated_at`. Unique `(conversation_id, client_message_id)`. Index `(conversation_id, created_at)`.
- Downgrade drops both tables.

Rules: no conversation row is created until the first user message is persisted (in the same transaction). Soft delete sets `deleted_at`; `restore` clears it. Hard purge is R1.1.

### 1.2 Wire types (Python `src/daily_agent/schemas_chat.py`, Dart `mobile/lib/api/chat/chat_models.dart` + `chat_events.dart`)
Owned by P1 (schema worker). Changing a field after P1 requires IntegrationLead.
- `FinishReason`: `stop | length | content_filter | cancelled | interrupted | error`.
- `MessageStatus`: `complete | streaming | stopped | interrupted | failed`.
- `ErrorCategory`: `quota_exhausted | capacity_full | provider_unavailable | validation_failed | unauthorized | resume_unavailable | internal | network` (`network` is client-only).
- `ConversationView`: `id, title, titleSource, pinned, archivedAt, updatedAt, lastMessageAt, messageCount`.
- `ChatMessageView`: `id, conversationId, role, status, content, finishReason?, runId?, parentMessageId?, variantIndex, createdAt, updatedAt`.
- `ConversationPage`: `items, nextCursor?`; `MessagePage`: `items (oldest→newest), hasMoreBefore`.

## 2. Stream protocol (Server-Sent Events)
Content-Type `text/event-stream; charset=utf-8`. Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`. Every event is `event: <name>`, `data: <JSON>`, and `id: <seq>` where applicable. Terminator is a blank line.

Event names and payloads (all JSON):
- `run.started` `{run_id, conversation_id, user_message_id, assistant_message_id, seq}` — always first.
- `message.delta` `{text}` — `seq` is the SSE `id`. `seq` is monotonically increasing per run, starting at 1.
- `heartbeat` `{at}` — sent every 15 s of silence. Not counted in `seq`.
- `run.finished` `{finish_reason, outcome, input_tokens?, output_tokens?, assistant_message_id}` — terminal.
- `run.error` `{category, retryable, retry_after_s?, assistant_message_id?}` — terminal. Partial text is kept.

Rules:
- A run emits exactly one terminal event (`run.finished` or `run.error`).
- `finish_reason=length` (provider reports truncation) is **never silent**: `run.finished` carries `length` and the UI offers Continue.
- Server output is never chain-of-thought. Only user-facing reply text is streamed.
- Pre-stream failures (auth, quota, validation, capacity) return the existing JSON error envelope with HTTP status, not an SSE event. Category mapping is in §2.2.

Endpoints (owned by Squad A, `src/daily_agent/routes/stream.py`):
- `POST /v1/chat/stream` body `{conversation_id?: string, text: string(1..100000), client_message_id: string(8..64)}` → SSE. Creates the conversation if `conversation_id` is absent. Idempotent on `(conversation_id, client_message_id)`: a repeat returns the same run's events (replay) if it exists.
- `GET /v1/runs/{run_id}/events?after_seq=N` → SSE. Replays `seq > N` from the in-memory buffer, then follows live. If the buffer no longer covers N, emits `run.error` with `category=resume_unavailable`.
- `POST /v1/runs/{run_id}/stop` → 202 `{status}`. Cancels the provider call. The run finishes with `finish_reason=cancelled`, and the message becomes `stopped` with partial content kept.
- `POST /v1/messages/{assistant_message_id}/continue` → SSE. Appends to the same assistant message (content grows). Only valid when the message `finish_reason` is `length|cancelled|interrupted|error` and status ≠ streaming. Provider receives prior content as an assistant prefix.
- `POST /v1/messages/{assistant_message_id}/regenerate` → SSE. Creates a sibling assistant message with `parent_message_id` = the user message and `variant_index` +1.

### 2.1 Server behaviour
- Generation runs in a background task owned by an in-process `StreamRegistry`. A client disconnect does **not** cancel generation.
- Delta buffer per run: kept 10 minutes after the terminal event (then evicted).
- Partial persistence: `runs.partial_text` and `chat_messages.content` are flushed at most once per 1.0 s or per 1 KB of new text, plus on terminal.
- Budget: one reservation at run start, one settlement at terminal (exactly once), reusing existing `services.py` functions.
- Startup sweep: runs in `streaming` state at process start are set to `interrupted` (`finish_reason=interrupted`), and their messages to `interrupted`.
- Stall: client considers the stream stalled after 25 s without any event; it then reconnects via `GET .../events?after_seq=`.
- Provider timeouts: first byte 20 s; idle gap 30 s. Both → `run.error` `provider_unavailable`, `retryable=true`.

### 2.2 Error mapping (HTTP pre-stream and `run.error`)
| Source | Category | Retryable | Note |
|---|---|---|---|
| 429 ALLOWANCE_EXHAUSTED | quota_exhausted | false | show plan/usage link |
| 429 BETA_CAPACITY_FULL | capacity_full | true | `retry_after_s` if present |
| provider timeout/5xx | provider_unavailable | true | |
| content_filter / empty reply / Devanagari check | validation_failed | true | |
| 401 | unauthorized | false | session expiry |
| resume buffer evicted | resume_unavailable | false | UI shows partial + Continue |
| anything else | internal | true | logged with run_id, never content |

## 3. Conversations and search API (Squad B, `src/daily_agent/routes/conversations.py`)
- `GET /v1/conversations?archived=false|true&cursor&limit(≤50)` → `ConversationPage`, ordered by `pinned DESC, updated_at DESC`.
- `GET /v1/conversations/search?q&limit(≤50)` → list of `{conversation: ConversationView, snippet, matched: title|content}`. `q` 1..200 chars. **Declare this route before `/{id}`.**
- `GET /v1/conversations/{id}` → `ConversationView`.
- `GET /v1/conversations/{id}/messages?before=<message_id>&limit(≤100)` → `MessagePage`.
- `PATCH /v1/conversations/{id}` `{title?: string(1..200), pinned?: bool, archived?: bool}` → `ConversationView`. Setting `title` sets `title_source=user`.
- `DELETE /v1/conversations/{id}` → soft delete (`deleted_at`), 204.
- `POST /v1/conversations/{id}/restore` → `ConversationView`. Within the undo window only in the UI; server restores until purge (purge is R1.1).
- Auto title: first 60 characters of the first user message when the conversation is created (`title_source=auto`). Never overwrites `user` titles.
- Every query scopes to the caller's `user_id`. Cross-user access returns 404, not 403.
- Search escapes `%`, `_`, `\`.

## 4. API ownership and compatibility
- `src/daily_agent/api.py`: only IntegrationLead edits it. P1 extracts shared FastAPI dependencies into `src/daily_agent/deps.py` and adds `include_router` lines for the two new routers (`routes/stream.py`, `routes/conversations.py`), which exist as empty routers after P1.
- Mobile API: `mobile/lib/api/karmi_api.dart` keeps its current methods unchanged. New classes live in `mobile/lib/api/stream/` (Squad A) and `mobile/lib/api/conversations/` (Squad B).
- Existing error envelopes and HTTP codes are unchanged.

## 5. Design tokens (Squad F)
- `mobile/lib/theme/` owns tokens. Other squads consume `KarmiTokens` and must not hardcode colours or durations.
- Dark patch: specular border alpha and inline usage-warning colours (80% threshold pill, amber) per plan §3.9.
- Contrast: body text ≥ 4.5:1, large text and UI ≥ 3:1 in both themes, checked by a QA test.
- Motion: `reduceMotion` (MediaQuery.disableAnimations) → durations 0 and no shimmer; `reduceTransparency` → opaque surfaces. Helpers in `theme/motion.dart` and `theme/transparency.dart`.
- Goldens change when tokens change. QA regenerates on Linux with `TZ=Asia/Kolkata` after Phase 2.

## 6. File ownership per squad (disjoint; each file has one writer)
P1 (serial prerequisite, one worker, runs first):
- `src/daily_agent/models.py` (add ORM classes), `migrations/versions/c7a1d2e3f405_stream_runs.py`, `migrations/versions/d8b2e3f4a516_conversations.py`, `src/daily_agent/schemas_chat.py`, `src/daily_agent/deps.py` (extracted from api.py), `src/daily_agent/routes/__init__.py`, empty `src/daily_agent/routes/stream.py` and `routes/conversations.py` (routers only), `mobile/lib/api/chat/chat_models.dart`, `mobile/lib/api/chat/chat_events.dart`, `mobile/pubspec.yaml` (add `markdown: ^7.3.1`, `url_launcher: ^6.3.3`; then `flutter pub get` once), `mobile/pubspec.lock`.
- `src/daily_agent/api.py`: P1 adds only the two `include_router` lines and the extracted-dep imports.

A — Streaming (backend + client stream):
- Backend: `src/daily_agent/streaming/` (new: `registry.py`, `runner.py`, `sse.py`), `src/daily_agent/routes/stream.py`, `src/daily_agent/gateway/adapters.py`, `src/daily_agent/gateway/opencode.py`, `src/daily_agent/gateway/service.py`, `src/daily_agent/gateway/types.py`.
- Client: `mobile/lib/api/stream/` (new: `sse_parser.dart`, `run_stream_client.dart`, `run_events.dart`), `mobile/lib/features/chat/state/chat_controller.dart` (new).

B — Persistence, management and search:
- Backend: `src/daily_agent/conversations/` (new: `service.py`, `search.py`), `src/daily_agent/routes/conversations.py`.
- Client: `mobile/lib/api/conversations/` (new), `mobile/lib/features/history/` (new: `conversation_list.dart`, `conversation_actions.dart` (rename/pin/archive/delete + undo snackbar), `search_field.dart`).

C — Workspace shell and scroll (client only):
- `mobile/lib/shell/karmi_shell.dart` (owner for breakpoints and lazy tabs), `mobile/lib/shell/workspace_layout.dart` (new), `mobile/lib/shell/breakpoints.dart` (new), `mobile/lib/features/chat/scroll/end_anchored_scroll.dart` (new), `mobile/lib/features/chat/scroll/jump_to_latest_button.dart` (new).

D — Rich rendering (client only):
- `mobile/lib/features/chat/rendering/` (new: `markdown_message.dart`, `code_block.dart`, `table_view.dart`, `citation_chip.dart`, `file_chip.dart`, `long_output_fold.dart`, `safe_link.dart`). Uses `package:markdown` (`ExtensionSet.gitHubWeb`, no raw HTML). Links open only `http`/`https` via url_launcher.

E — Composer, processing and recovery (client only):
- `mobile/lib/features/chat/composer.dart` (owner), `mobile/lib/features/chat/composer/` (new: `attachment_chip.dart`, `paste_chip.dart`, `draft_store.dart`, `text_attachment.dart`), `mobile/lib/features/chat/processing_panel.dart` (new), `mobile/lib/features/chat/error_card.dart` (new).

F — Tokens, dark mode and a11y (client only):
- `mobile/lib/theme/` (all), `mobile/lib/widgets/usage_warning_pill.dart` (new), `mobile/lib/widgets/feedback.dart` (owner).

G — Performance (client startup and backend DB):
- `mobile/lib/main.dart`, `mobile/lib/app.dart`. Startup awaits run in parallel where independent. Clerk init is deferred until the auth screen is first built, or runs in parallel if that is not possible; the choice must be recorded in the handoff.
- Backend: `src/daily_agent/perf/` not used. Batching of stream flushes belongs to A. G adds nothing else in R1.

Phase 2 (one writer, after A–F land):
- `mobile/lib/features/chat/chat_screen.dart`, `message_bubble.dart`, `chat_entry.dart`, `status_chip.dart`. Wires ChatController, rendering, composer, processing, error card, scroll, and history rail. Owner: IntegrationLead worker `ChatWiring`.

Owned by QA (not written by squads): `tests/**`, `mobile/test/**`, `docs/release1/TEST_STRATEGY.md`, `docs/release1/QA_REPORT.md`, `docs/release1/perf/*`.
Owned by ProgramDirector: `DEPENDENCY_BOARD.md`, `SCOPE_TIMELINE.md`, `R1_1_BACKLOG.md`, `RELEASE_REPORT.md`, `Memory.md`.

## 7. Public Dart seams (contract for parallel squads)
- `ChatController` (A): `ChangeNotifier` with `List<ChatMessageView> messages`, `ChatRunPhase phase` (`idle|sending|streaming|stalled|finished|error`), `ErrorCategory? error`, `FinishReason? finishReason`. Methods: `send(text, attachments)`, `stop()`, `continueMessage(id)`, `regenerate(id)`, `resume()`. Deltas batched on a 50 ms ticker before notify.
- `MarkdownMessage({required String text, required bool streaming, bool allowCollapse})` (D).
- `Composer({required String draftKey, required bool busy, required ValueChanged<ComposerSubmit> onSubmit, required VoidCallback onStop})` (E). `ComposerSubmit{text, attachments}`.
- `ProcessingPanel({required ChatRunPhase phase})` (E): staged summary only ("Preparing", "Writing", "Finishing"); never model reasoning.
- `ErrorCard({required ErrorCategory category, VoidCallback? onRetry, VoidCallback? onContinue, VoidCallback? onUpgrade})` (E).
- `JumpToLatestButton({required bool visible, required VoidCallback onTap})` and `EndAnchoredScroll` (C).
- `WorkspaceLayout({required Widget rail, required Widget main})`, breakpoints in `breakpoints.dart`: compact <600, medium 600–1024, expanded >1024 (C).
- `ConversationList({required ValueChanged<String> onOpen, required VoidCallback onNewChat})` (B).
- `UsageWarningPill({required double fraction})` shows at ≥0.8 (F).

## 8. Test requirements (QA writes them; squads do not)
- Backend unit: stream runner (delta order, seq, single terminal event, stop, disconnect-doesn't-cancel, buffer eviction → resume_unavailable, startup sweep → interrupted, budget settled once); conversations (no empty record, first-message creates row, title auto/user, soft delete/restore, search escaping, cross-user 404, pagination).
- Backend e2e: SSE happy path, resume after_seq, stop, continue appends, regenerate creates sibling, idempotent `client_message_id`.
- Client unit/widget: sse_parser (split frames, heartbeats, multi-line data), ChatController (batching, stall → resume, length → Continue offered, error categories), draft store per conversation, paste chip threshold 2,500 chars, Enter vs Shift+Enter, scroll stays pinned at bottom when streaming and not when user scrolled up, Jump to Latest, markdown (tables, code copy, no raw HTML, safe links), tokens contrast, usage pill at ≥0.8, reduced-motion.
- Goldens: updated in Phase 2 on Linux with `TZ=Asia/Kolkata`.
- Suggested file names are in `docs/release1/discovery/04-test-release-audit.md`.

## 9. Metrics (logged server-side as structured events, no content)
- `stream.started`, `stream.first_delta_ms`, `stream.finished{finish_reason}`, `stream.error{category}`, `stream.stalled`, `stream.resumed`, `stream.stopped`, `conversation.created`, `conversation.searched{result_count}`.
- Client perf (QA measures): cold start to first frame, chat scroll frame time during streaming, rebuild counts, before/after recorded in `docs/release1/perf/`.

## 10. Migration, deploy and rollback
- Migrations are additive: `c7a1d2e3f405` then `d8b2e3f4a516`. Downgrade drops only the new columns and tables. No data backfill is needed.
- No production deploy or migration in R1. Verification uses local Postgres 17 via `make test-integration`.
- Rollback: revert the release commits in reverse merge order, then `alembic downgrade 5f708192a3b4`. The old mobile build keeps working because the legacy routes are unchanged.
- Stream routes are not behind a flag. Rollback is code revert.

## 11. Merge order and checks
Order: P1 → F (tokens) → A (streaming) → B (persistence) → D (rendering) → E (composer/processing/error) → C (shell/scroll) → G (startup) → Phase 2 ChatWiring → QA tests and goldens → final checks.

Each squad worker: reads only the ranges it needs; writes only owned files; does **not** run tests, builds, analyzers, or formatters mid-flight; does not commit. The IntegrationLead runs checks once after each merge group and once at the end:
- Backend: `make PYTHON=.venv/bin/python lint`, `typecheck`, `test-unit`, `test-e2e`, `test-integration`.
- Flutter (in `mobile/`): `dart format --output=none --set-exit-if-changed .`, `flutter analyze`, `flutter test --exclude-tags golden`, `TZ=Asia/Kolkata flutter test --tags golden`.

## 12. Acceptance (R1)
All eight R1 items (plan §3.1–3.9 as scoped) are implemented, the checks in §11 pass, and the evidence list in the task brief is filled in. Anything not finished is reported as an open risk with its reason. No placeholder or stub ships.
