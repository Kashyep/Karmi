# Discovery 02 — Chat UX inventory and R1 gap analysis (PHASE 0, read-only)

Source: explorer ObedientAlligator, 2026-10-21.

| Component | File:lines | Responsibility today | Gap vs R1 |
|---|---|---|---|
| ChatScreen | features/chat/chat_screen.dart:16-378 | `_entries` List<ChatEntry>, `_scroll`, `_pending`, `_actionError`; send/deliver/retry/feedback/regenerate; `ListView.builder` with sticky Composer (:280-360) | In-memory only; no threads, no search, no New Chat reset; no end-anchored scroll or Jump to Latest; single loader |
| _UserRow | chat_screen.dart:401-445 | user bubble + delivery StatusChip | no in-stream recovery card; retry only via chip |
| MessageBubble | features/chat/message_bubble.dart:13-112 | `readableProseWidth` (88% / 38em); `Text()` only (reply :76) | No markdown, code highlight/copy, tables, citations, file chips |
| _ReplyActions | message_bubble.dart:114-200 | thumbs up/down, FeedbackReason chips, regenerate | no copy response, no edit prompt, no version navigation |
| Composer | features/chat/composer.dart:9-96 | TextField 1–5 lines inside KarmiGlassSurface; IME send | no draft persistence; no attachments; no long-paste chip (>2,500 chars); no Enter vs Shift+Enter; no Stop |
| StatusChip | features/chat/status_chip.dart:13-84 | ACCEPT/DEFERRED/ASK_USER/UNKNOWN + delivery states | no streaming status states |
| TaskConfirmationSheet | features/tasks/task_confirmation_sheet.dart:31-105 | modal for askUser outcome | raw response only |
| KarmiShell | shell/karmi_shell.dart:35-214 | 4 tabs in IndexedStack; GlassScaffold vs Scaffold | no tablet/desktop breakpoints, no history rail, no drawer |
| KarmiLoader | widgets/feedback.dart:9-48 | spinner; hourglass under reduced motion | no staged processing accordion |
| EmptyState | widgets/feedback.dart:51-92 | empty state | not chat-aware |

## Missing R1 features (anchored)
- Item 1 streaming controls: none (no Continue/Resume/Stop/Regenerate-in-stream).
- Item 2 persistence: no history list, rename/pin/archive/delete/undo, no drafts.
- Item 3 workspace: no history rail, no Jump to Latest, no end-anchored scroll.
- Item 4 rendering: none (see table above).
- Item 5 states: no processing accordion, no categorized recovery cards.
- Item 6 composer: see Composer row.
- Item 8: dark-mode specular border patch and inline 80% quota pill absent. Reduced-motion and reduced-transparency are already structured (theme/, KarmiLoader).

## Tests baseline
- Golden coverage: 32 phone permutations (light/dark, 1.0x/2.0x, glass/opaque, tiers), single 412x915 size. No tablet golden.
