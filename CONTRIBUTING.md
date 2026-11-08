# Contributing to Karmi

Thanks for helping. This guide covers how to set up the project, which checks to run, and how
changes are reviewed. The product is a privacy-scoped daily assistant: a FastAPI backend in
`src/daily_agent/`, an offline model lab in `src/model_lab/`, and a Flutter app in `mobile/`.
The Python package is named `daily_agent`; the project name is Karmi.

## Ground rules

- Open an issue before large changes so the direction can be agreed first.
- Keep pull requests small and focused on one change.
- Open pull requests as **drafts**. The maintainer reviews and merges them by hand. Do not
  enable auto-merge, and do not merge a pull request you opened unless the maintainer asks.
- Never commit secrets, `.env` files, keystores, `key.properties`, or real personal data.
  Test data must be synthetic and obviously fake (for example `test@example.com`).
- Screenshots and device evidence must use a synthetic test account and must not show emails,
  sign-in codes, phone numbers, or server addresses.

## Backend setup (Python 3.12+)

Linux or macOS:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
.venv/bin/python scripts/tasks.py doctor
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e ".[dev]"
.\.venv\Scripts\python.exe scripts\tasks.py doctor
```

`requirements.lock` is the pinned constraint file that CI uses. If you change dependencies in
`pyproject.toml`, regenerate the lock file as described in `CLAUDE.md`.

Run the local dev server with `scripts/tasks.py dev`. For the full local setup, including the
database, see `docs/runbooks/local-development.md`.

## Mobile setup (Flutter)

The app is in `mobile/`. It uses Flutter 3.47.5 with Dart 3.13 and the package name `karmi_app`.
Follow `mobile/README.md` for setup and the mobile gates.

## Checks to run

Run these from the repository root with the backend venv active. They are the same commands CI
runs (see `scripts/tasks.py` and `.github/workflows/ci.yml`).

| Area | Command | What it covers |
| --- | --- | --- |
| Backend lint | `python scripts/tasks.py lint` | `ruff check src tests scripts` plus the secret scan |
| Backend types | `python scripts/tasks.py typecheck` | `mypy src` |
| Backend unit | `python scripts/tasks.py test-unit` | `tests/unit`, `tests/model_lab`, `tests/web` |
| Backend end-to-end | `python scripts/tasks.py test-e2e` | `tests/e2e` |
| Backend integration | `python scripts/tasks.py test-integration` | `tests/integration`; needs Docker or podman |
| Model lab demo | `python scripts/tasks.py benchmark-demo` | run when `src/model_lab/` or `benchmarks/` changes |
| Mobile unit and widget | `cd mobile && flutter test --exclude-tags golden` | Flutter tests without golden files |
| Mobile golden | `cd mobile && TZ=Asia/Kolkata flutter test --tags golden` | golden images; CI sets `TZ` the same way |
| Android build | `cd mobile && flutter build appbundle --release` | release bundle |
| iOS build | `cd mobile && flutter build ipa --release --no-codesign` | macOS only; iOS is experimental and untested on device |

`test-integration` starts disposable PostgreSQL and Redis containers. If neither Docker nor podman
is installed, the task stops with an error. Say so in your pull request instead of skipping it
silently.

## Definition of done

From `CLAUDE.md`:

- `lint`, `typecheck`, `test-unit`, and `test-e2e` pass.
- Changes to money or concurrency also run `test-integration`, or the pull request says
  `NOT RUN` with the reason.
- Behaviour changes include a test that fails without the change.
- The pull request reports VERIFIED and NOT VERIFIED results separately. Do not mark Docker,
  device, payment, or provider checks as passed unless you ran them.

## Database migrations

Schema changes need a new Alembic revision in `migrations/` and the matching model change in the
same commit. Never edit a migration that has already been applied. A downgrade must not silently
drop user data. The rules are in `CLAUDE.md` and `.claude/rules/money-and-tenancy.md`.

## Test data

Use synthetic data only. Secrets in tests must look fake. Fixtures must stay obviously synthetic.
See `.claude/rules/testing.md`.

## Agent tooling in this repository

The project uses AI coding agents. Their configuration is committed so every contributor gets the
same guardrails. You do not need an agent to contribute.

| Path | Read by | Contents |
| --- | --- | --- |
| `CLAUDE.md`, `.claude/` | Claude Code | project instructions, rules, settings, agent definitions, the ruff hook |
| `AGENTS.md`, `.codex/` | Codex | project instructions, agent definitions, config, hooks |
| `.agents/skills/verify/` | skill-aware agent runtimes | the `verify` checklist (a `SKILL.md` file) |

Agents must not enable WhatsApp, paid checkout, live charges, or real outbound messages. They must
not deploy or run migrations against the hosted beta without owner approval, must not handle
secrets, and must not weaken fail-closed or budget checks. Agents must not force-push, rewrite
history, run `git reset --hard`, or delete untracked files.

Agent output is not a substitute for running the checks above.

## Pull request checklist

Use the template that GitHub fills in. In short: describe the change, list the checks you ran,
say whether you added a migration, and confirm that no secrets or personal data are included.

## Reporting bugs and security issues

- Bugs and feature ideas: use the issue forms. The in-app report (Settings → Report a bug) is
  the preferred route for bugs, because it attaches diagnostics.
- Security problems: do not open a public issue. See `SECURITY.md`.

## Licence

By contributing, you agree that your contribution is licensed under the MIT licence in `LICENSE`.
