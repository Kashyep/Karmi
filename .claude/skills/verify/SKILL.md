---
name: verify
description: Run this repository's verification gates (lint+secret scan, mypy strict, unit, e2e, ModelLab demo, and integration when Docker is up) and report a compact PASS/FAIL/NOT RUN table. Use before declaring a change done or before committing.
---

Run from the repo root, one gate at a time, capturing output to a temp file and showing only the
summary line (`All checks passed` / `Success:` / `N passed` / first failure):

1. `python scripts/tasks.py lint`
2. `python scripts/tasks.py typecheck`
3. `python scripts/tasks.py test-unit`
4. `python scripts/tasks.py test-e2e`
5. `python scripts/tasks.py benchmark-demo`: only if `src/model_lab/` or `benchmarks/` changed
6. `docker info` succeeds → `python scripts/tasks.py test-integration`; otherwise record
   `NOT RUN: Docker daemon unavailable`. Required for changes to budget/money code, models or migrations.

On failure show the failing test id and the assertion or error lines only, not the full log.
Do not re-run a failing gate unchanged. Diagnose first.

Report:
```
PASS:    <gate> (<counts>)
FAIL:    <gate> — <one-line reason>
NOT RUN: <gate> — <reason>
```
