#!/usr/bin/env bash
# Repeatable R1 perf baseline. Usage: docs/release1/perf/measure.sh [repo-root]
# Host-VM widget benchmarks (cold-start proxy, scroll frame pump, rebuild counts) + release APK size.
set -euo pipefail
ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT/mobile"
flutter test test/perf/chat_perf_test.dart --reporter expanded 2>&1 | grep -E "^PERF |passed|failed"
flutter build apk --release --target-platform android-arm64 --analyze-size 2>&1 | tail -n 40
