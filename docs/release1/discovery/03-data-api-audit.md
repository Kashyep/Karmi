# Discovery 03 — Data and API audit (PHASE 0, read-only)

Source: explorer ExtensiveHawk, 2026-10-21.

## Alembic
- Head `5f708192a3b4`. Linear chain of 15 revisions from `92174af1e5c5`. No branches.

## Tables (src/daily_agent/models.py)
- accounts(id, name, created_at); users(id, account_id, display_name, role, token_version, clerk_subject unique, unlocked_tier 1-4, active_theme 1-4)
- subscriptions(account_id unique, plan_id, policy_version, status, event_version, period_anchor)
- usage_windows(daily: everyday_limit/used, spend/reserved/settled micro, token_limit/tokens_reserved/tokens_settled, reset_at)
- usage_periods(monthly spend), platform_budgets, gateway_request_days (global daily pool)
- budget_reservations(logical_request_id, stage, reserved_micro, actual_micro, reserved_tokens, status), cost_ledger
- tasks, reminders, inbox_events, billing_events, outbox_events
- runs(id, account_id, user_id, logical_request_id, request_hash, status, outcome, response_text Text, generation, previous_run_id, regenerate_reason). **No prompt text stored** (only request_hash, api.py:404). No conversation_id, no role/content/tokens/created_at.
- message_feedback(run_id, rating up|down, reason)
- routing_records, routing_decisions, policy_bundles, policy_bundle_events

**No conversations table, no messages table.** Prompt text is not persisted, so regenerate must resend text (RegenerateCreate.text validated against hash).

## Routes (21)
GET /health (api.py:133), GET /ready (:137), POST /dev/token (:149), GET /admin/overview (:161), GET /admin/runs (:182), GET /v1/usage (:199), GET /v1/armory (:244), PUT /v1/armory/active-theme (:263), GET /v1/tasks (:288), POST /v1/tasks (:298), PATCH /v1/tasks/{id}/complete (:331), POST /v1/reminders (:350), **POST /v1/messages (:577)**, POST /v1/access-code (:599), POST /v1/runs/{id}/feedback (:636), POST /v1/runs/{id}/regenerate (:675), POST /webhooks/internal-test (:706), POST /webhooks/billing-sandbox (:733), GET / (:800), GET /static/{path} (:804), GET /manifest.webmanifest (:812).

## Stream protocol
- NONE. No SSE, WebSocket or chunked encoding.
- Provider adapters hard-code `"stream": False` (gateway/adapters.py:114; opencode.py:140).
- POST /v1/messages blocks and returns MessageView(run_id, status, outcome, response, route, previous_run_id).
- No heartbeats, no seq ids, no Last-Event-ID.

## Output / input limits
- MAX_OUTPUT_TOKENS = 4096 for all plans (adapters.py:25). Owner decision 2026-10-21: no per-plan reply-length cap while models are free.
- Input tokens per plan: ananta 4,000; yanta 8,000; trika 16,000; parth 32,000.
- MessageCreate.text max 100,000 chars (schemas.py:36); adapter MAX_PROMPT_CHARS = 120,000.
- Provider timeout 20s (OpenRouter and OpenCode); MAX_ATTEMPTS = 2 (gateway/service.py:28), one fallback model.
- finish_reason: OpenRouter parses it; OpenCode sets None. validate_output (gateway/service.py) rejects only content_filter, empty and Devanagari-missing cases. **finish_reason=length is accepted silently** (no truncation flag, no continue).

## Uploads and search
- Uploads: none. No multipart route, no storage, no attachment fields.
- Search: none. No FTS/trigram/ilike endpoint.

## Usage
- INR_MICRO accounting. Daily request count and daily tokens per usage_windows (UTC midnight reset). Monthly spend per usage_periods.
- Plans: Ananta ₹0 20 req/day 40k tok/day; Yanta ₹149 100 req/day 300k tok/day; Trika ₹399 250 req/day 800k tok/day; Parth ₹899 500 req/day 2M tok/day.
- Errors: 429 ALLOWANCE_EXHAUSTED, 429 BETA_CAPACITY_FULL, 409 ReservationInFlight.

## Flutter API client (mobile/lib/api)
- KarmiApi: issueDevToken, sendMessage, sendFeedback, regenerateRun/regenerateMessage, redeemAccessCode, getUsage, listTasks, completeTask, getArmory, setActiveTheme. Exceptions: Network, Server, Unauthorized, TierLocked, InFlight, IdempotencyConflict, LimitReached, BetaCapacityFull.
- Models: Outcome, FeedbackRating, FeedbackReason, RunFeedbackView, MessageView, UsageView, TaskView, ArmoryView, AccessCodeResult.
- No stream client, no conversation/search/attachment models.

## Gaps for R1 items 1, 2, 4, 6
- 1 streaming: SSE route, typed events, seq ids, resume buffer, finish_reason=length detection, continuation route.
- 2 persistence: conversations and messages tables; CRUD and search routes; soft delete with undo.
- 4 rich content: structured message parts (text/code/table/citation/artifact/file).
- 6 composer: attachments table and upload route.

## Additive migrations the explorer proposed (inputs to the contract)
1. conversations; 2. messages; 3. message_parts; 4. attachments; 5. nullable runs.conversation_id and runs.message_id.
