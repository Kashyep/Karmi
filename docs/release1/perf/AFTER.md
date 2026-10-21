# R1 perf AFTER (final QA re-measurement)

Source SHA (worktree `/tmp/wt-finalqa`, branch `r1/finalqa`): `e9dd199`.
Baseline source: `dcf4f75` (see BASELINE.md).

Machine: linux 7.2.11-arch1-1, x64. Flutter version not re-checked for this run; BASELINE.md records 3.47.5.

Command: `cd mobile && TZ=Asia/Kolkata flutter test test/perf/chat_perf_test.dart --reporter expanded`, run twice.

**All numbers are host-VM widget-test proxies, not device measurements.**

## Before / after

| Metric | Before (`dcf4f75`, BASELINE.md) | After (`e9dd199`, run 1 / run 2) |
|---|---|---|
| Cold start proxy, pumpApp median | 313 ms (run 1), 337 ms (run 2) | 215.3 ms / 209.8 ms |
| Cold start proxy, pumpApp p95 (n=7) | 1521 ms (run 1), 2075 ms (run 2) | 2022.3 ms / 1359.9 ms |
| Chat list scroll frame pump, median (90 frames) | 0.11 ms | 0.11 ms / 0.11 ms |
| Chat list scroll frame pump, p95 (90 frames) | 5.26 ms | 7.86 ms / 7.85 ms |
| Rebuilds per send, ChatScreen/MessageBubble/_UserRow/Composer (filtered log) | 3, 6, 9, 12, 15 (median 9) | 11, 18, 20, 22, 24 (median 20), both runs |
| Rebuilds per send, all widgets (unfiltered) | 398 to 836 per send | NOT MEASURED. The perf file has no unfiltered case; the figure in the test's note string is a hard-coded carry-over from the baseline, not a measurement. |
| Streaming frame timing | NOT MEASURED | NOT MEASURED. The fake backend still returns one `message.delta` per reply, so there is no token stream. |
| Device frame timings / jank | NOT MEASURED | NOT MEASURED. No device attached. |
| Release APK size | NOT MEASURED | NOT MEASURED. The release APK build was skipped (did not finish in the prior session). |

## Method comparison

- Test file logic (cold start loop, 90-step drag scroll with `pump(16ms)`, rebuild filter on `debugPrintRebuildDirtyWidgets` with the same four widget names, 5 sends) reads as identical to the baseline test body. The file header is a few lines longer in this worktree, and the source SHAs differ.
- The harness (`test/support/harness.dart`, `fake_backend.dart`) was not diffed against the baseline tree; it may differ.
- The rebuild-count delta is therefore a change in the code under test plus a possibly unchanged method. It is only a valid before/after comparison if the harness is identical. This was not verified.

## Honest interpretation

- The scroll-frame median (0.11 ms) is unchanged. The p95 rose from 5.26 ms to about 7.85 ms, consistently across both runs. That is a real host-VM signal under this harness, but 90 frames gives a noisy p95 and a harness difference cannot be ruled out.
- The rebuild counts rose from a median of 9 to 20 per send. Both runs agree exactly. Because the filter is a debug-log text match, this is a proxy, and it is only comparable if the harness matched.
- Cold start is noise-dominated. With 7 samples per run, p95 is effectively the single largest sample and varied from 1360 ms to 2022 ms across two runs of the same code. The median moved from 313-337 ms to 210-215 ms, which is within what a 7-sample run can produce. Do not read a cold-start improvement or regression from these numbers.
- None of these numbers say anything about device jank, raster cost, or APK size.

## Commit

`docs(r1/qa): perf AFTER measurements`
