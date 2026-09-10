# Local development runbook

1. Create `.venv` and install `.[dev]` as shown in the root README.
2. Run `python scripts/tasks.py doctor` and `python scripts/tasks.py lint`.
3. Run `python scripts/tasks.py dev`; open `/`, `/docs`, `/health` and `/ready`.
4. Create a synthetic token with `POST /dev/token`. Never enable this endpoint in production.
5. Use only synthetic notes/tasks/reminders. Reminder delivery is `test_adapter_only`.
6. Stop with Ctrl+C. Local SQLite data is under ignored `data/`; it is not production evidence.

If readiness fails, verify the configured database first. Live providers, checkout and WhatsApp
must remain false unless a later reviewed release explicitly replaces the current gates.

