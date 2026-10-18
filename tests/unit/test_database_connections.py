from unittest.mock import patch

import pytest
from sqlalchemy.engine import make_url

from daily_agent.config import Settings
from daily_agent.db import build_engine


def test_neon_urls_are_normalized_and_tls_verified() -> None:
    settings = Settings(_env_file=None, database_url=(
        'postgresql://user:p%40ss@ep-fixture-pooler.ap-southeast-1.aws.neon.tech/neondb'
        '?sslmode=require&channel_binding=require'
    ))
    url = make_url(settings.database_url)
    assert url.drivername == 'postgresql+psycopg'
    assert url.password == 'p@ss'  # noqa: S105 - synthetic URL roundtrip fixture
    assert url.query['sslmode'] == 'verify-full'
    assert url.query['sslrootcert'].endswith('/certifi/cacert.pem')
    assert url.query['channel_binding'] == 'require'
    with pytest.raises(ValueError, match='direct'):
        _ = settings.migration_url


def test_migration_uses_explicit_direct_url() -> None:
    settings = Settings(_env_file=None,
        database_url='postgresql://u:p@ep-fixture-pooler.aws.neon.tech/neondb',
        migration_database_url='postgresql://u:p@ep-fixture.aws.neon.tech/neondb')
    assert make_url(settings.migration_url).host == 'ep-fixture.aws.neon.tech'
    assert '-pooler' in settings.database_url


def test_postgres_pool_is_bounded_without_connecting() -> None:
    settings = Settings(_env_file=None, database_url='postgresql://u:p@localhost/dev')
    with patch('daily_agent.db.create_engine') as create:
        build_engine(settings)
    assert create.call_args.kwargs['pool_size'] == 2
    assert create.call_args.kwargs['max_overflow'] == 0
    assert create.call_args.kwargs['pool_timeout'] == 15
    assert create.call_args.kwargs['pool_pre_ping'] is True
    assert create.call_args.kwargs['connect_args']['connect_timeout'] == 15


def test_sqlite_migration_fallback_unchanged() -> None:
    settings = Settings(_env_file=None)
    assert settings.migration_url == settings.database_url


def test_postgres_startup_does_not_create_schema() -> None:
    from fastapi.testclient import TestClient

    from daily_agent.api import create_app

    settings = Settings(_env_file=None, database_url='postgresql://u:p@localhost/dev')
    with patch('daily_agent.api.get_settings', return_value=settings), patch(
        'daily_agent.api.create_schema'
    ) as create, TestClient(create_app()) as client:
        assert client.get('/health').status_code == 200
    create.assert_not_called()


def test_schema_helper_rejects_postgres_before_any_write() -> None:
    from unittest.mock import MagicMock

    from daily_agent.db import create_schema

    engine = MagicMock()
    engine.dialect.name = 'postgresql'
    with patch('daily_agent.db.Base.metadata.create_all') as create, pytest.raises(
        ValueError, match='SQLite-only'
    ):
        create_schema(engine)
    create.assert_not_called()


def test_postgres_worker_does_not_create_schema() -> None:
    from daily_agent.worker import main

    settings = Settings(_env_file=None, database_url='postgresql://u:p@localhost/dev')
    with patch('daily_agent.config.get_settings', return_value=settings), patch(
        'daily_agent.db.create_schema'
    ) as create, patch('daily_agent.db.get_engine'), patch(
        'daily_agent.db.SessionLocal'
    ), patch('daily_agent.worker.run_once', side_effect=KeyboardInterrupt):
        main()
    create.assert_not_called()


def test_runtime_engine_uses_pooled_url_not_migration_url() -> None:
    settings = Settings(_env_file=None,
        database_url='postgresql://u:p@ep-fixture-pooler.aws.neon.tech/neondb',
        migration_database_url='postgresql://u:p@ep-fixture.aws.neon.tech/neondb')
    with patch('daily_agent.db.create_engine') as create:
        build_engine(settings)
    runtime_host = make_url(create.call_args.args[0]).host
    assert runtime_host == 'ep-fixture-pooler.aws.neon.tech'
