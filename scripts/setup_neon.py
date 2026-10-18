"""Save Neon URLs privately; never connect, start the app or run migrations."""
from __future__ import annotations

import getpass
import os
import warnings
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.engine import make_url

from daily_agent.config import Settings
from scripts.setup_backend import write_env

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    target = ROOT / '.env.neon'
    if target.exists() or target.is_symlink():
        print('Existing .env.neon preserved. No changes made.')
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            pooled = getpass.getpass('Paste Neon POOLED URL (pooling ON, hidden): ').strip()
            direct = getpass.getpass('Paste Neon DIRECT URL (pooling OFF, hidden): ').strip()
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None, database_url=pooled, migration_database_url=direct)
        runtime = make_url(settings.database_url)
        migration = make_url(settings.migration_url)
        host = runtime.host or ''
        direct_host = migration.host or ''
        if (runtime.drivername != 'postgresql+psycopg'
                or migration.drivername != 'postgresql+psycopg'
                or not host.endswith('.neon.tech')
                or '-pooler.' not in host
                or direct_host != host.replace('-pooler.', '.', 1)
                or runtime.database != migration.database
                or runtime.database != 'neondb'):
            raise ValueError('Use matching Neon pooled/direct URLs for neondb.')
        values = {
            'DAILY_AGENT_DATABASE_URL': settings.database_url,
            'DAILY_AGENT_MIGRATION_DATABASE_URL': settings.migration_url,
        }
        if any('\n' in v or '\r' in v or '${' in v for v in (pooled, direct)):
            raise ValueError('URLs must be literal single lines.')
        write_env(target, values)
    except (ValueError, OSError, EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print('Setup stopped. Check matching URL formats and terminal permissions. Secrets not displayed.')
        return 1
    print('Saved private .env.neon. No database connection or schema changes performed.')
    print('This file is not loaded automatically. Do not start the app or run migrations against Neon yet.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
