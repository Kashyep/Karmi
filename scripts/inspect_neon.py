"""Read-only inventory of Neon schema state; never applies or proposes migrations."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from daily_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    values = dotenv_values(ROOT / '.env.neon', interpolate=False)
    raw_url = values.get('DAILY_AGENT_MIGRATION_DATABASE_URL')
    if not raw_url:
        print('Missing direct Neon URL in .env.neon')
        return 1
    settings = Settings(_env_file=None, database_url=values.get('DAILY_AGENT_DATABASE_URL', ''),
                        migration_database_url=raw_url)
    url = make_url(settings.migration_url)
    if url.host is None or not url.host.endswith('.neon.tech') or '-pooler.' in url.host:
        print('Refusing inventory: expected the direct Neon endpoint.')
        return 1
    driver_url = url.set(drivername='postgresql').render_as_string(hide_password=False)
    try:
        with psycopg.connect(
            driver_url,
            connect_timeout=15,
            sslmode='verify-full',
            sslrootcert=url.query['sslrootcert'],
            options='-c default_transaction_read_only=on -c statement_timeout=10000',
        ) as connection, connection.cursor() as cursor:
                cursor.execute(
                    'SELECT current_database(), current_schema(), '
                    'current_setting(\'server_version\')'
                )
                database, schema, version = cursor.fetchone()
                cursor.execute(
                    "SELECT tablename FROM pg_catalog.pg_tables "
                    "WHERE schemaname = 'public' ORDER BY tablename"
                )
                tables = [row[0] for row in cursor.fetchall()]
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_tables "
                    "WHERE schemaname='public' AND tablename='alembic_version')"
                )
                has_version = cursor.fetchone()[0]
                revision = None
                if has_version:
                    cursor.execute('SELECT version_num FROM public.alembic_version ORDER BY version_num')
                    revision = [row[0] for row in cursor.fetchall()]
        print('READ_ONLY_INVENTORY_SUCCESS')
        print(f'Database: {database}; schema: {schema}; PostgreSQL: {version.split()[0]}')
        print(f'Public tables ({len(tables)}): {", ".join(tables) if tables else "none"}')
        print(f'Alembic version table: {"present" if has_version else "absent"}')
        if revision is not None:
            print(f'Recorded revision(s): {", ".join(revision) if revision else "empty"}')
        return 0
    except Exception as exc:
        # Connection exceptions may embed credentials. Never print them.
        diagnostic = str(exc).lower()
        category = next((name for needle, name in ((
            'certificate', 'TLS certificate verification'),
            ('could not translate host', 'DNS resolution'),
            ('name or service not known', 'DNS resolution'),
            ('timeout', 'network timeout'),
            ('authentication', 'database authentication'),
            ('password', 'database authentication'),
            ('connection refused', 'network connection refused'),
            ('network is unreachable', 'network unreachable'),
        ) if needle in diagnostic), 'unclassified connection error')
        print(f'Read-only inventory failed: {type(exc).__name__}')
        print(f'Diagnostic category: {category}')
        print(f'Cause: {type(exc.__cause__).__name__ if exc.__cause__ else "unavailable"}')
        print(f'SQLSTATE: {getattr(exc, "sqlstate", None) or "unavailable"}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
