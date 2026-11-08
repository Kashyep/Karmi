# Squad BW handoff: backend wiring (branch r1/bw)

## Wired
- `api.py` lifespan: `sweep_interrupted_runs(Session(get_engine()))` at startup (logs count when >0). Routers unchanged; `/v1` chat routes untouched.
- `routes/stream.py` `chat_stream`: conversation create/attach via `ensure_conversation_for_message` (flush only; budget denial rollback leaves no empty record).
- Terminal touch: `streaming/runner.py` `_flush_db` touches the conversation when run status is COMPLETED/FAILED (covers completed, stopped, failed); `routes/stream.py` `stop_run` touches it on the no-registry stop path.

## Deviation (flag)
- Terminal touch lives in `runner.py`, not `routes/stream.py`: the runner is where terminal state is written, and the route cannot observe background completion.

## Checks (worktree, run by BW)
- `ruff check` on edited files: All checks passed.
- `mypy` on api.py, routes/stream.py, streaming/runner.py: Success, no issues in 3 files.
- pytest tests/e2e/test_release1_stream_conversations.py + tests/unit/test_stream_{routes,runner}.py + tests/unit/test_conversations_{routes,service}.py: 39 passed (~47s, includes 16.5s heartbeat test).

## Not run
- `make lint` / `make typecheck` (full), full `tests/unit tests/e2e`, `make test-integration` (Postgres availability not checked).
- Not committed yet at time of writing (see SHA in report).
