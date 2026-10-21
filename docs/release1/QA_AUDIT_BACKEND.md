# Karmi R1 Backend QA Audit Report

**Date**: 2026-10-21  
**Target Worktree**: `/tmp/wt-qa` (branch `r1/qa`)  
**Contract Baseline**: `docs/release1/EXECUTION_CONTRACT.md` (§2, §2.1, §3, §4)  
**Audit Scope**:
- `src/daily_agent/streaming/registry.py`
- `src/daily_agent/streaming/runner.py`
- `src/daily_agent/streaming/sse.py`
- `src/daily_agent/routes/stream.py`
- `src/daily_agent/routes/conversations.py`
- `src/daily_agent/conversations/service.py`
- `src/daily_agent/conversations/search.py`

---

## Executive Summary

- **Critical**: 1
- **High**: 3
- **Medium**: 3
- **Low**: 3
- **Total Findings**: 10

---

## Findings by Severity

### Critical

#### 1. Cross-User Authorization Bypass and Data Leakage in Continue and Regenerate
- **File & Line**: `src/daily_agent/routes/stream.py:402-407` (`continue_message`) and `src/daily_agent/routes/stream.py:523-528` (`regenerate_message`)
- **Contract Clause**: §3 ("Every query scopes to the caller's `user_id`. Cross-user access returns 404, not 403.")
- **Description**: Both `POST /v1/messages/{assistant_message_id}/continue` and `POST /v1/messages/{assistant_message_id}/regenerate` query the target message using only `ChatMessage.account_id == principal.account_id`. In multi-user accounts, `ChatMessage` does not carry `user_id`, and neither endpoint joins or verifies that the parent `Conversation` belongs to `principal.user_id`. Consequently, User A can continue or regenerate User B's assistant messages, inspect User B's prior message content (`prior_content=msg.content`), and append new messages into User B's conversation.
- **Suggested Fix**: Join `Conversation` on `ChatMessage.conversation_id == Conversation.id` and filter `Conversation.user_id == principal.user_id` and `Conversation.deleted_at.is_(None)`. If the conversation or message is not owned by the calling `user_id`, raise `HTTPException(status_code=404, detail="message not found")`.

---

### High

#### 2. Cross-User Data Leakage During Idempotency Replay in Chat Stream
- **File & Line**: `src/daily_agent/routes/stream.py:157-170`
- **Contract Clause**: §3 ("Every query scopes to the caller's `user_id`. Cross-user access returns 404, not 403.") & §2 ("Idempotent on (conversation_id, client_message_id): a repeat returns the same run's events (replay) if it exists.")
- **Description**: The idempotency lookup in `POST /v1/chat/stream` filters only by `ChatMessage.client_message_id == body.client_message_id` and `ChatMessage.account_id == principal.account_id` without checking `Conversation.user_id == principal.user_id`. If User A supplies a `client_message_id` previously used by User B in the same account (or specifies User B's `conversation_id`), the server matches User B's message and replays User B's entire stream and assistant response to User A.
- **Suggested Fix**: Join `Conversation` in the idempotency query to enforce `Conversation.user_id == principal.user_id`. If `body.conversation_id` is supplied, ensure it matches `principal.user_id` before performing the lookup or raise 404.

#### 3. Startup Sweep Leaves Budget Reservations Permanently Locked
- **File & Line**: `src/daily_agent/streaming/registry.py:98-114`
- **Contract Clause**: §2.1 ("Budget: one reservation at run start, one settlement at terminal (exactly once), reusing existing services.py functions; Startup sweep: runs in streaming state at process start are set to interrupted").
- **Description**: `sweep_interrupted_runs` marks abandoned `Run` records as `interrupted` and `ChatMessage` records as `interrupted`, but does not release or settle their active `BudgetReservation` records. The reservations remain in `ReservationStatus.RESERVED` indefinitely, permanently holding `UsageWindow.reserved_micro`, `tokens_reserved`, and `PlatformBudget.reserved_micro` without freeing user quota after a process restart or crash.
- **Suggested Fix**: In `sweep_interrupted_runs`, look up all `BudgetReservation` records matching `run.logical_request_id` in `RESERVED` status and call `release_budget(session, reservation)` to refund the unspent quota.

#### 4. Unbounded Memory Growth in StreamRegistry (No Periodic Eviction & Stuck Runs)
- **File & Line**: `src/daily_agent/streaming/registry.py:65-82`
- **Contract Clause**: §2.1 ("Delta buffer per run: kept 10 minutes after the terminal event (then evicted).")
- **Description**: `evict_expired()` is only executed when `get()` or `has()` is called on `StreamRegistry`. For runs created via `POST /v1/chat/stream` that complete without clients reconnecting via `GET .../events`, `get()` is never called, and `_runs` grows unbounded in memory. Additionally, if an exception or cancellation occurs prior to `run.publish("run.finished")` or `run.publish("run.error")`, `state.terminal` remains `False`, and `evict_expired()` permanently ignores it because it filters strictly on `state.terminal and state.terminated_at is not None`.
- **Suggested Fix**: Trigger `evict_expired()` on every `register()` call or schedule a periodic background task (e.g. every 60 seconds). Also evict runs where `not state.terminal` if the run's task is done or older than a safety timeout (e.g. 15 minutes).

---

### Medium

#### 5. Synchronous Database Flushing Blocks Asyncio Event Loop
- **File & Line**: `src/daily_agent/streaming/runner.py:107-134` and `src/daily_agent/streaming/runner.py:227-228`
- **Contract Clause**: §2.1 ("Partial persistence: runs.partial_text and chat_messages.content are flushed at most once per 1.0 s or per 1 KB of new text, plus on terminal.")
- **Description**: `StreamRunner._flush_db` executes synchronous database operations (`session.scalar`, `session.get`, `session.commit`) directly inside `async def run()` on the asyncio event loop. Under concurrent stream load or database network latency/locking, periodic commits (every 1s / 1KB) block the single-threaded event loop, delaying heartbeats and streaming responses across all active connections.
- **Suggested Fix**: Wrap `_flush_db` with `await asyncio.to_thread(self._flush_db, ...)` or run database flushes asynchronously off the main event loop thread.

#### 6. Potential MultipleResultsFound Crash in Idempotency Check Without Conversation ID
- **File & Line**: `src/daily_agent/routes/stream.py:165-170`
- **Contract Clause**: §2 ("POST /v1/chat/stream body ... Idempotent on (conversation_id, client_message_id): a repeat returns the same run's events (replay) if it exists.")
- **Description**: When `body.conversation_id` is omitted, the query filters solely on `ChatMessage.client_message_id == body.client_message_id` and `ChatMessage.account_id == principal.account_id`. Because the unique constraint is `(conversation_id, client_message_id)`, two distinct conversations can share the same `client_message_id`. If this occurs, `session.scalar()` throws `sqlalchemy.exc.MultipleResultsFound`, triggering an internal 500 error instead of a graceful replay or fresh conversation creation.
- **Suggested Fix**: Use `session.scalars(...).first()` ordered by `ChatMessage.created_at.desc()` scoped to user conversations, or require `conversation_id` when resolving idempotency across existing threads.

#### 7. After_Seq Beyond Buffer Length Emits run.finished Instead of resume_unavailable
- **File & Line**: `src/daily_agent/routes/stream.py:77-89` and `src/daily_agent/routes/stream.py:353-357`
- **Contract Clause**: §2 ("If the buffer no longer covers N, emits run.error with category=resume_unavailable.")
- **Description**: When a client calls `GET /v1/runs/{run_id}/events?after_seq=N` with `N > run_state.last_seq` on an already-completed run, `stream_run_events` skips past delta events but emits `run.finished` at the end of the buffer. Because the buffer does not cover seq `N`, the endpoint should reject resumption with `run.error` category `resume_unavailable`.
- **Suggested Fix**: In `run_events`, if `after_seq > run_state.last_seq`, emit `run.error` with `category=resume_unavailable` and `retryable=false` rather than yielding `run.finished`.

---

### Low

#### 8. Historical Heartbeats Replayed in Burst on Stream Resume
- **File & Line**: `src/daily_agent/routes/stream.py:86-87`
- **Contract Clause**: §2 ("heartbeat {at} — sent every 15 s of silence. Not counted in seq.")
- **Description**: `stream_run_events` stores all `heartbeat` events in `run_state.events`. When a client reconnects with `after_seq > 0`, lines 86-87 yield all historical heartbeats encountered in the event log without checking whether the heartbeat occurred prior to `after_seq`. This sends an unnatural burst of stale heartbeats immediately upon reconnection.
- **Suggested Fix**: Do not yield historical heartbeat events during resume catch-up (`if evt.event == "heartbeat" and after_seq < 0`), or do not persist heartbeat frames in the replay delta buffer.

#### 9. Soft-Deleted Conversations Permit Continue and Regenerate Operations
- **File & Line**: `src/daily_agent/routes/stream.py:402-407` and `src/daily_agent/routes/stream.py:523-528`
- **Contract Clause**: §3 ("DELETE /v1/conversations/{id} → soft delete (deleted_at), 204. POST /v1/conversations/{id}/restore → ConversationView.")
- **Description**: Neither `continue_message` nor `regenerate_message` verifies that the conversation is active (`deleted_at.is_(None)`). If a conversation was soft-deleted, a user can continue or regenerate a message, appending new content and updating `last_message_at` without first calling `/restore`.
- **Suggested Fix**: Verify `Conversation.deleted_at.is_(None)` when validating the assistant message and parent conversation, returning HTTP 404 if soft-deleted.

#### 10. Unused Gateway Admission Slots Leaked in Streaming Endpoints
- **File & Line**: `src/daily_agent/routes/stream.py:223-225`, `src/daily_agent/routes/stream.py:449-451`, and `src/daily_agent/routes/stream.py:567-569`
- **Contract Clause**: §2.1 ("Budget: one reservation at run start, one settlement at terminal (exactly once), reusing existing services.py functions")
- **Description**: Each streaming endpoint invokes `admit_gateway_requests(session, settings, paid=..., slots=2)`. However, streaming invocations consume at most 1 gateway provider call, and unused slots are never returned via `return_gateway_requests(session, admission, used=1)`. This causes `GatewayRequestDay.requests_used` to accumulate 2 slots per stream request, prematurely depleting the daily capacity counter.
- **Suggested Fix**: Capture the `GatewayAdmission` object and return unused slots in `StreamRunner._settle_or_release_budget` via `return_gateway_requests(session, admission, used=1)`.

---

## No Issue Found (Verified Areas)

1. **SQL Injection and LIKE Escaping**:
   - `src/daily_agent/conversations/search.py:6-8` correctly escapes `\`, `%`, and `_` via `escape_like(term)`.
   - `src/daily_agent/conversations/service.py:392, 403, 437` consistently uses parameterized SQLAlchemy `.ilike(pattern, escape="\\")`. No raw SQL strings or unescaped LIKE queries exist.

2. **Chain-of-Thought Leakage**:
   - `src/daily_agent/gateway/adapters.py:244-248` extracts only `delta["content"]` and ignores reasoning/thought blocks.
   - `src/daily_agent/streaming/runner.py:209-224` only publishes user-facing text deltas to `message.delta`. Error payloads and processing cards omit model internal reasoning.

3. **Disconnect Handling**:
   - `src/daily_agent/routes/stream.py:91-94`: Client disconnection cancels the SSE generator (`stream_run_events`), which catches `asyncio.CancelledError` and exits cleanly. The underlying generation task (`run_state.task`) continues unaffected in the background registry as mandated by §2.1.

4. **Monotonic Sequence Numbering & Single Terminal Event**:
   - `src/daily_agent/streaming/runner.py:211, 220-224`: Sequence numbers start at 1 and increment monotonically per `message.delta`. `run.started` is emitted first with seq 0.
   - `src/daily_agent/streaming/runner.py:249, 273, 296`: Exactly one terminal event (`run.finished` or `run.error`) is published across normal completion, user stop/cancellation, and error paths.

5. **Search Route Precedence**:
   - `src/daily_agent/routes/conversations.py:58-80`: `@router.get("/search")` is declared before `@router.get("/{conversation_id}")`, avoiding path parameter routing shadowing.

6. **Keyset Pagination & Ordering**:
   - `src/daily_agent/conversations/service.py:175-231`: `list_conversations` correctly enforces `ORDER BY pinned DESC, updated_at DESC, id DESC` and encodes/decodes base64url keyset cursors.

7. **Soft Delete and Restore Correctness**:
   - `src/daily_agent/conversations/service.py:338-368`: `soft_delete` sets `deleted_at=now` (204 No Content), and `restore` clears `deleted_at`. Non-deleted queries strictly filter `deleted_at.is_(None)`.

8. **Auto-Title Generation**:
   - `src/daily_agent/conversations/service.py:44-50`: First 60 stripped characters of the initial message become the conversation title with `title_source="auto"`. `update_conversation` preserves user titles and updates `title_source="user"`.

9. **Provider Streaming Timeouts**:
   - `src/daily_agent/gateway/service.py:254, 313-350`: 20.0 s first-byte timeout and 30.0 s gap timeout are enforced by `_stream_with_timeouts` and mapped to `ProviderUnavailableError` (`retryable=True`).
