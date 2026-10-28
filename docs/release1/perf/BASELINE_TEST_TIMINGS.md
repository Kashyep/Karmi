# Pre-R1 timing baseline (QA-recorded, 2026-10-21)

Commit base: `dcf4f75` (origin/main), branch `release1/chat-redesign`. Machine: linux 7.2.11-arch1-1, x64.

| Measurement | Command | Result |
|---|---|---|
| Backend unit/model-lab/web | `make PYTHON=.venv/bin/python test-unit` | 166 passed in 9.07s (pytest-reported) |
| Backend e2e | `make PYTHON=.venv/bin/python test-e2e` | 51 passed in 5.31s (pytest-reported) |
| Flutter analyze | `cd mobile && flutter analyze` | No issues found (ran in 11.0s) |
| Flutter tests incl. goldens | `cd mobile && TZ=Asia/Kolkata flutter test` | 340 passed, wall time 30.02s |

Runtime perf metrics for the redesign (time-to-interactive, transcript rebuilds per delta, p95 list/search latency) are NOT measured yet; they will be added here with the exact reproducing command when squad G and QA instrument them. Until then they are recorded as "not measured", not as passing.
