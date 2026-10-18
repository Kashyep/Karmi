"""Safely advance an expected Neon neondb revision after explicit approval."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from daily_agent.config import Settings

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = 'c5d7e9f1a2b4'
TARGET_REVISION = '1a2b3c4d5e6f'
CLERK_UNIQUE_CONSTRAINT_SQL = (
    "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint AS c "
    "JOIN pg_catalog.pg_attribute AS a ON a.attrelid=c.conrelid "
    "AND a.attnum=ANY(c.conkey) "
    "WHERE c.conname='uq_users_clerk_subject' AND c.conrelid='public.users'::regclass "
    "AND c.contype='u' AND a.attname='clerk_subject' AND array_length(c.conkey, 1)=1)"
)


def classify_migration_state(
    existing_tables: set[str],
    revisions: list[str],
    has_clerk_subject: bool,
    has_clerk_constraint: bool,
) -> str:
    if revisions == [TARGET_REVISION] and has_clerk_subject and has_clerk_constraint:
        return 'current'
    if not existing_tables and not revisions:
        return 'fresh'
    if (
        revisions == [PREVIOUS_REVISION]
        and 'users' in existing_tables
        and not has_clerk_subject
        and not has_clerk_constraint
    ):
        return 'migrate'
    return 'refuse'


def connect_read_only(url: str) -> psycopg.Connection:
    return psycopg.connect(
        url,
        connect_timeout=15,
        sslmode='verify-full',
        options='-c default_transaction_read_only=on -c statement_timeout=10000',
    )


def main() -> int:
    values = dotenv_values(ROOT / '.env.neon', interpolate=False)
    try:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(
                _env_file=None,
                database_url=values.get('DAILY_AGENT_DATABASE_URL', ''),
                migration_database_url=values.get('DAILY_AGENT_MIGRATION_DATABASE_URL', ''),
            )
        runtime = make_url(settings.database_url)
        direct = make_url(settings.migration_url)
        if (runtime.database != 'neondb' or direct.database != 'neondb'
                or not runtime.host or not runtime.host.endswith('.neon.tech')
                or '-pooler.' not in runtime.host
                or not direct.host or not direct.host.endswith('.neon.tech')
                or '-pooler.' in direct.host
                or direct.host != runtime.host.replace('-pooler.', '.', 1)):
            print('Refusing migration: expected matching Neon pooled/direct URLs for neondb.')
            return 1
        direct_driver_url = direct.set(drivername='postgresql').render_as_string(hide_password=False)
        with connect_read_only(direct_driver_url) as connection, connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_schema(), current_setting(\'server_version\')')
            database, schema, version = cursor.fetchone()
            cursor.execute(
                "SELECT schemaname, tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
            existing_tables = {row[1] for row in cursor.fetchall()}
            has_version = 'alembic_version' in existing_tables
            revisions: list[str] = []
            if has_version:
                cursor.execute('SELECT version_num FROM public.alembic_version ORDER BY version_num')
                revisions = [row[0] for row in cursor.fetchall()]
            has_clerk_subject = False
            has_clerk_constraint = False
            if 'users' in existing_tables:
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='users' "
                    "AND column_name='clerk_subject')"
                )
                has_clerk_subject = bool(cursor.fetchone()[0])
                cursor.execute(CLERK_UNIQUE_CONSTRAINT_SQL)
                has_clerk_constraint = bool(cursor.fetchone()[0])
        if database != 'neondb' or schema != 'public':
            print('Refusing migration: database or schema does not match the expected Neon target.')
            return 1
        migration_state = classify_migration_state(
            existing_tables, revisions, has_clerk_subject, has_clerk_constraint
        )
        if migration_state == 'current':
            print(f'ALREADY_CURRENT: {database} is at revision {TARGET_REVISION}.')
            return 0
        if migration_state == 'refuse':
            print('Refusing migration: schema is neither empty nor at the reviewed previous revision.')
            print('No migration was run; inspect the current schema and Alembic revision first.')
            return 1
        prior_state = 'empty schema' if migration_state == 'fresh' else f'revision {PREVIOUS_REVISION}'
        print(
            f'Preflight passed: {database}, {schema}, PostgreSQL {version.split()[0]}, '
            f'{prior_state}; target {TARGET_REVISION}.'
        )
        child_env = {k: v for k, v in os.environ.items() if not k.startswith('DAILY_AGENT_')}
        child_env.update({k: v for k, v in values.items() if v is not None})
        result = subprocess.run(  # noqa: S603 - fixed local Alembic command, validated direct Neon endpoint
            [str(ROOT / '.venv/bin/python'), '-m', 'alembic', 'upgrade', TARGET_REVISION],
            cwd=ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            # Captured Alembic diagnostics can contain a connection URL: suppress them.
            print(f'Alembic failed with exit code {result.returncode}; diagnostic output suppressed.')
            return result.returncode
        with connect_read_only(direct_driver_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename")
            tables = [row[0] for row in cursor.fetchall()]
            cursor.execute('SELECT version_num FROM public.alembic_version ORDER BY version_num')
            revisions = [row[0] for row in cursor.fetchall()]
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='users' AND column_name='clerk_subject')"
            )
            has_clerk_subject = bool(cursor.fetchone()[0])
            cursor.execute(CLERK_UNIQUE_CONSTRAINT_SQL)
            has_clerk_constraint = bool(cursor.fetchone()[0])
        if revisions != [TARGET_REVISION] or not has_clerk_subject or not has_clerk_constraint:
            print('Migrations ran, but revision or Clerk column verification failed.')
            return 1
        print(f'MIGRATIONS_APPLIED_SUCCESSFULLY: {len(tables)} tables; revision {revisions[0]}.')
        return 0
    except Exception as exc:
        print(f'Migration setup failed: {type(exc).__name__}; database diagnostics suppressed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
