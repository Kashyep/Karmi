# Daily Agent

Daily Agent is a bounded, privacy-scoped assistant backend with an owned web/PWA shell and an
offline model evaluation lab. This repository is an implementation candidate derived from the
specification in `docs/blueprint/`.

Current status: local development candidate. WhatsApp, paid checkout and live model providers
are disabled. The development plans and costs are synthetic fixtures, not commercial offers.

## Prerequisites

- Python 3.12 or newer (3.14 is used by the recorded Windows run)
- Docker Desktop with Compose for PostgreSQL/Redis integration checks
- GNU Make is optional; every Make target delegates to `python scripts/tasks.py`

## Install and run

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\tasks.py doctor
.\.venv\Scripts\python.exe scripts\tasks.py dev
```

Linux/macOS:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/tasks.py doctor
.venv/bin/python scripts/tasks.py dev
```

Open <http://127.0.0.1:8000/> for the owned-channel shell and
<http://127.0.0.1:8000/docs> for the API explorer. `POST /dev/token` creates a synthetic local
identity only when development authentication is enabled.

## Verification commands

```bash
python scripts/tasks.py test-unit
python scripts/tasks.py test-e2e
python scripts/tasks.py benchmark-demo
python scripts/tasks.py test-integration
python scripts/tasks.py test-release
```

`test-integration` starts explicitly named disposable Compose services and refuses to run against
an undeclared database. `test-release` runs real lint, type, unit, E2E, ModelLab and integration
checks; it exits nonzero when a required gate is unavailable or fails.

## Safety boundaries

- Production mode requires PostgreSQL, real authentication configuration and finite approved
  monetary budgets. It rejects the development secret and local auth flow.
- Provider keys remain server-side. The TypeSafe adapter is opt-in: it only runs when
  `DAILY_AGENT_LIVE_MODELS_ENABLED=true`, is bounded by per-attempt budget reservations, and
  every measured call is recorded in the cost ledger. In production it additionally requires an
  approved finite `production_period_budget_micro`.
- WhatsApp activation is hard-disabled for the present India-first release because current terms
  restrict general-purpose AI as the primary service outside the stated EEA/Brazil exception.
- Billing accepts signed sandbox fixtures only. No checkout or live charge path is present.
- All examples, users, messages, plan limits and costs are synthetic.

See `Memory.md` for verified state and `docs/release-evidence/` for candidate-specific evidence.

