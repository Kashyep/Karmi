# R1 perf baseline (pre-redesign, measured)

Source tree: `/tmp/karmi-baseline` at `dcf4f75` (detached). Machine: linux 7.2.11-arch1-1, x64. Flutter 3.47.5 (stable). Measurements are host-VM widget tests, not device runs.

Reproduce: `docs/release1/perf/measure.sh <repo-root>` runs `flutter test test/perf/chat_perf_test.dart` (the PERF lines) and the release APK size build.

## Results

| Metric | Method | Result |
|---|---|---|
| Cold start proxy (`pumpApp` to settled first frame) | `flutter test`, 7 samples, Stopwatch around harness `pumpApp` (includes `settle`, fake backend, prefs). Proxy only: no real engine start, no splash, no network. | median 337 ms, p95 2075 ms (run 2; run 1 median 313 ms, p95 1521 ms) |
| Chat list scroll frame pump time, 40-entry transcript | 20 sends via UI with fake replies, then 90 manual drag steps (35 px each), timing each `pump(16ms)`. Covers build+layout+paint on the host VM. No raster/GPU. | median 0.11 ms, p95 5.26 ms (90 frames) |
| Chat rebuild count per delta (ChatScreen, MessageBubble, _UserRow, Composer) | `debugPrintRebuildDirtyWidgets` log lines filtered by widget name, per send, 5 sends | 3, 6, 9, 12, 15 per send (grows with transcript length; median 9) |
| Rebuild count, all widgets (unfiltered) | same log, unfiltered | 398 to 836 per send, grows with transcript (includes Overlay/Ticker tree) |
| Streaming frame timing | NOT MEASURED. The fake backend returns whole replies; there is no token stream to simulate. | n/a |
| Device frame timings / jank (`flutter run --profile`, DevTools) | NOT MEASURED. No device attached in this session. | n/a |
| Release APK size (`flutter build apk --release --target-platform android-arm64 --analyze-size`) | Gradle build started and did not finish within the session cap; no APK artifact was produced. Android SDK present at ~/Android/Sdk. | NOT MEASURED (rerun `measure.sh`) |
| Backend p50 latency of key endpoints | NOT MEASURED. Not attempted in this session (time cap). | n/a |

## Caveats

- Scroll and rebuild numbers are from a host widget test. They are not comparable to device frame budgets.
- The rebuild filter relies on debug log text ("Rebuilding ... ChatScreen"); it is a proxy, not an exact per-widget count.
- The cold-start number is `pumpApp` wall time under the test binding, not app launch to first frame.

## Files

- `mobile/test/perf/chat_perf_test.dart` (new)
- `docs/release1/perf/measure.sh` (new)
- `docs/release1/perf/BASELINE.md` (this file)

## Commit

Commit SHA: recorded in the handoff (see yield).
