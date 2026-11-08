# Markdown AST Parse Counts: With vs Without `ParsedMarkdownCache`

**Date**: 2026-11-08  
**Branch**: `r1f/perf-parse`  
**Base Commit**: `2cc5ad7`  
**Test Suite**: `mobile/test/features/chat/rendering/markdown_message_test.dart`  
**Verification Command**: `TMPDIR=~/.cache/karmi-tmp flock /tmp/karmi-heavy.lock flutter test test/features/chat/rendering/markdown_message_test.dart`

---

## 1. Overview & Purpose

Section 4 of `docs/release1/perf/R1_FINAL.md` noted:
> - **Implementation**: Parsed AST cached per message id + content revision in a bounded LRU (`ParsedMarkdownCache`, commit `01db879`).
> - **Effectiveness**: Parse-count effect NOT MEASURED.
> - **Unit tests**: `test/features/chat/rendering/markdown_message_test.dart` (cache hit, streaming invalidation, bounded eviction): 18/18 pass.

This document records the deterministic before/after parse count measurements comparing execution **with** vs **without** `ParsedMarkdownCache` across host widget and unit tests.

---

## 2. Measurement Methodology & Instrumentation

To count AST parses deterministically with zero production behavior change:
1. `ParsedMarkdownCache` supports `enabled: true` (default) and `ParsedMarkdownCache.disabled()` (pass-through mode that parses on every call without retaining AST nodes).
2. `MarkdownMessage` exposes test-visible hooks:
   - `MarkdownMessage.debugParseCount`: increments each time the Markdown parser document generator (`md.Document.parseLines`) is invoked.
   - `MarkdownMessage.debugDisableCache`: test-only flag to simulate un-cached widget trees without modifying application code.
   - `MarkdownMessage.debugResetParseCount()`: resets the counter between runs.
3. Every test validates the deterministic invariant:
   - **With cache**: `parses == distinct (id, revision) pairs`
   - **Without cache**: `parses == rebuilds * messages`

---

## 3. Results Summary

| Scenario | Messages | Rebuilds / Pumps | Distinct `(id, rev)` Pairs | Uncached Parses (`rebuilds * messages`) | Cached Parses (`distinct pairs`) | Cache Hits | Parse Reduction |
|---|---|---|---|---|---|---|---|
| **Long conversation rebuilds** | 30 | 20 | 30 | **600** | **30** | 570 | **-95.0%** (20x) |
| **Streaming message deltas** | 1 | 45 (15 deltas × 3 pumps) | 15 | **45** | **15** | 30 | **-66.7%** (3x) |
| **Conversation with streaming message** | 30 (29 static + 1 streaming) | 20 (10 deltas × 2 pumps) | 39 (29 static + 10 deltas) | **600** | **39** | 561 | **-93.5%** (15.4x) |

---

## 4. Scenario Breakdown

### Scenario A: Long Conversation Rebuilds (30 messages, N=20 rebuilds)
- **Setup**: A chat conversation widget host with 30 messages (`msg-0` through `msg-29`), each containing Markdown formatting (bold, code, links). The entire conversation is pumped through 20 full rebuilds.
- **Without Cache**:
  - Rebuild 0: 30 parses.
  - Rebuilds 1–19: 30 parses per rebuild.
  - Total parses: $20 \times 30 = \mathbf{600}$.
  - Cache hits: $0$.
- **With Cache**:
  - Rebuild 0: 30 parses (initial cache misses).
  - Rebuilds 1–19: 0 parses ($19 \times 30 = 570$ cache hits).
  - Total parses: $\mathbf{30}$ (exactly equals the 30 distinct message pairs).
  - Parse reduction: **570 fewer parses (-95.0%)**.

### Scenario B: Streaming Message Deltas (1 message, 15 deltas, 3 pumps per delta)
- **Setup**: A streaming assistant message that receives 15 incremental token deltas (growing content revision). At each delta, the widget tree undergoes 3 rebuilds (simulating incremental layout/scroll/timer pumps). Total pumps = 45.
- **Without Cache**:
  - Every pump re-parses the accumulated Markdown string.
  - Total parses: $15 \times 3 = \mathbf{45}$.
  - Cache hits: $0$.
- **With Cache**:
  - On the first pump of each new token delta: 1 parse (new revision key).
  - On the subsequent 2 pumps of the same delta: 0 parses (cache hits).
  - Total parses: $\mathbf{15}$ (exactly equals the 15 distinct token revisions).
  - Cache hits: $30$.
  - Parse reduction: **30 fewer parses (-66.7%)**.

### Scenario C: Long Conversation with Active Streaming Message
- **Setup**: A conversation with 29 completed static messages plus 1 active assistant message receiving 10 token deltas. For each delta, the conversation rebuilds 2 times ($N = 20$ conversation rebuilds, 30 messages in the tree).
- **Total Widget Evaluations**: $20 \times 30 = 600$.
- **Distinct (id, revision) Pairs**: $29 \text{ static} + 10 \text{ deltas} = 39$.
- **Without Cache**:
  - Parses: $20 \times 30 = \mathbf{600}$.
- **With Cache**:
  - 29 static messages parsed once on rebuild 0, hitting cache for all subsequent 19 rebuilds ($29 \times 19 = 551$ hits).
  - 1 streaming message parsed once per delta (10 parses), hitting cache on the duplicate pump of each delta (10 hits).
  - Total parses: $29 + 10 = \mathbf{39}$.
  - Total hits: $551 + 10 = \mathbf{561}$.
  - Parse reduction: **561 fewer parses (-93.5%)**.

---

## 5. Test Suite Verification

Both unit and host widget tests pass deterministically:
```
00:00 +18: ParsedMarkdownCache parse counting: cached vs uncached unit: 20 rebuilds of 30 messages has deterministic parse counts
00:00 +19: ParsedMarkdownCache parse counting: cached vs uncached unit: streaming message with 15 deltas and 3 rebuilds per delta
00:00 +20: ParsedMarkdownCache parse counting: cached vs uncached host widget: N=20 rebuilds of a long conversation (30 messages)
00:01 +21: ParsedMarkdownCache parse counting: cached vs uncached host widget: streaming message across growing content (15 deltas x 3 rebuilds)
00:01 +22: ParsedMarkdownCache parse counting: cached vs uncached host widget: 30-message conversation with streaming message across 20 rebuilds
00:02 +23: All tests passed!
```
