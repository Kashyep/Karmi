# Squad D handoff: safe rich renderer (branch r1/d)

## Files (new, owned per contract §6)
- mobile/lib/features/chat/rendering/markdown_message.dart: `MarkdownMessage({text, streaming, allowCollapse})`
- mobile/lib/features/chat/rendering/code_block.dart: `CodeBlock({code, language})` (language label, copy, wrap toggle, long-code fold)
- mobile/lib/features/chat/rendering/table_view.dart: `TableView({rows, alignments})` (horizontal scroll)
- mobile/lib/features/chat/rendering/citation_chip.dart: `CitationChip({index})`
- mobile/lib/features/chat/rendering/file_chip.dart: `FileCard({name, content})` (lazy preview)
- mobile/lib/features/chat/rendering/long_output_fold.dart: `LongOutputFold({child, collapsible, maxHeight})`
- mobile/lib/features/chat/rendering/safe_link.dart: `isSafeLinkUri`, `openSafeLink` (http, https, mailto only)
- mobile/test/features/chat/rendering/markdown_message_test.dart (8 widget/unit tests)
- mobile/test/features/chat/rendering/markdown_golden_test.dart (tag golden)
- mobile/test/features/chat/rendering/goldens/markdown_message_basic.png (generated on Linux)

## Conventions for other squads (needs)
- Attachment (D2) marker: a fenced block with info string `file:<name>`. Squad E (composer inlining) and A must emit this exact form when inlining text attachments.
- Citations: inline `[n]` (digits, not followed by `(`) renders as CitationChip.
- Collapse applies only when `allowCollapse && !streaming` and text > 4000 chars or > 60 lines.

## Design notes
- No raw HTML: `markdown` parsed with `ExtensionSet.gitHubWeb`, HTML is shown as literal text.
- No hardcoded colours; `KarmiColors` read nullable with colorScheme fallback (KarmiTokens not yet on branch).
- Unclosed fences are rendered as code to end-of-text during streaming (package behaviour).
- Images render alt text only (no network loads).

## Checks run (worktree)
- `dart format --output=none --set-exit-if-changed` on rendering dirs: formatted in place.
- `flutter analyze lib/features/chat/rendering test/features/chat/rendering`: No issues found.
- `TZ=Asia/Kolkata flutter test test/features/chat/rendering/markdown_message_test.dart`: All 8 passed.
- `TZ=Asia/Kolkata flutter test --tags golden --update-goldens test/features/chat/rendering/markdown_golden_test.dart`: baseline generated, passed.

## Risks / remaining
- Only one golden; no QA contrast checks on rendered colours.
- LongOutputFold always reserves maxHeight when collapsible (only used for long content).
- CitationChip is non-interactive (no source list exists in R1 data).
