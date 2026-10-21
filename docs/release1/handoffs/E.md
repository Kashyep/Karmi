# Squad E handoff — composer, processing, recovery

Branch `r1/e` (worktree `/tmp/wt-e`), based on `release1/chat-redesign` 8d4cb3a.
Commits: b0f0fdc, 4e0a9b3, 7b2d17e, c79920d, 4cc6ca3.

## Files
- `mobile/lib/features/chat/composer.dart` (replaced): `Composer({draftKey, busy, onSubmit, onStop, draftStore?, onPickAttachments?})`, `ComposerSubmit{text, attachments}`.
- `mobile/lib/features/chat/composer/draft_store.dart`: `DraftStore {load, save, clear}` interface + `SharedPrefsDraftStore` (key `draft.v1.<draftKey>`). Owned by E per Supervisor ruling; B consumes only.
- `mobile/lib/features/chat/composer/text_attachment.dart`: D2 validator (≤3 files, ≤40,000 chars each, ≤60,000 total, text-only, NUL rejected).
- `mobile/lib/features/chat/composer/paste_chip.dart`: `longPasteThreshold = 2500`, expand/collapse/remove.
- `mobile/lib/features/chat/composer/attachment_chip.dart`.
- `mobile/lib/features/chat/processing_panel.dart`: `ProcessingPanel({phase})`, `ChatRunPhase` enum (temporary local definition, see Needs).
- `mobile/lib/features/chat/error_card.dart`: `ErrorCard({category, onRetry, onContinue, onUpgrade})`, `messageFor`, `isRetryable`.

## Tests (own, new files)
- `mobile/test/features/chat/composer/{composer,text_attachment,draft_store}_test.dart`
- `mobile/test/features/chat/{processing_panel,error_card}_test.dart`

## Checks (manager, combined tree)
- `flutter analyze` on owned files: No issues found.
- `TZ=Asia/Kolkata flutter test test/features/chat`: 44 passed, 0 failed.
- `dart format`: clean (composer files).

## Needs / merge items
1. `ChatRunPhase` is defined in `processing_panel.dart` only because Squad A's `features/chat/state/chat_controller.dart` is not in this tree. At merge, delete the local enum and import it from A's file. Do not keep two definitions.
2. Phase 2 (`chat_screen.dart`) must switch from old `Composer(onSend, isPending)` to the new constructor, and may pass `onPickAttachments`.
3. Error categories follow the contract (§2.2), not the wording in the task brief: rate_limited→`capacityFull`, server→`providerUnavailable`, content_filter→`validationFailed`. `RecoveryBar` was not built (not in contract §7).
4. Error card copy needs Squad F/UX review.
5. Test location `mobile/test/features/chat/**` is under QA-owned `mobile/test/**` in §6; these are own-module tests as required by the wave-1 brief. QA may keep or move them.
