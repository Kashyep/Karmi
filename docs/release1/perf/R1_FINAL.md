# Karmi Release 1 final: Item 2 measured performance (host only)

## 1. Scope and Status
- **Device frame timing**: NOT VERIFIED (device testing paused by owner).
- **Environment**: Host-only testing.
- **Providers**: No live model or provider calls; fake provider only.

## 2. Mobile Rebuild Metric
Evaluated via `test/perf/chat_perf_test.dart` (`chat_screen_subtree_rebuilds_per_send`).

| Measurement | Matcher | Runs | Median |
|---|---|---|---|
| Base `314afa4`, as originally reported | Substring matcher (`contains('Composer')`) | 12, 12, 12 | 12 |
| Base `314afa4`, corrected matcher | `Rebuilding Composer(` / `Rebuilding Composer-[` | 4, 4, 4 | 4 |
| Branch `bd92301`, corrected matcher | `Rebuilding Composer(` / `Rebuilding Composer-[` | 4, 4, 4 | 4 |

- **Measurement detail**: The 12 figure came from an overcounting matcher: the substring matcher `contains('Composer')` also counted FocusNode debug label `ComposerTextFieldFocus` lines, so it was not a true composer rebuild count. Corrected-matcher base is 4 and the branch stays 4 after the revert.
- **Assessment**: The <=9 target is met ONLY through metric correction. NO real rebuild reduction is claimed. The composer narrowing gave no reduction.

## 3. All-Widget Rebuilds Per Send
The composer ValueNotifier narrowing has been reverted. All-widget numbers below are as measured previously on the pre-revert branch (`bd92301`) using an instrumented copy of the test across 5 sends, counting raw `Rebuilding` lines:

| Commit | Runs | Samples (5 sends) | Min | Max | Median |
|---|---|---|---|---|---|
| Base `314afa4` | Identical across 3 runs | 365, 613, 647, 681, 715 | 365 | 715 | 647 |
| Branch `bd92301` (pre-revert) | Identical across 3 runs | 367, 615, 649, 683, 717 | 367 | 717 | 649 |

- **Assessment**: As measured on the pre-revert branch, no reduction was observed (+2 rebuilds per send). The narrowing has been reverted; no all-widget rebuild reduction is claimed.
## 4. Markdown Cache
- **Implementation**: Parsed AST cached per message id + content revision in a bounded LRU (`ParsedMarkdownCache`, commit `01db879`).
- **Effectiveness**: Parse-count effect NOT MEASURED.
- **Unit tests**: `test/features/chat/rendering/markdown_message_test.dart` (cache hit, streaming invalidation, bounded eviction): 18/18 pass.

## 5. Mobile Gates
- **Commit `5b79463`**:
  - `flutter analyze`: 0 issues.
  - `TZ=Asia/Kolkata flutter test --reporter=failures-only`: 1133 passed, 0 failed, 0 skipped.
- **Commit `bd92301`** (format only):
  - `dart format --output=none --set-exit-if-changed .`: exit 0 (223 files).
  - `flutter analyze`: No issues found.

## 6. Release APK Sizes
Build command: `flutter build apk --release --split-per-abi --obfuscate --split-debug-info=<~/.cache/karmi-tmp/symbols-r1f>` at commit `bd92301` (debug-signed via `KARMI_ALLOW_DEBUG_SIGNING=1` because no `key.properties` exists in the worktree).

| File | Bytes | MB ($10^6$) | MiB |
|---|---|---|---|
| `app-armeabi-v7a-release.apk` | 20,461,537 | 20.46 | 19.51 |
| `app-arm64-v8a-release.apk` | 23,003,669 | 23.00 | 21.94 |
| `app-x86_64-release.apk` | 24,552,977 | 24.55 | 23.42 |

- Baseline `app-profile.apk`: 85,714,285 B (85.71 MB / 81.74 MiB) is a universal profile build; NOT like-for-like with per-ABI release splits, so indicative only.
- Sibling `v0.1.0+4` APK: 63,239,627 B for reference.
- Release-signed build not produced (needs owner key).

## 7. Backend Chat Timing
Implemented in `ChatTimingMiddleware` (`src/daily_agent/chat_timing.py`; toggle env `DAILY_AGENT_CHAT_TIMING_ENABLED`).
Timing defaults to **OFF** (missing or empty -> disabled; "1", "true", "yes", or "on" -> enabled).

To enable for local benchmarking only:
```bash
DAILY_AGENT_CHAT_TIMING_ENABLED=1 python scripts/bench_chat_latency.py --compare
```

Bench: `scripts/bench_chat_latency.py --compare --rounds 3 -n 200 --warmup 10` (fake provider port 8765, backend 8766, token delay 0.005 s; alternating BEFORE [timing off] / AFTER [timing on]; fresh backend per pass).

| Metric | Round 1 | Round 2 | Round 3 | Median |
|---|---|---|---|---|
| Client p50 ms (BEFORE) | 124.84 | 127.19 | 125.02 | 125.02 |
| Client p50 ms (AFTER) | 127.88 | 131.61 | 127.38 | 127.88 |
| Client p95 ms (BEFORE) | 157.40 | 134.92 | 133.23 | 134.92 |
| Client p95 ms (AFTER) | 172.80 | 181.73 | 176.44 | 176.44 |
| Server p50 ms (AFTER) | 126.96 | 130.52 | 126.14 | 126.96 |
| Server p95 ms (AFTER) | 171.17 | 180.59 | 175.09 | 175.09 |

- **Middleware direct overhead (AFTER)**: p50 0.23 ms, p95 0.28 ms, mean 0.22 ms.
- **Open p95 question**: Client p95 gap is ~40 ms higher with timing on across 3 rounds (BEFORE median 134.92 ms vs AFTER median 176.44 ms), despite middleware direct overhead p95 being only 0.28 ms. Cause not identified; owner decision needed. Timing defaults to OFF until this is resolved.

## 8. Backend Gates
- `scripts/tasks.py lint`: exit 0 after ruff fix commit `c47425b`.
- `typecheck`: exit 0 (63 files).
- `test-unit`: 404 passed, 1 skipped on the pre-lint-fix code (formatting-only change since; rerun reported separately).

## 9. Not Verified / Residual Risks
- Device frame timing NOT VERIFIED (paused by owner).
- Release-signed APK not built (requires owner key).
- Markdown-cache parse-count effect NOT MEASURED.
- Composer narrowing gave no measured reduction (+2 on all-widget rebuilds on pre-revert branch) and was reverted (composer behaviourally matches base `314afa4`).
- Backend chat timing default stays OFF due to unexplained client p95 latency gap (~40 ms higher with timing on across 3 rounds, middleware direct overhead p95 0.28 ms, cause not identified, owner decision needed).
