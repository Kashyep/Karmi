from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from scripts.setup_neon import main


def test_neon_setup_saves_separately_without_overwriting(tmp_path: Path) -> None:
    (tmp_path / '.env').write_text('LOCAL=preserved\n')
    urls = ['postgresql://u:p%40ss@ep-fixture-pooler.aws.neon.tech/neondb',
            'postgresql://u:p%40ss@ep-fixture.aws.neon.tech/neondb']
    with patch('scripts.setup_neon.ROOT', tmp_path), patch(
        'scripts.setup_neon.getpass.getpass', side_effect=urls
    ):
        assert main() == 0
        assert main() == 1
    values = dotenv_values(tmp_path / '.env.neon')
    assert 'sslmode=verify-full' in values['DAILY_AGENT_DATABASE_URL']
    assert (tmp_path / '.env').read_text() == 'LOCAL=preserved\n'
    assert (tmp_path / '.env.neon').stat().st_mode & 0o777 == 0o600


def test_neon_setup_rejects_different_endpoints(tmp_path: Path) -> None:
    with patch('scripts.setup_neon.ROOT', tmp_path), patch(
        'scripts.setup_neon.getpass.getpass', side_effect=[
            'postgresql://u:p@ep-one-pooler.aws.neon.tech/neondb',
            'postgresql://u:p@ep-other.aws.neon.tech/neondb'
        ]
    ):
        assert main() == 1
    assert not (tmp_path / '.env.neon').exists()
