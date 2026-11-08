# Squad A handoff: streaming reliability (branch r1/a)

## Delivered
- Backend: `src/daily_agent/streaming/` (registry, runner, sse), `src/daily_agent/routes/stream.py` (5 endpoints per §2), gateway streaming with finish_reason and first-byte/idle timeouts (`gateway/adapters.py`, `gateway/opencode.py`, `gateway/service.py`, `gateway/types.py`).
- Client: `mobile/lib/api/stream/` (sse_parser, run_events, run_stream_client), `mobile/lib/features/chat/state/chat_controller.dart`.
- Tests: `tests/unit/test_stream_{sse,registry,runner,routes}.py`; `mobile/test/api/stream/*`; `mobile/test/features/chat/chat_controller_test.dart`.

## Checks (main agent, this tree)
- `make PYTHON=.venv/bin/python lint`: All checks passed; secret scan clean.
- `make PYTHON=.venv/bin/python typecheck`: Success, no issues in 46 source files.
- `pytest tests/unit/test_stream_*.py`: 17 passed.
- `TZ=Asia/Kolkata flutter test test/api/stream test/features/chat/chat_controller_test.dart`: 38 passed (27 transport + 11 controller).
- `flutter analyze` on squad A dart paths: No issues found.

## Needs (outside squad A ownership)
- `src/daily_agent/api.py` (IntegrationLead): call `sweep_interrupted_runs(session)` at app startup. The function exists in `streaming/registry.py` and is NOT yet wired.
- `ChatController.send(text, attachmentTexts)` takes `List<String>` of already-inlined fenced text because `composer/text_attachment.dart` (squad E) was absent. Phase 2 wiring should adapt to the E type.

## Risks / remaining
- Stall/resume, stop and continue are covered by unit tests with fakes only; no e2e SSE test was run (QA owns e2e).
- Process-restart sweep is not active until the api.py call above lands.
- Provider malformed SSE frames are skipped with a debug log (no content).
- Not checked: `ruff format` on the repo (53 pre-existing files flagged, outside this change); dart format on the squad files was run by workers.
