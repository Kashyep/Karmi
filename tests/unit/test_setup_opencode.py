from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from scripts.setup_opencode import main, write_private_env


def test_opencode_setup_saves_hidden_key_without_overwriting(tmp_path: Path, capsys) -> None:
    with patch("scripts.setup_opencode.ROOT", tmp_path), patch(
        "scripts.setup_opencode.getpass.getpass", return_value="sk-test-secret-value"
    ):
        assert main() == 0
        assert main() == 1

    saved = tmp_path / ".env.opencode"
    assert dotenv_values(saved)["DAILY_AGENT_OPENCODE_API_KEY"] == "sk-test-secret-value"
    assert saved.stat().st_mode & 0o777 == 0o600
    output = capsys.readouterr().out
    assert "sk-test-secret-value" not in output
    assert "No provider request was made" in output


def test_opencode_setup_rejects_multiline_and_interpolation(tmp_path: Path) -> None:
    for key in ("first\nsecond", "${SECRET}"):
        try:
            write_private_env(tmp_path / ".env.opencode", key)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe API key format was accepted")
        assert not (tmp_path / ".env.opencode").exists()
