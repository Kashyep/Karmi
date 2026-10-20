# Daily Agent

Daily Agent is a bounded, privacy-scoped assistant backend with an owned web/PWA shell and an
offline model evaluation lab. This repository is an implementation candidate derived from the
specification in `docs/blueprint/`.

Current status: beta (`v0.1.0-beta.1`, Android). A hosted beta backend runs on Azure Container
Apps with Neon PostgreSQL. WhatsApp and paid checkout are disabled. Live model providers are off by
default; when an OpenRouter or OpenCode key is configured, chat replies come from free models
through the model gateway, otherwise they are deterministic demo copy. All live replies share one
daily provider-request cap (`DAILY_AGENT_GATEWAY_DAILY_REQUEST_LIMIT`, default 50) with a reserve
for paid plans. Plan prices are the owner's labels; quotas and costs are still provisional.

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

For interactive connection setup and mobile connection commands, see
`docs/runbooks/backend-setup.md`.

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
- Provider keys remain server-side. The optional TypeSafe integration only performs structured
  classification; it does not generate the chat reply. Its current
  synthetic rate card is not approved for real spend accounting. Do not enable it for production.
- Parakh model-selection bundles are shadow-only. They record candidate decisions and do not select
  a model for live traffic. ModelLab has a validated 60-case offline seed bank and import/report
  tools, but no live model runner or evidence-backed best-model recommendation yet.
- WhatsApp activation is hard-disabled for the present India-first release because current terms
  restrict general-purpose AI as the primary service outside the stated EEA/Brazil exception.
- Billing accepts signed sandbox fixtures only. No checkout or live charge path is present.
- All examples, users, messages, plan limits and costs are synthetic.

See `Memory.md` for verified state and `docs/release-evidence/` for candidate-specific evidence.
