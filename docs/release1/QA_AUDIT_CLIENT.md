# Client Quality Assurance Audit (Karmi R1)

Date: 2026-10-22  
Scope: `mobile/lib/features/chat/**`, `mobile/lib/api/stream/**`, `mobile/lib/features/history/**`

## Summary of Findings

| Severity | Count |
|:---|:---:|
| **Critical** | 0 |
| **High** | 2 |
| **Medium** | 2 |
| **Low** | 1 |
| **Total** | 5 |

---

## Detailed Findings Table

| ID | Severity | File:Line | Issue | Suggested Fix |
|:---|:---|:---|:---|:---|
| **AUDIT-01** | High | `mobile/lib/features/chat/chat_screen.dart:171-198` | **Active Stream Not Cancelled on Conversation Switch**: In `_loadConversationMessages()`, the network call `await _conversationsApi.messages(conversationId)` is awaited before disposing `_chatController`. If a stream is active when the user switches conversations, it continues receiving and appending SSE tokens to the old controller during the fetch. Furthermore, if `messages()` throws an exception, the old controller is never disposed. | Cancel/dispose the existing `_chatController` or call `_chatController.stop()` synchronously before initiating `_conversationsApi.messages()`. |
| **AUDIT-02** | High | `mobile/lib/features/chat/composer/draft_store.dart:14` | **Draft Storage Key Lacks User Scoping**: `SharedPrefsDraftStore.storageKey(key)` uses `'draft.v1.$key'`. Because the key does not incorporate the authenticated user's ID, drafts (notably `draft.v1.new` for new chats) persist across user logout/login on the same device, leaking draft messages across users. | Scope draft storage keys by user ID: `'draft.v1.$userId.$key'`, or clear user-associated drafts on sign-out. |
| **AUDIT-03** | Medium | `mobile/lib/features/history/conversation_actions.dart:89` | **TextEditingController Leak in Rename Dialog**: `showRenameDialog` instantiates `final textController = TextEditingController(...)` but never disposes it after `showDialog<void>` completes. | Wrap the dialog in a `try/finally` block and call `textController.dispose()` in `finally`, or manage the controller within a dedicated `StatefulWidget`. |
| **AUDIT-04** | Medium | `mobile/lib/features/chat/chat_screen.dart:428-432` | **Unread Indicator Dropped on Jump to Latest Button**: `ValueListenableBuilder<bool>` listens to `_scrollController.hasNewContent`, but `hasNewContent` is omitted when instantiating `JumpToLatestButton`, defaulting it to `false`. As a result, the button never displays the "New messages" badge or semantics label when new content arrives while scrolled up. | Pass `hasNewContent: hasNewContent` to `JumpToLatestButton` at line 430. |
| **AUDIT-05** | Low | `mobile/lib/features/chat/composer/attachment_chip.dart:60` | **Undersized Tap Target on Attachment Removal**: The remove `IconButton` on `AttachmentChip` specifies `constraints: BoxConstraints(minWidth: 24, minHeight: 24)` and `padding: EdgeInsets.zero`, failing the 48dp minimum accessible touch target recommendation. | Increase touch target bounds to 48x48dp using standard padding or `TouchTargetPadding`. |

---

## Audit Checklist & Verification

### 1. Stream Lifecycle Leaks
- **RunStreamClient**: SSE connections are consumed via `SseParser.parseBytes(response.stream)` with socket and HTTP timeout handlers (`mobile/lib/api/stream/run_stream_client.dart:203-311`).
- **ChatController**: Disposes `_deltaFlushTimer`, `_stallTimer`, and cancels `_streamSubscription` in `dispose()` (`mobile/lib/features/chat/state/chat_controller.dart:360-369`).
- **ConversationListController**: Disposes `_searchTimer` and `_undoTimer` in `dispose()` (`mobile/lib/features/history/conversation_list_controller.dart:368-376`).
- **EndAnchoredScroll**: Removes scroll listener on dispose; disposes owned controllers (`mobile/lib/features/chat/scroll/end_anchored_scroll.dart:104-111, 206-212`).
- **MarkdownMessage**: Properly cleans up `TapGestureRecognizer`s both in `dispose()` and at the start of each `build()` (`mobile/lib/features/chat/rendering/markdown_message.dart:71-82, 647`).
- **Issues Found**:
  - `showRenameDialog` leaks `TextEditingController` (see **AUDIT-03**).
  - Stream not immediately aborted prior to conversation message loading (see **AUDIT-01**).

### 2. Chain-of-Thought (CoT) Exposure
- **Status**: **PASS**
- **Verification**:
  - Models (`ChatMessageView`, `RunEvent`) contain no reasoning or CoT fields (`mobile/lib/api/chat/chat_models.dart`, `mobile/lib/api/chat/chat_events.dart`).
  - `ProcessingPanel` displays only staged progress labels ("Preparing", "Writing", "Still working…") and explicitly disallows reasoning output (`mobile/lib/features/chat/processing_panel.dart:5, 27-44`).
  - No message content or tokens are logged via `print`, `debugPrint`, or logging frameworks.

### 3. Link & HTML Safety
- **Status**: **PASS**
- **Verification**:
  - `MarkdownMessage` enables `encodeHtml: true` with `ExtensionSet.gitHubWeb`, escaping raw HTML tags into text nodes (`mobile/lib/features/chat/rendering/markdown_message.dart:60-64`).
  - `isSafeLinkUri` strictly validates that schemes are `http`, `https` (requiring a non-empty host) or `mailto` (`mobile/lib/features/chat/rendering/safe_link.dart:9-18`).
  - Dangerous URL schemes (`javascript:`, `data:`, `file:`) are rejected and rendered as non-interactive text spans (`mobile/lib/features/chat/rendering/markdown_message.dart:185-190`).
  - No links are auto-launched; links open only upon explicit user tap via `openSafeLink` (`LaunchMode.externalApplication`).

### 4. Draft Handling
- **Status**: **PARTIAL (Issue AUDIT-02)**
- **Verification**:
  - Keying: Draft keys are passed per conversation (`_activeConversationId ?? 'new'`) (`mobile/lib/features/chat/chat_screen.dart:456`).
  - Saving: Text edits schedule debounced draft saves at 300ms, and unmount triggers immediate save (`mobile/lib/features/chat/composer.dart:125, 145`).
  - Clearing: Draft store is explicitly cleared on send: `_draftStore.clear(widget.draftKey)` (`mobile/lib/features/chat/composer.dart:259`).
  - Leaks: Drafts are not scoped by `user_id`, causing cross-user leakage on shared devices (see **AUDIT-02**).

### 5. Scroll Behaviour
- **Status**: **PASS (Minor Issue AUDIT-04)**
- **Verification**:
  - Bottom Anchoring: While pinned (`isAtBottom == true`) and user is not gesturing, content growth triggers `jumpTo(currentMax)` to track the stream (`mobile/lib/features/chat/scroll/end_anchored_scroll.dart:272-278`).
  - User Scroll-Up: User scrolling past `bottomThreshold` (48dp) unpins `isAtBottom` and sets `hasNewContent` to `true` on subsequent stream growth (`mobile/lib/features/chat/scroll/end_anchored_scroll.dart:280-285`).
  - Jump to Latest: Floating button appears when `!isAtBottom` and smoothly scrolls/jumps to the bottom extent on click (`mobile/lib/features/chat/chat_screen.dart:429-431`).
  - Issue: `hasNewContent` listenable is not passed through to `JumpToLatestButton` (see **AUDIT-04**).

### 6. Accessibility & Semantics
- **Status**: **PASS (Minor Issue AUDIT-05)**
- **Verification**:
  - Send Button: `Semantics(button: true, label: widget.busy ? 'Stop generating' : 'Send message')` (`mobile/lib/features/chat/composer.dart:373-375`).
  - Jump to Latest: `Semantics(button: true, label: semanticsLabel, container: true, excludeSemantics: true)` (`mobile/lib/features/chat/scroll/jump_to_latest_button.dart:126-135`).
  - Error Card: `Semantics(container: true, liveRegion: true, label: message)` (`mobile/lib/features/chat/error_card.dart:81-84`).
  - Message Bubbles: `Semantics(container: true, liveRegion: announce, label: isUser ? 'You said' : 'Karmi replied')` (`mobile/lib/features/chat/message_bubble.dart:162-167`).
  - Touch Targets: Send button, Jump to Latest, Feedback buttons, and Error Card actions all guarantee $\ge 48\times 48\text{dp}$. `AttachmentChip` close button is undersized at $24\times 24\text{dp}$ (see **AUDIT-05**).

### 7. Error Category Mapping
- **Status**: **PASS (100% Mapped)**
- **All 8 categories** from `ErrorCategory` (`mobile/lib/api/chat/chat_models.dart:44-53`) are mapped to user-facing copy and icons in `ErrorCard` (`mobile/lib/features/chat/error_card.dart:21-72`):

| ErrorCategory Wire Name | User-Facing Message | Retryable | User Action |
|:---|:---|:---:|:---|
| `quota_exhausted` | *"You've reached your plan limit for now."* | No | View plans |
| `capacity_full` | *"Karmi is busy right now."* | Yes | Try again |
| `provider_unavailable` | *"The model service had a problem."* | Yes | Retry |
| `validation_failed` | *"This reply was blocked or came back empty."* | Yes | Regenerate |
| `unauthorized` | *"Your session expired. Sign in again."* | No | Sign in |
| `resume_unavailable` | *"Connection lost. Partial reply kept."* | No | Continue |
| `network` | *"You appear to be offline."* | Yes | Retry |
| `internal` | *"Something went wrong."* | Yes | Retry |
