from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import dotenv_values

from scripts.setup_backend import collect, write_env


def test_env_roundtrip_and_private_permissions(tmp_path: Path) -> None:
    path = tmp_path / '.env'
    values = {'DAILY_AGENT_DATABASE_URL': "postgresql+psycopg://u:p%40ss@localhost/db",
              'DAILY_AGENT_AUTH_SECRET': "quoted'and\\secret#value"}
    write_env(path, values)
    assert dotenv_values(path) == values
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_env(path, {'DAILY_AGENT_AUTH_SECRET': 'replacement'})
    assert dotenv_values(path) == values


def test_collect_converts_postgres_without_displaying_secret(capsys: pytest.CaptureFixture[str]) -> None:
    url = 'postgresql://user:p%40ss@localhost/dev?sslmode=require'
    with patch('scripts.setup_backend.getpass.getpass', side_effect=[url, '']):
        values = collect()
    assert values['DAILY_AGENT_DATABASE_URL'] == url.replace('postgresql:', 'postgresql+psycopg:')
    assert len(values['DAILY_AGENT_AUTH_SECRET']) == 64
    assert values['DAILY_AGENT_LIVE_MODELS_ENABLED'] == 'false'
    assert 'p%40ss' not in capsys.readouterr().out


def test_collect_rejects_dotenv_interpolation() -> None:
    with patch('scripts.setup_backend.getpass.getpass', side_effect=[
        'postgresql://user:${PASSWORD}@localhost/dev', ''
    ]), pytest.raises(ValueError, match='interpolation'):
        collect()


def test_hidden_input_failure_aborts_without_writing(tmp_path: Path) -> None:
    import getpass
    import warnings

    from scripts.setup_backend import main

    def unavailable(prompt: str) -> str:
        warnings.warn("Cannot disable echo", getpass.GetPassWarning, stacklevel=2)
        raise AssertionError("Must abort before fallback input")

    with patch('scripts.setup_backend.ROOT', tmp_path), patch(
        'scripts.setup_backend.getpass.getpass', side_effect=unavailable
    ):
        assert main() == 1
    assert not (tmp_path / '.env').exists()


def test_default_setup_creates_data_directory(tmp_path: Path) -> None:
    from scripts.setup_backend import main

    with patch('scripts.setup_backend.ROOT', tmp_path), patch(
        'scripts.setup_backend.getpass.getpass', side_effect=['', '']
    ):
        assert main() == 0
    assert (tmp_path / 'data').is_dir()
    assert (tmp_path / '.env').is_file()
