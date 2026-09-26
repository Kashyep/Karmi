---
paths:
  - "tests/**"
---

# Test conventions

- Shared fixtures: `tests/conftest.py`. `test_context` gives a `TestClient` over a temp SQLite DB
  plus `factory` / `settings`; `create_identity(session, settings, name=..., role=...)` returns
  `(account, user, token)`.
- E2E tests hit HTTP through the client; unit tests call `services` functions with a session.
- Integration tests (`tests/integration`, marker `integration`) refuse to run outside the declared
  disposable Postgres/Redis started by `tasks.py test-integration`.
- Use synthetic data only. Secrets in tests must look fake (ruff `S106` is ignored under tests/).
- Never loosen an assertion or add a skip to get green. Fix the code or report the failure.
- ~1000 `DeprecationWarning`s come from a globally installed pytest-asyncio on Python 3.14, not
  from this repo. Ignore them.
