# Squad B handoff — persistence, management, search (branch r1/b)

## Backend
- `src/daily_agent/conversations/service.py`: `ensure_conversation_for_message(session, principal, conversation_id, first_user_text, now)` (Squad A calls this from the stream route; caller commits), `touch_conversation`, list/get/messages/update/soft_delete/restore/search, cursor codec, view mappers.
- `src/daily_agent/conversations/search.py`: `escape_like`, `make_snippet`.
- `src/daily_agent/routes/conversations.py`: 7 endpoints in contract order (`/search` declared before `/{id}`). Commits on PATCH/DELETE/restore.
- Tests: `tests/unit/test_conversations_service.py`, `tests/unit/test_conversations_routes.py`.

## Client
- `mobile/lib/api/conversations/conversations_api.dart`: `ConversationsApi` (list/search/get/messages/update/delete/restore/close).
- `mobile/lib/features/history/conversation_list_controller.dart`: `ConversationListController` (ChangeNotifier; optimistic rename/pin/archive/delete, debounced search, undo window).
- `mobile/lib/features/history/conversation_list.dart`, `conversation_actions.dart`, `search_field.dart`.
- `ConversationList` takes an extra required `controller` param (approved by Supervisor).
- Tests: `mobile/test/api/conversations/`, `mobile/test/features/history/`.

## Not in B (per Supervisor ruling)
- `mobile/lib/features/chat/composer/draft_store.dart` is owned by Squad E. B does not write it. Consumers key drafts as `draft.v1.<conversationId or "new">`.

## Needs (for integration)
- Squad A: call `ensure_conversation_for_message` inside the stream transaction before inserting the user message; call `touch_conversation` on assistant terminal.
- ChatWiring: construct `ConversationsApi` from `KarmiApi.baseUrl` plus `tokenProvider`; pass the controller into `ConversationList`.

## Checks run (manager, once)
- mypy (conversations + routes): Success, no issues in 4 source files.
- ruff check: All checks passed.
- pytest tests/unit/test_conversations_{service,routes}.py: all pass.
- flutter analyze (B paths): no issues after fixes.
- flutter test test/api/conversations test/features/history: 47 tests passed.
