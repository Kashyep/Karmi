# Phase 2 ChatWiring handoff

Branch `r1/wiring` (from `release1/chat-redesign`).

- ChatScreen runs on `ChatController` (streaming via `POST /v1/chat/stream`, `RunStreamClient`), with Composer(draftKey, busy, onSubmit, onStop), EndAnchoredScroll + JumpToLatestButton, MarkdownMessage for assistant text, ProcessingPanel and ErrorCard recovery actions (Retry, Continue, Resume, Stop, Regenerate).
- Thumbs feedback stays on MessageBubble and uses the legacy feedback API.
- New Chat creates no record. Conversation id is assigned on first send.
- History rail: `KarmiShell.historyRailBuilder` with ConversationList and ConversationListController (wide layouts); drawer on mobile.
- UsageWarningPill renders inline in usage screen at >= 80%.
- `ChatRunPhase` lives only in `state/chat_controller.dart`.
- Legacy `KarmiApi` methods unchanged; `client` getter added for stream and conversations reuse.
- Goldens regenerated: `glass_legibility_dark.png` (rim alpha 0.18); chat/chat_empty/settings/tier_chat goldens (new chat UI) in commit 408661a.

Checks: `flutter analyze` clean. `TZ=Asia/Kolkata flutter test`: 536 passed, 0 failed.
