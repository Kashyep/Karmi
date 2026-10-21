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

Rebuild-count row is per send, not per delta.

## Method comparison

- Test file logic (cold start loop, 90-step drag scroll with `pump(16ms)`, rebuild filter on `debugPrintRebuildDirtyWidgets` with the same four widget names, 5 sends) reads as identical to the baseline test body. The file header is a few lines longer in this worktree, and the source SHAs differ.
- The harness (`test/support/harness.dart`, `fake_backend.dart`) was not diffed against the baseline tree; it may differ.
- The rebuild-count delta is therefore a change in the code under test plus a possibly unchanged method. It is only a valid before/after comparison if the harness is identical. This was not verified.

## Honest interpretation

- The scroll-frame median (0.11 ms) is unchanged. The p95 rose from 5.26 ms to about 7.85 ms, consistently across both runs. That is a real host-VM signal under this harness, but 90 frames gives a noisy p95 and a harness difference cannot be ruled out.
- The rebuild counts rose from a median of 9 to 20 per send. Both runs agree exactly. Because the filter is a debug-log text match, this is a proxy, and it is only comparable if the harness matched.
- Cold start is noise-dominated. With 7 samples per run, p95 is effectively the single largest sample and varied from 1360 ms to 2022 ms across two runs of the same code. The median moved from 313-337 ms to 210-215 ms, which is within what a 7-sample run can produce. Do not read a cold-start improvement or regression from these numbers.
- None of these numbers say anything about device jank, raster cost, or APK size.

## Batching claim

- The perf test measures rebuilds per send (5 sends with a fake whole-reply backend), NOT rebuilds per streamed delta. The fake backend emits one `message.delta` per reply, so token batching is NOT exercised.
- The measured filtered rebuild count per send went UP (median 9 -> 20) under the same method. This measurement does NOT support a claim that rebuilds decreased with batching.
- A per-delta batching measurement requires a multi-delta fake stream, which is not in this package.

## Commit

`docs(r1/qa): perf AFTER measurements`

## fixperf re-measurement (branch `r1/fixperf`, commit ca7e193)

Host-VM proxies only. Same caveats as above.

Streaming benchmark (`mobile/test/perf/stream_perf_test.dart`, 89acba8): 200 deltas. HEAD streams via `POST /v1/chat/stream` with one SSE body of 200 `message.delta` events. The baseline uses its non-streaming `POST /v1/messages` path, which returns the same 200 tokens as one reply, because the legacy backend has no per-delta stream. This adaptation is not a like-for-like streaming comparison.

| Metric | Baseline (`dcf4f75`) | HEAD before fix (89acba8) | HEAD after fix (ca7e193) |
|---|---|---|---|
| Filtered rebuilds per 200 deltas (ChatScreen/MessageBubble/_UserRow/Composer) | 3 (0.015/delta) | 11 (0.055/delta) | 11 (0.055/delta) |
| Frame build median / p95 (200 frames, 16 ms pump) | 0.18 ms / 25.20 ms | 0.32 ms / 45.30 ms (rerun 0.17 / 25.42) | 0.17 ms / 25.55 ms |
| Per-send filtered rebuilds, median (5 sends) | 9 | 20 | 20 |
| Release APK size | 22,392,361 bytes | HEAD build not yet complete; see below | pending |

Fix attempted: `ChatController` bumps a `streamRevision` ValueNotifier per 50 ms delta flush instead of `notifyListeners`, and `ChatScreen` wraps the streaming bubble in a `ValueListenableBuilder`. Tests pass (`test/features/chat`, `test/features/chat_test.dart`, `test/perf`). The filtered rebuild counts did NOT change, so the fix does not meet the gate. Per-send rebuilds also still exceed the baseline (20 vs 9). The filter counts lines naming ChatScreen/MessageBubble/_UserRow/Composer, and the HEAD burst's dominant dirty widgets are generic framework widgets (Theme, Focus, Text, Icon), so the filtered counter does not isolate the streaming path. The cause of the remaining 11 is not yet identified.

Cold-start proxy (`chat_perf_test.dart`, 7 samples, one run at ca7e193): median 242.6 ms, p95 2241.7 ms. Noise-dominated; do not read a trend from it.

Release APK: baseline 22,392,361 bytes. The HEAD build was started at ca7e193 as `flutter build apk --release` with log `/tmp/apk-logs/head2.log`. Its size is not yet recorded here.
