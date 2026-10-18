"""Create a private development connection file without echoing credentials."""
from __future__ import annotations

import getpass
import os
import secrets
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.engine import make_url

from daily_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def collect() -> dict[str, str]:
    print('Karmi development setup. Use a dedicated development database only.')
    print('Leave the database URL blank for local SQLite (no account or password needed).')
    database = getpass.getpass('Paste development PostgreSQL URL (hidden), or Enter for SQLite: ').strip()
    if not database:
        database = 'sqlite+pysqlite:///./data/development.db'
    if "${" in database or "\n" in database or "\r" in database:
        raise ValueError("Connection URL cannot contain interpolation or newlines.")
    url = make_url(database)
    if url.drivername in {'postgres', 'postgresql'}:
        database = url.set(drivername='postgresql+psycopg').render_as_string(hide_password=False)
    elif url.drivername not in {'postgresql+psycopg', 'sqlite+pysqlite'}:
        raise ValueError('Use postgresql+psycopg:// or sqlite+pysqlite://.')
    print('Redis is optional; current workers use the database outbox.')
    redis = getpass.getpass('Paste development Redis URL (hidden), or Enter to skip: ').strip()
    if redis and make_url(redis).drivername not in {'redis', 'rediss'}:
        raise ValueError('Redis URL must start with redis:// or rediss://.')
    values = {
        'DAILY_AGENT_ENVIRONMENT': 'development',
        'DAILY_AGENT_DATABASE_URL': database,
        'DAILY_AGENT_REDIS_URL': redis,
        'DAILY_AGENT_AUTH_SECRET': secrets.token_hex(32),
        'DAILY_AGENT_WEBHOOK_SECRET': secrets.token_hex(32),
        'DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH': 'true',
        'DAILY_AGENT_LIVE_MODELS_ENABLED': 'false',
        'DAILY_AGENT_PAID_CHECKOUT_ENABLED': 'false',
        'DAILY_AGENT_WHATSAPP_ENABLED': 'false',
        'DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO': '100000',
    }
    if any('\n' in value or '\r' in value or '${' in value for value in values.values()):
        raise ValueError('Connection values must be single lines without dotenv interpolation.')
    with patch.dict(os.environ, {}, clear=True):
        Settings(_env_file=None, **{
            key.removeprefix('DAILY_AGENT_').lower(): value for key, value in values.items()
        })
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    # Exclusive creation preserves existing operator configuration, including symlinks.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write('# Private local development configuration. Never commit this file.\n')
        for key, value in values.items():
            quoted = value.replace('\\', '\\\\').replace("'", "\\'")
            stream.write(f"{key}='{quoted}'\n")


def main() -> int:
    path = ROOT / '.env'
    if path.exists() or path.is_symlink():
        print('Existing .env preserved. Edit it locally or move it before rerunning setup.')
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            values = collect()
        if values["DAILY_AGENT_DATABASE_URL"] == "sqlite+pysqlite:///./data/development.db":
            (ROOT / "data").mkdir(parents=True, exist_ok=True)
        write_env(path, values)
    except (ValueError, OSError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        # Validation exceptions can contain credential-bearing URLs: do not print them.
        print('Setup stopped. Check URL format and file permissions; no credentials displayed.')
        return 1
    print('Saved private .env; generated authentication and webhook secrets locally.')
    print('Next: .venv/bin/python -m alembic upgrade head')
    print('Then: .venv/bin/python scripts/tasks.py dev')
    print('Live models and checkout remain disabled. No provider API key is needed for this setup.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
